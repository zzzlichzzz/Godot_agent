# -*- coding: utf-8 -*-
"""Тесты альфа-моста agent_bridge.py (MCP v0).

Контракт моста, который здесь закрепляется:
  * код возврата 0 — успех, данные в stdout;
  * код возврата 2 — «запрошенного не существует» / обоснованный отказ
    (класс неизвестен кэшу, совпадений нет, источник переименования отсутствует).
    Это ОТВЕТ инструмента, а не его сбой;
  * код возврата 3 — инструмент НЕ СМОГ ответить (исключение, нет кэша,
    сервер недоступен для status);
  * код возврата 4 — неверные аргументы командной строки;
  * в stderr всегда одна статусная строка вида «bridge: ok|not-found|error|usage: ...»,
    исключения не утекают наружу traceback'ом.
"""
import contextlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import agent_bridge  # noqa: E402
import gd_api_cache  # noqa: E402


def run_bridge(argv):
    """Запуск CLI внутри процесса: (rc, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = agent_bridge.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


# Кэш НОВОГО формата: рядом с арностью лежат полные сигнатуры методов
# (их собирает экспортёр ClassDB из agent_api_export.gd).
_SIG_CLASSES = {
    "Object": {"inherits": "", "methods": {"free": [0, 0]}, "properties": [], "signals": []},
    "PhysicsBody2D": {
        "inherits": "Object",
        "methods": {"get_collision_layer": [0, 0]},
        "signatures": {"get_collision_layer": "get_collision_layer() -> int"},
        "properties": [],
        "signals": [],
    },
    "CharacterBody2D": {
        "inherits": "PhysicsBody2D",
        "methods": {"move_and_slide": [0, 0], "take_hit": [1, 2]},
        "signatures": {
            "move_and_slide": "move_and_slide() -> bool",
            "take_hit": "take_hit(amount: int, crit: bool = false) -> void",
        },
        "properties": ["velocity"],
        "signals": [],
    },
}


class AgentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bridge_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = str(Path(self.temp.name))
        self.store = str(Path(self.temp.name, "bridge_store"))
        self.agent_dir = Path(self.root, "addons", "Godot_agent", "godot_agent")
        self.external_addon = Path(self.root, "addons", "demo")
        self.agent_dir.mkdir(parents=True)
        self.external_addon.mkdir(parents=True)
        (self.agent_dir / "agent.gd").write_text(
            "extends Node\nconst TOKEN = \"AGENT_ONLY_TOKEN\"\n", encoding="utf-8")
        (self.external_addon / "tool.gd").write_text(
            "extends Node\nconst TOKEN = \"ADDON_ONLY_TOKEN\"\n", encoding="utf-8")
        Path(self.root, "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="Bridge Test Proj"\n',
            encoding="utf-8")
        Path(self.root, "src").mkdir()
        Path(self.root, "src", "player.gd").write_text(
            'extends Node\nclass_name Player\n\nvar hp = 100\n\nfunc take_damage(amount):\n\thp -= amount\n',
            encoding="utf-8")
        Path(self.root, "src", "player.gd.uid").write_text('uid://bridgeplayer\n', encoding="utf-8")
        Path(self.root, "src", "main.gd").write_text(
            'extends Node\nconst P = preload("res://src/player.gd")\n', encoding="utf-8")
        gd_api_cache.save_cache(self.root, {
            "Object": {"inherits": "", "methods": {"free": [0, 0]}, "properties": [], "signals": []},
            "Node": {"inherits": "Object", "methods": {"add_child": [1, 1], "get_node": [1, 1]},
                     "properties": ["name"], "signals": ["ready"]},
            "CharacterBody2D": {"inherits": "Node", "methods": {"move_and_slide": [0, 0]},
                                "properties": ["velocity"], "signals": []},
        }, godot_version="4.6.3")
        self.base = ["--root", self.root, "--udd", self.store, "--no-builtin-cache"]
        import history_manager
        previous_storage = history_manager._STORAGE_OVERRIDE
        self.addCleanup(setattr, history_manager, "_STORAGE_OVERRIDE", previous_storage)

    def request_file(self, payload, name="request.json"):
        path = Path(self.store, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return str(path)

    @staticmethod
    def plan_id(output):
        match = re.search(r"^plan_id: ([0-9a-f]{24})$", output, re.MULTILINE)
        return match.group(1) if match else ""

    @staticmethod
    def entry_id(output):
        match = re.search(r"^entry_id: ([0-9a-f]{12})$", output, re.MULTILINE)
        return match.group(1) if match else ""

    # --- api ---------------------------------------------------------------

    def test_api_known_class_exit0_with_inherited(self):
        rc, out, err = run_bridge(self.base + ["api", "CharacterBody2D"])
        self.assertEqual(rc, 0, err)
        self.assertIn("move_and_slide", out)
        self.assertIn("add_child", out)  # унаследовано от Node
        self.assertIn("velocity", out)
        self.assertIn("bridge: ok", err)

    def test_api_unknown_class_exit2_not_error(self):
        rc, out, err = run_bridge(self.base + ["api", "NoSuchClass123"])
        self.assertEqual(rc, 2, err)
        self.assertIn("not-found", err)
        self.assertNotIn("Traceback", out + err)

    def test_api_without_any_cache_exit3(self):
        empty = tempfile.TemporaryDirectory(prefix="bridge_nocache_")
        self.addCleanup(empty.cleanup)
        Path(empty.name, "project.godot").write_text("config_version=5\n", encoding="utf-8")
        rc, out, err = run_bridge(["--root", empty.name, "--no-builtin-cache", "api", "Node"])
        self.assertEqual(rc, 3, err)
        self.assertIn("error", err)
        self.assertNotIn("Traceback", out + err)

    # --- engine ------------------------------------------------------------

    def test_engine_reports_cached_version(self):
        rc, out, err = run_bridge(self.base + ["engine"])
        self.assertEqual(rc, 0, err)
        self.assertIn("4.6.3", out)

    # --- search ------------------------------------------------------------

    def test_search_found_exit0(self):
        rc, out, err = run_bridge(self.base + ["search", "take_damage"])
        self.assertEqual(rc, 0, err)
        self.assertIn("player.gd", out)

    def test_search_nothing_exit2(self):
        rc, out, err = run_bridge(self.base + ["search", "zzz_no_such_identifier_zzz"])
        self.assertEqual(rc, 2, err)
        self.assertNotIn("Traceback", out + err)

    def test_search_missing_max_is_usage(self):
        rc, out, err = run_bridge(self.base + ["search", "--max"])
        self.assertEqual(rc, 4, err)
        self.assertIn("bridge: usage:", err)
        self.assertNotIn("Traceback", out + err)

    def test_search_non_numeric_max_is_usage(self):
        rc, out, err = run_bridge(self.base + ["search", "--max", "abc", "query"])
        self.assertEqual(rc, 4, err)
        self.assertIn("bridge: usage:", err)
        self.assertNotIn("Traceback", out + err)

    def test_search_zero_max_is_usage(self):
        rc, out, err = run_bridge(self.base + ["search", "--max", "0", "query"])
        self.assertEqual(rc, 4, err)
        self.assertIn("bridge: usage:", err)
        self.assertNotIn("Traceback", out + err)

    def test_search_negative_max_is_usage(self):
        rc, out, err = run_bridge(self.base + ["search", "--max", "-1", "query"])
        self.assertEqual(rc, 4, err)
        self.assertIn("bridge: usage:", err)
        self.assertNotIn("Traceback", out + err)

    def test_search_max_without_query_is_usage(self):
        rc, out, err = run_bridge(self.base + ["search", "--max", "10"])
        self.assertEqual(rc, 4, err)
        self.assertIn("bridge: usage:", err)
        self.assertNotIn("Traceback", out + err)

    def test_search_valid_max_still_works(self):
        for index in range(12):
            Path(self.root, "src", "match_%02d.gd" % index).write_text(
                "var bridge_limited_match = %d\n" % index, encoding="utf-8")

        rc, out, err = run_bridge(
            self.base + ["search", "--max", "10", "bridge_limited_match"])

        self.assertEqual(rc, 0, err)
        self.assertIn("bridge: ok", err)
        self.assertIn("10 match groups", err)
        self.assertEqual(out.count("\n---\n"), 10)
        self.assertIn("results truncated at 10", out)
        self.assertNotIn("Traceback", out + err)

    # --- ask (библиотекарь) -------------------------------------------------

    def test_ask_exit0_librarian_answer(self):
        rc, out, err = run_bridge(self.base + ["ask", "player damage"])
        self.assertEqual(rc, 0, err)
        self.assertIn("[Librarian]", out)
        self.assertNotIn("Traceback", out + err)

    def test_ask_footer_is_bridge_not_server(self):
        # Хвост Библиотекаря советует серверные read_function/patch_file —
        # через мост их нет; мост обязан подменить подсказку на свою.
        rc, out, err = run_bridge(self.base + ["ask", "player damage"])
        self.assertEqual(rc, 0, err)
        self.assertIn("Next (bridge):", out)
        self.assertNotIn("read_function", out)

    def test_ask_preserves_source_and_only_writes_agent_history(self):
        root = Path(self.root)
        before = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()
        }

        rc, out, err = run_bridge(self.base + ["ask", "player damage"])
        self.assertEqual(rc, 0, err)
        self.assertIn("[Librarian]", out)

        after = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()
        }
        is_history = lambda rel: rel == ".agent_history" or rel.startswith(".agent_history/")
        source_before = {rel: data for rel, data in before.items() if not is_history(rel)}
        source_after = {rel: data for rel, data in after.items() if not is_history(rel)}
        self.assertEqual(source_after, source_before,
                         "ask изменил исходные файлы или дерево проекта")
        new_outside_history = sorted(
            rel for rel in set(after) - set(before) if not is_history(rel))
        self.assertEqual(new_outside_history, [],
                         "ask создал файл вне разрешённого .agent_history")

    def test_ask_nothing_relevant_exit2_not_error(self):
        # «По запросу ничего не нашлось» — это ОТВЕТ (rc 2), а не успех
        # (иначе модель решит, что данные получены) и не сбой (rc 3).
        rc, out, err = run_bridge(self.base + ["ask", "zzqxx_no_such_thing_zz"])
        self.assertEqual(rc, 2, err)
        self.assertIn("not-found", err)
        self.assertNotIn("Traceback", out + err)

    # --- полные сигнатуры методов в `api` (кэш нового формата) ---

    def test_api_full_signatures_when_cache_has_them(self):
        # Внешней модели нужны ИМЕНА/типы аргументов и дефолты, а не только
        # «0..0»: без сигнатур она галлюцинирует параметры.
        gd_api_cache.save_cache(self.root, _SIG_CLASSES, godot_version="4.6.3")
        rc, out, err = run_bridge(self.base + ["api", "CharacterBody2D"])
        self.assertEqual(rc, 0, err)
        self.assertIn("move_and_slide() -> bool", out)
        self.assertIn("take_hit(amount: int, crit: bool = false) -> void", out)
        # унаследованный метод тоже печатается с сигнатурой
        self.assertIn("get_collision_layer() -> int", out)
        self.assertNotIn("take_hit(1..2)", out)

    def test_api_arity_only_cache_keeps_working(self):
        # Старый кэш (без signatures) — поведение прежнее, ничего не ломаем.
        classes = {
            "Object": {"inherits": "", "methods": {"free": [0, 0]}, "properties": [], "signals": []},
            "PhysicsBody2D": {"inherits": "Object", "methods": {"get_collision_layer": [0, 0]},
                              "properties": [], "signals": []},
            "CharacterBody2D": {"inherits": "PhysicsBody2D",
                                "methods": {"move_and_slide": [0, 0], "take_hit": [1, 2]},
                                "properties": ["velocity"], "signals": []},
        }
        gd_api_cache.save_cache(self.root, classes, godot_version="4.6.3")
        rc, out, err = run_bridge(self.base + ["api", "CharacterBody2D"])
        self.assertEqual(rc, 0, err)
        self.assertIn("move_and_slide()", out)
        self.assertIn("take_hit(1..2)", out)
        self.assertNotIn("amount: int", out)  # принтер не выдумывает сигнатуры

    # --- access modes -------------------------------------------------------

    def access_base(self, mode):
        return self.base + ["--access", mode]

    def test_project_mode_hides_all_addons(self):
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            for token in ("ADDON_ONLY_TOKEN", "AGENT_ONLY_TOKEN"):
                rc, out, err = run_bridge(
                    self.access_base("project") + ["search", token])
                self.assertEqual(rc, 2, err)
                self.assertIn("access=project", out)

    def test_addon_mode_reads_external_addon_but_not_current_agent(self):
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(
                self.access_base("addon") + ["search", "ADDON_ONLY_TOKEN"])
            self.assertEqual(rc, 0, err)
            self.assertIn("addons/demo/tool.gd", out)
            rc, out, err = run_bridge(
                self.access_base("addon") + ["search", "AGENT_ONLY_TOKEN"])
            self.assertEqual(rc, 2, err)

    def test_agent_dev_mode_reads_current_agent(self):
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(
                self.access_base("agent-dev") + ["read",
                "res://addons/Godot_agent/godot_agent/agent.gd"])
            self.assertEqual(rc, 0, err)
            self.assertIn("AGENT_ONLY_TOKEN", out)
            self.assertIn("access: agent-dev", out)

    def test_access_mode_never_accepts_client_addon_dir(self):
        rc, out, err = run_bridge(self.base + [
            "--access", "agent-dev", "read", "res://addons/demo/tool.gd"])
        # The temp project has no discoverable source installation, so agent-dev
        # fails closed instead of trusting any model-provided path.
        self.assertEqual(rc, 2, err)
        self.assertNotIn("internal failure", out)
        rc, out, err = run_bridge(self.base + [
            "--addon-dir", str(self.agent_dir), "--access", "agent-dev",
            "read", "res://addons/demo/tool.gd"])
        self.assertEqual(rc, 4, err)
        self.assertIn("unknown option --addon-dir", out + err)

    # --- read ---------------------------------------------------------------

    def test_read_is_policy_aware_and_bounded(self):
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(
                self.access_base("addon") + ["read", "--max-chars", "5",
                "res://addons/demo/tool.gd"])
            self.assertEqual(rc, 0, err)
            self.assertIn("truncated: true", out)
            rc, out, err = run_bridge(
                self.access_base("addon") + ["read",
                "res://addons/Godot_agent/godot_agent/agent.gd"])
            self.assertEqual(rc, 2, err)

    # --- paths preview ------------------------------------------------------

    def test_paths_preview_exit0_counts_references(self):
        rc, out, err = run_bridge(self.base + ["paths", "preview",
                                               "res://src/player.gd", "res://src/hero.gd"])
        self.assertEqual(rc, 0, err)
        self.assertIn("reference_count", out)
        self.assertIn("main.gd", out)
        # preview не должен ничего переименовывать
        self.assertTrue(Path(self.root, "src", "player.gd").exists())
        self.assertFalse(Path(self.root, "src", "hero.gd").exists())

    def test_paths_preview_missing_source_exit2(self):
        rc, out, err = run_bridge(self.base + ["paths", "preview",
                                               "res://src/ghost.gd", "res://src/x.gd"])
        self.assertEqual(rc, 2, err)
        self.assertNotIn("Traceback", out + err)

    # --- write alpha --------------------------------------------------------

    def run_bridge_in(self, cwd, argv):
        """Запуск CLI из указанной рабочей директории (cwd влияет на план)."""
        out, err = io.StringIO(), io.StringIO()
        previous = os.getcwd()
        try:
            os.chdir(cwd)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = agent_bridge.main(list(argv))
        finally:
            os.chdir(previous)
        return rc, out.getvalue(), err.getvalue()

    def test_plan_id_does_not_depend_on_working_directory(self):
        """Одинаковый запрос из разных cwd обязан давать одинаковый plan_id.

        Раньше `os.path.realpath(addon_dir or "")` возвращал текущий каталог,
        поэтому в режиме `--access project` (addon_dir=None) plan_id «плавал»
        вместе с cwd.
        """
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"}, "cwd.json")
        dir_a = Path(self.root, "workdir_a")
        dir_b = Path(self.root, "workdir_b")
        dir_a.mkdir()
        dir_b.mkdir()
        rc_a, out_a, err_a = self.run_bridge_in(str(dir_a), self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc_a, 0, err_a)
        rc_b, out_b, err_b = self.run_bridge_in(str(dir_b), self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc_b, 0, err_b)
        plan_a, plan_b = self.plan_id(out_a), self.plan_id(out_b)
        self.assertRegex(plan_a, r"^[0-9a-f]{24}$")
        self.assertEqual(plan_a, plan_b,
                         "plan_id зависит от cwd: %s != %s" % (plan_a, plan_b))

    def test_preview_and_apply_work_across_working_directories(self):
        """preview из A + apply из B с тем же plan_id должен работать."""
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"}, "cross.json")
        dir_a = Path(self.root, "workdir_a")
        dir_b = Path(self.root, "workdir_b")
        dir_a.mkdir()
        dir_b.mkdir()
        rc, out, err = self.run_bridge_in(str(dir_a), self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)
        plan_id = self.plan_id(out)
        rc, out, err = self.run_bridge_in(str(dir_b), self.access_base("project") + [
            "--validation", "off", "write", "apply", "--request", request,
            "--plan-id", plan_id])
        self.assertEqual(rc, 0, "apply из другого cwd отклонён: %s" % (out + err))
        self.assertNotIn("stale plan", out + err)
        self.assertIn("var hp = 90", Path(self.root, "src", "player.gd").read_text())

    def test_plan_stays_single_use_across_working_directories(self):
        """Одноразовость плана не должна ослабнуть после снятия зависимости от cwd."""
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"}, "single.json")
        dir_a = Path(self.root, "workdir_a")
        dir_b = Path(self.root, "workdir_b")
        dir_a.mkdir()
        dir_b.mkdir()
        rc, out, err = self.run_bridge_in(str(dir_a), self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)
        plan_id = self.plan_id(out)
        rc, out, err = self.run_bridge_in(str(dir_b), self.access_base("project") + [
            "--validation", "off", "write", "apply", "--request", request,
            "--plan-id", plan_id])
        self.assertEqual(rc, 0, err)
        rc, out, err = self.run_bridge_in(str(dir_b), self.access_base("project") + [
            "--validation", "off", "write", "apply", "--request", request,
            "--plan-id", plan_id])
        self.assertNotEqual(rc, 0, "план перестал быть одноразовым")
        self.assertEqual(rc, 3, err)

    def test_plan_id_distinguishes_really_different_policies(self):
        """Нормализация не должна склеивать РАЗНЫЕ режимы доступа."""
        project_plan = None
        addon_plan = None
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"}, "distinguish.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)
        project_plan = self.plan_id(out)
        addon_request = self.request_file({"action": "patch_file",
            "path": "res://addons/demo/tool.gd", "search": "ADDON_ONLY_TOKEN",
            "replace": "ADDON_PATCHED"}, "addon_distinguish.json")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(self.access_base("addon") + [
                "--validation", "off", "write", "preview", "--request", addon_request])
        self.assertEqual(rc, 0, err)
        addon_plan = self.plan_id(out)
        self.assertNotEqual(project_plan, addon_plan)

    # --- этап 5: коды возврата и режимы доступа --------------------------

    def test_missing_plan_receipt_is_infrastructure_error_not_not_found(self):
        """Квитанцию плана создаёт сам мост: её отсутствие — сбой (3), а не 2."""
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"}, "infra_plan.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "apply", "--request", request,
            "--plan-id", "0" * 24])
        self.assertEqual(rc, 3, "отсутствие квитанции — сбой моста: %s" % err)
        self.assertIn("already applied", out)

    def test_missing_journal_entry_is_infrastructure_error(self):
        """Журнал ведёт мост: отсутствующей записи соответствует код 3."""
        rc, out, err = run_bridge(self.access_base("project") + [
            "write", "rollback", "--entry-id", "ffffffffffff"])
        self.assertEqual(rc, 3, err)
        self.assertNotEqual(rc, 2, "нельзя выдавать сбой журнала за not-found")

    def test_usage_errors_return_code_4(self):
        """Ошибки разбора опций и запроса — usage (4), а не not-found (2)."""
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"}, "usage.json")
        cases = [
            ["write", "preview"],
            ["write", "apply", "--request", request, "--plan-id", "ZZZ"],
            ["context"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                rc, out, err = run_bridge(self.access_base("project") + argv)
                self.assertEqual(rc, 4, "%s -> %s" % (argv, err))
                self.assertIn("usage", err)

    def test_broken_request_file_is_usage_error(self):
        bad = Path(self.store, "not_json.json")
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("{not json", encoding="utf-8")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", str(bad)])
        self.assertEqual(rc, 4, err)
        self.assertIn("not valid JSON", out)

    def test_duplicate_max_in_search_is_usage_error(self):
        rc, out, err = run_bridge(self.access_base("project") + [
            "search", "--max", "5", "--max", "9", "hp"])
        self.assertEqual(rc, 4, err)
        self.assertIn("duplicate option", err)

    def test_single_max_in_search_still_works(self):
        rc, out, err = run_bridge(self.access_base("project") + [
            "search", "--max", "5", "hp"])
        self.assertEqual(rc, 0, err)
        rc, out, err = run_bridge(self.access_base("project") + ["search", "hp"])
        self.assertEqual(rc, 0, err)

    def test_addon_mode_degradation_is_reported(self):
        """Молчаливая деградация addon->project запрещена: нужен warning."""
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=None):
            rc, out, err = run_bridge(self.access_base("addon") + [
                "search", "hp"])
        self.assertEqual(rc, 0, err)
        self.assertIn("degraded", out + err)
        self.assertIn("add-on", (out + err).lower())

    def test_addon_mode_has_no_warning_when_root_found(self):
        """При найденном доверенном корне деградации нет и warning'а нет."""
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(self.access_base("addon") + [
                "search", "ADDON_ONLY_TOKEN"])
        self.assertEqual(rc, 0, err)
        self.assertNotIn("degraded", out + err)

    def test_headless_only_extensions_are_checked_only_if_godot_ran(self):
        """`.tres`/`.gdshader`/`.shader` проверяет только настоящий Godot.

        При `--validation auto` без движка не выполняется НИ ОДНОЙ проверки,
        поэтому `checked` обязан быть false. Раньше он считался по
        принадлежности расширения к списку и давал ложное «clean».
        """
        root = Path(self.root)
        (root / "material.tres").write_text(
            '[gd_resource type="StandardMaterial3D"]\n', encoding="utf-8")
        (root / "effect.gdshader").write_text(
            "shader_type canvas_item;\nvoid fragment() {}\n", encoding="utf-8")
        (root / "sky.shader").write_text(
            "shader_type sky;\nvoid sky() {}\n", encoding="utf-8")
        for name in ("res://material.tres", "res://effect.gdshader",
                     "res://sky.shader"):
            with self.subTest(path=name):
                rc, out, err = run_bridge(self.access_base("project") + [
                    "--godot", str(root / "no_godot.exe"),
                    "--validation", "auto", "check", name])
                self.assertNotEqual(rc, 0,
                                    "%s не проверялся, но мост сказал 'clean': %s"
                                    % (name, out))
                self.assertIn("checked: false", out)
                self.assertIn("check_skipped:", out)
                self.assertIn("НЕ проверен", out)
                self.assertNotIn("files clean", err)

    def test_headless_only_extensions_pass_when_godot_actually_ran(self):
        """С настоящим Godot эти расширения проверяются — checked: true."""
        checked_statuses = {"passed": True, "failed": True,
                            "skipped": False, "unavailable": False,
                            "inconclusive": False}
        for status, expected in checked_statuses.items():
            with self.subTest(status=status):
                target = Path(self.root, "material.tres")
                target.write_text('[gd_resource type="StandardMaterial3D"]\n',
                                  encoding="utf-8")
                report = {"status": status, "mode": "auto", "blocking": False,
                          "new_diagnostics": [], "pre_existing_diagnostics": []}
                with patch.object(agent_bridge, "_plan_dir"), \
                     patch("godot_headless_validation.validate_batch",
                           return_value={"schema_version": 1,
                                         "candidate_digest": "x",
                                         "source_hashes": {},
                                         "report": report}):
                    rc, out, err = run_bridge(self.access_base("project") + [
                        "--validation", "auto", "check", "res://material.tres"])
                self.assertIn("headless: %s" % status, out)
                if expected:
                    self.assertIn("checked: true", out)
                else:
                    self.assertIn("checked: false", out)

    def test_protected_agent_parts_check_lives_in_exactly_one_function(self):
        """Фильтр защищённых путей должен быть ровно в одном месте кода.

        Дубль в `_validate_bridge_candidate` был безвреден только пока общий
        фильтр вызывался следом: он считал relpath без канонизации и не видел
        симлинк. При перестановке вызовов такой мёртвый код стал бы единственным.
        """
        import ast
        source = Path(agent_bridge.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        holders = []
        # `path[6:]` ищется в АСТ, а не в исходнике: docstring функции честно
        # цитирует эту небезопасную склейку, объясняя, почему её удалили.
        unsafe_slices = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if any(isinstance(child, ast.Name)
                       and child.id == "PROTECTED_AGENT_PARTS"
                       for child in ast.walk(node)):
                    holders.append(node.name)
            if isinstance(node, ast.Subscript):
                value = node.value
                if (isinstance(value, ast.Name) and value.id == "path"
                        and isinstance(node.slice, ast.Slice)
                        and isinstance(node.slice.lower, ast.Constant)
                        and node.slice.lower.value == 6):
                    unsafe_slices.append(getattr(node, "lineno", "?"))
        self.assertEqual(holders, ["_assert_agent_path_writable"],
                         "PROTECTED_AGENT_PARTS используется вне единственного "
                         "фильтра: %s" % holders)
        self.assertEqual(unsafe_slices, [],
                         "осталась ручная склейка пути вместо канонизации "
                         "в строках %s" % unsafe_slices)

    def test_protected_agent_dir_still_blocked_after_duplicate_removal(self):
        """После удаления дубля транзакция в dist/ всё ещё отклоняется."""
        dist = self.agent_dir / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        request = self.request_file({"action": "create_file",
            "path": "res://addons/Godot_agent/godot_agent/dist/new.gd",
            "content": "extends Node\n"}, "dup_removed.json")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(self.access_base("agent-dev") + [
                "--validation", "off", "write", "preview", "--request", request])
        self.assertNotEqual(rc, 0, "защита ослабла после удаления дубля: %s" % out)
        self.assertIn("generated/frozen", out)
        self.assertFalse((dist / "new.gd").exists())

    def test_repair_scene_cannot_write_into_protected_agent_dir(self):
        """Фильтр PROTECTED_AGENT_PARTS обязан покрывать и repair_scene."""
        dist = self.agent_dir / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "scene.tscn").write_text('[gd_scene load_steps=9 format=3]\n\n'
            '[node name="Root" type="Node"]\n'
            'material = SubResource("1_mat")\n[/node]\n\n'
            '[sub_resource type="StandardMaterial3D" id="1_mat"]\n'
            'albedo_color = Color(1, 0, 0, 1)\n', encoding="utf-8")
        request = self.request_file({"action": "repair_scene",
            "path": "res://addons/Godot_agent/godot_agent/dist/scene.tscn"},
            "protected_scene.json")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(self.access_base("agent-dev") + [
                "--validation", "off", "write", "preview", "--request", request])
        self.assertNotEqual(rc, 0, "repair_scene прошёл в защищённый dist/: %s" % out)
        self.assertIn("generated/frozen", out)

    def test_rename_symbol_cannot_write_into_protected_agent_dir(self):
        """Тот же фильтр обязан покрывать и rename_symbol."""
        dist = self.agent_dir / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "gen.gd").write_text(
            "extends Node\nfunc generated():\n\tpass\n", encoding="utf-8")
        request = self.request_file({"action": "rename_symbol", "kind": "function",
            "declaration": "res://addons/Godot_agent/godot_agent/dist/gen.gd:2:1",
            "old_name": "generated", "new_name": "renamed"}, "protected_rename.json")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(self.access_base("agent-dev") + [
                "--validation", "off", "write", "preview", "--request", request])
        self.assertNotEqual(rc, 0, "rename_symbol прошёл в защищённый dist/: %s" % out)
        self.assertIn("generated/frozen", out)

    # --- этап 6: уборка квитанций планов ----------------------------------

    def plan_dir(self):
        return Path(agent_bridge._plan_dir(self.root, {"udd": self.store}))

    def write_receipt(self, plan_id, created, name=None):
        folder = self.plan_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name or (plan_id + ".json"))
        path.write_text(json.dumps({
            "schema": 1, "plan_id": plan_id, "created": created,
            "mode": "project", "paths": []}), encoding="utf-8")
        return path

    def test_expired_receipt_is_pruned_on_next_preview(self):
        """Просроченная квитанция не должна копиться в каталоге."""
        old = time.time() - (agent_bridge.PLAN_TTL_SECONDS + 600)
        expired = self.write_receipt("a" * 24, old)
        fresh = self.write_receipt("b" * 24, time.time())
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"}, "prune.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)
        self.assertFalse(expired.exists(), "просроченная квитанция не удалена")
        self.assertTrue(fresh.exists(), "свежая квитанция не должна удаляться")

    def test_active_apply_receipt_of_current_process_is_never_pruned(self):
        """`.applying-<pid>` текущего процесса — это наш ЖИВОЙ apply."""
        import os as _os
        mine = self.write_receipt(
            "c" * 24, time.time(),
            name="c" * 24 + ".json.applying-%d" % _os.getpid())
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"}, "prune2.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)
        self.assertTrue(mine.exists(),
                        "уборка удалила квитанцию АКТИВНОГО apply текущего процесса")

    def test_orphaned_apply_receipt_is_pruned(self):
        """`.applying-<мёртвый pid>` — останется падения, его убираем."""
        orphan = self.write_receipt(
            "d" * 24, time.time(), name="d" * 24 + ".json.applying-999999")
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"}, "prune3.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)
        self.assertFalse(orphan.exists(), "осиротевшая квитанция не удалена")

    def test_prune_is_safe_without_plan_directory(self):
        """Уборка не должна бросать исключений, если каталога ещё нет."""
        import shutil
        shutil.rmtree(self.plan_dir(), ignore_errors=True)
        self.assertEqual(
            agent_bridge._prune_plan_receipts(self.root, {"udd": self.store}), 0)
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"}, "prune4.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)

    def test_live_process_receipt_older_than_ttl_is_not_pruned(self):
        """Живой apply с квитанцией СТАРШЕ TTL всё равно не трогаем.

        Раньше условие было `not alive or age > TTL`, из-за чего файл
        удалялся у живого процесса — вопреки собственному docstring.
        """
        holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            path = self.write_receipt(
                "7" * 24, time.time(),
                name="7" * 24 + ".json.applying-%d" % holder.pid)
            old = time.time() - (agent_bridge.PLAN_TTL_SECONDS * 4)
            os.utime(path, (old, old))   # делаем файл сильно старше TTL
            removed = agent_bridge._prune_plan_receipts(
                self.root, {"udd": self.store})
            self.assertEqual(removed, 0, "квитанция ЖИВОГО apply удалена по TTL")
            self.assertTrue(path.exists(),
                            "маркер живого apply не должен удаляться по возрасту")
        finally:
            holder.terminate()
            holder.wait(timeout=10)

    def test_prune_keeps_receipt_when_process_state_is_ambiguous(self):
        """Нет доступа к процессу ≠ процесс мёртв: файл трогать нельзя.

        `OpenProcess` может не открыться и потому, что PID не существует
        (тогда чистить можно), и потому, что процесс жив, но прав нет
        (тогда нельзя). Неоднозначность обязана трактоваться как «жив».
        """
        self.assertFalse(agent_bridge._windows_process_alive(999999),
                         "несуществующий PID должен считаться мёртвым")
        self.assertTrue(agent_bridge._windows_process_alive(os.getpid()),
                        "текущий процесс обязан считаться живым")
        for pid in (0, -1, -12345):
            self.assertFalse(agent_bridge._windows_process_alive(pid))

    def test_prune_keeps_receipt_created_by_a_live_foreign_process(self):
        """Живой чужой apply нельзя считать мусором только из-за возраста файла."""
        holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            path = self.write_receipt(
                "e" * 24, time.time(),
                name="e" * 24 + ".json.applying-%d" % holder.pid)
            removed = agent_bridge._prune_plan_receipts(
                self.root, {"udd": self.store})
            self.assertEqual(removed, 0, "квитанция ЖИВОГО процесса удалена")
            self.assertTrue(path.exists())
        finally:
            holder.terminate()
            holder.wait(timeout=10)

    def test_write_preview_apply_is_single_use_and_rollbackable(self):
        request = self.request_file({"action": "patch_file",
            "path": "res://addons/demo/tool.gd", "search": "ADDON_ONLY_TOKEN",
            "replace": "ADDON_PATCHED_TOKEN"})
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(self.access_base("addon") + [
                "--validation", "off", "write", "preview", "--request", request])
            self.assertEqual(rc, 0, err)
            plan_id = self.plan_id(out)
            self.assertRegex(plan_id, r"^[0-9a-f]{24}$")
            self.assertIn("ADDON_ONLY_TOKEN", (self.external_addon / "tool.gd").read_text())

            rc, out, err = run_bridge(self.access_base("addon") + [
                "--validation", "off", "write", "apply", "--request", request,
                "--plan-id", plan_id])
            self.assertEqual(rc, 0, err)
            entry_id = self.entry_id(out)
            self.assertRegex(entry_id, r"^[0-9a-f]{12}$")
            self.assertIn("ADDON_PATCHED_TOKEN",
                          (self.external_addon / "tool.gd").read_text())

            rc, out, err = run_bridge(self.access_base("addon") + [
                "--validation", "off", "write", "apply", "--request", request,
                "--plan-id", plan_id])
            # Квитанция одноразовая и её создаёт сам мост: её отсутствие —
            # сбой состояния моста (3), а не «объекта не существует» (2).
            self.assertEqual(rc, 3, err)
            self.assertIn("already applied", out)

            rc, out, err = run_bridge(self.access_base("addon") + [
                "write", "rollback", "--entry-id", entry_id])
            self.assertEqual(rc, 0, err)
            self.assertIn("ADDON_ONLY_TOKEN",
                          (self.external_addon / "tool.gd").read_text())

    def test_project_mode_write_and_rollback(self):
        request = self.request_file({"action": "patch_file",
            "path": "res://src/player.gd", "search": "var hp = 100",
            "replace": "var hp = 90"})
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)
        plan_id = self.plan_id(out)
        self.assertIn("var hp = 100", Path(self.root, "src", "player.gd").read_text())
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "apply", "--request", request,
            "--plan-id", plan_id])
        self.assertEqual(rc, 0, err)
        entry_id = self.entry_id(out)
        self.assertIn("var hp = 90", Path(self.root, "src", "player.gd").read_text())
        rc, out, err = run_bridge(self.access_base("project") + [
            "write", "rollback", "--entry-id", entry_id])
        self.assertEqual(rc, 0, err)
        self.assertIn("var hp = 100", Path(self.root, "src", "player.gd").read_text())

    def test_write_modes_enforce_project_addon_agent_boundaries(self):
        addon_request = self.request_file({"action": "patch_file",
            "path": "res://addons/demo/tool.gd", "search": "ADDON_ONLY_TOKEN",
            "replace": "ADDON_CHANGED"}, "addon.json")
        agent_request = self.request_file({"action": "patch_file",
            "path": "res://addons/Godot_agent/godot_agent/agent.gd",
            "search": "AGENT_ONLY_TOKEN", "replace": "AGENT_CHANGED"}, "agent.json")
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(self.access_base("project") + [
                "--validation", "off", "write", "preview", "--request", addon_request])
            self.assertEqual(rc, 2, err)
            rc, out, err = run_bridge(self.access_base("addon") + [
                "--validation", "off", "write", "preview", "--request", agent_request])
            self.assertEqual(rc, 2, err)
            rc, out, err = run_bridge(self.access_base("agent-dev") + [
                "--validation", "off", "write", "preview", "--request", agent_request])
            self.assertEqual(rc, 0, err)
            plan_id = self.plan_id(out)
            rc, out, err = run_bridge(self.access_base("agent-dev") + [
                "--validation", "off", "write", "apply", "--request", agent_request,
                "--plan-id", plan_id])
            self.assertEqual(rc, 0, err)
            self.assertIn("AGENT_CHANGED", (self.agent_dir / "agent.gd").read_text())

    def test_write_move_file_updates_all_references_and_rolls_back(self):
        project_file = Path(self.root, "project.godot")
        project_file.write_text(
            'config_version=5\n\n[autoload]\nPlayer="*res://src/player.gd"\n',
            encoding="utf-8")
        player = Path(self.root, "src", "player.gd")
        player.write_text("extends Node\nclass_name Player\n", encoding="utf-8")
        Path(str(player) + ".uid").write_text("uid://bridgeplayer\n", encoding="utf-8")
        consumer = Path(self.root, "src", "main.gd")
        consumer.write_text(
            'extends Node\nconst P = preload("res://src/player.gd")\n',
            encoding="utf-8")
        request = self.request_file({"action": "move_file",
            "path": "res://src/player.gd",
            "dest": "res://actors/hero.gd"})
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)
        self.assertIn("reference_count: 2", out)
        self.assertIn("res://src/player.gd", consumer.read_text())
        plan_id = self.plan_id(out)

        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "apply", "--request", request,
            "--plan-id", plan_id])
        self.assertEqual(rc, 0, err)
        entry_id = self.entry_id(out)
        self.assertIn("reference_count: 2", out)
        self.assertFalse(player.exists())
        moved = Path(self.root, "actors", "hero.gd")
        self.assertTrue(moved.exists())
        self.assertEqual(Path(str(moved) + ".uid").read_text(), "uid://bridgeplayer\n")
        self.assertIn('preload("res://actors/hero.gd")', consumer.read_text())
        self.assertIn('Player="*res://actors/hero.gd"', project_file.read_text())

        rc, out, err = run_bridge(self.access_base("project") + [
            "write", "rollback", "--entry-id", entry_id])
        self.assertEqual(rc, 0, err)
        self.assertTrue(player.exists())
        self.assertFalse(moved.exists())
        self.assertIn('preload("res://src/player.gd")', consumer.read_text())
        self.assertIn('Player="*res://src/player.gd"', project_file.read_text())

    def test_write_transaction_with_move_is_refused(self):
        request = self.request_file({"action": "transaction", "operations": [
            {"action": "create_file", "path": "res://src/new.gd",
             "content": "extends Node\n"},
            {"action": "move_file", "path": "res://src/player.gd",
             "dest": "res://src/hero.gd"}]}, "mixed_move.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 2, err)
        self.assertIn("отдельный move_file", out)
        self.assertFalse(Path(self.root, "src", "new.gd").exists())

    def test_write_apply_rejects_source_change(self):
        request = self.request_file({"action": "patch_file",
            "path": "res://addons/demo/tool.gd", "search": "ADDON_ONLY_TOKEN",
            "replace": "ADDON_CHANGED"})
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            rc, out, err = run_bridge(self.access_base("addon") + [
                "--validation", "off", "write", "preview", "--request", request])
            plan_id = self.plan_id(out)
            target = self.external_addon / "tool.gd"
            target.write_text(target.read_text() + "# external edit\n")
            rc, out, err = run_bridge(self.access_base("addon") + [
                "--validation", "off", "write", "apply", "--request", request,
                "--plan-id", plan_id])
            self.assertEqual(rc, 2, err)
            self.assertNotIn("ADDON_CHANGED", target.read_text())

    def test_write_rejects_invalid_text_and_protected_agent_paths(self):
        cases = [
            ({"action": "create_file", "path": "res://bad.py",
              "content": "def broken(:\n"}, "python"),
            ({"action": "create_file", "path": "res://bad.json",
              "content": "{broken\n"}, "json"),
            ({"action": "create_file", "path": "res://bad.cfg",
              "content": "[x]\na=1\na=2\n"}, "cfg"),
        ]
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent_dir)):
            for payload, name in cases:
                request = self.request_file(payload, name + ".json")
                rc, out, err = run_bridge(self.access_base("addon") + [
                    "--validation", "off", "write", "preview", "--request", request])
                self.assertEqual(rc, 2, err)
                self.assertIn("syntax validation", out)
            protected = self.request_file({"action": "create_file",
                "path": "res://addons/Godot_agent/godot_agent/python/dist/x.py",
                "content": "x = 1\n"}, "protected.json")
            rc, out, err = run_bridge(self.access_base("agent-dev") + [
                "--validation", "off", "write", "preview", "--request", protected])
            self.assertEqual(rc, 2, err)
            self.assertIn("generated/frozen", out)

    def test_write_request_rejects_duplicates_and_structural_paths(self):
        duplicate = Path(self.store, "duplicate.json")
        duplicate.parent.mkdir(parents=True, exist_ok=True)
        duplicate.write_text('{"action":"create_file","action":"patch_file",'
                             '"path":"res://x.py","content":"x=1\\n"}', encoding="utf-8")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", str(duplicate)])
        # Некорректный формат запроса — это ошибка ВЫЗОВА (4), а не
        # «запрошенного не существует» (2): модель должна исправить файл.
        self.assertEqual(rc, 4, err)
        self.assertIn("duplicate JSON key", out)
        for index, path in enumerate(("res://project.godot", "res://scene.tscn")):
            request = self.request_file({"action": "create_file", "path": path,
                                         "content": "unsafe\n"}, "protected%d.json" % index)
            rc, out, err = run_bridge(self.access_base("project") + [
                "--validation", "off", "write", "preview", "--request", request])
            self.assertEqual(rc, 2, err)

    # --- autonomous deterministic tools -------------------------------------

    def test_context_command_collects_local_evidence(self):
        request = self.request_file({"query": "player damage", "symbols": [],
            "editor": False, "active_scene": False, "diagnostics": True,
            "max_chars": 8000}, "context.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "context", "--request", request])
        self.assertEqual(rc, 0, err)
        self.assertIn("PROJECT REFERENCE", out)
        self.assertIn("take_damage", out)

    def test_check_reports_local_problems_and_scene_autofix(self):
        broken = Path(self.root, "src", "broken.gd")
        broken.write_text("extends Node\nfunc broken(\n", encoding="utf-8")
        scene = Path(self.root, "broken.tscn")
        scene.write_text('[gd_scene load_steps=9 format=3]\n\n'
            '[node name="Root" type="Node"]\n'
            'material = SubResource("1_mat")\n'
            '[/node]\n\n'
            '[sub_resource type="StandardMaterial3D" id="1_mat"]\n'
            'albedo_color = Color(1, 0, 0, 1)\n', encoding="utf-8")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "check",
            "res://src/broken.gd", "res://broken.tscn"])
        self.assertEqual(rc, 2, err)
        self.assertIn("path: res://src/broken.gd", out)
        self.assertIn("path: res://broken.tscn", out)
        self.assertIn("auto_fixable: true", out)

    def test_check_required_validation_without_godot_never_reports_clean(self):
        """--validation required без настоящего Godot — не «clean», а отказ.

        Раньше blocking-статус headless-проверки терялся, и мост рапортовал
        «1 files clean» там, где write apply отказывался применять кандидата.
        """
        good = Path(self.root, "src", "good.gd")
        good.write_text("extends Node\n\nfunc _ready() -> void:\n\tprint(1)\n",
                        encoding="utf-8")
        missing = str(Path(self.root, "no_such_godot.exe"))
        rc, out, err = run_bridge(self.access_base("project") + [
            "--godot", missing, "--validation", "required",
            "check", "res://src/good.gd"])
        self.assertNotEqual(rc, 0, "ложное 'clean' при недоступной валидации: %s" % out)
        self.assertNotEqual(rc, 2, "инфраструктурный сбой не должен быть not-found")
        self.assertEqual(rc, 3, err)
        self.assertIn("headless: unavailable", out)
        self.assertIn("executable не найден", out)

    def test_check_validation_off_keeps_exit0_and_reports_skipped(self):
        good = Path(self.root, "src", "good.gd")
        good.write_text("extends Node\n\nfunc _ready() -> void:\n\tprint(1)\n",
                        encoding="utf-8")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--godot", str(Path(self.root, "no_such_godot.exe")),
            "--validation", "off", "check", "res://src/good.gd"])
        self.assertEqual(rc, 0, err)
        self.assertIn("headless: skipped", out)

    def test_check_blocking_headless_reaches_problems_not_only_stderr(self):
        """Блокировка обязана быть в stdout как problem, а не теряться."""
        good = Path(self.root, "src", "good.gd")
        good.write_text("extends Node\n\nfunc _ready() -> void:\n\tprint(1)\n",
                        encoding="utf-8")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--godot", str(Path(self.root, "no_such_godot.exe")),
            "--validation", "required", "check", "res://src/good.gd"])
        self.assertIn("problem:", out)
        self.assertIn("обязательная проверка настоящим Godot недоступна", out)

    def test_check_passes_through_failing_headless_diagnostics(self):
        """Ошибка кандидата, найденная Godot, — это not-found (2), не сбой (3)."""
        good = Path(self.root, "src", "good.gd")
        good.write_text("extends Node\n\nfunc _ready() -> void:\n\tprint(1)\n",
                        encoding="utf-8")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--godot", str(Path(self.root, "no_such_godot.exe")),
            "--validation", "auto", "check", "res://src/good.gd"])
        # auto при отсутствии Godot не блокирует — поведение прежнее.
        self.assertEqual(rc, 0, err)
        self.assertIn("headless: unavailable", out)

    def test_check_mixed_broken_and_blocked_prefers_readable_problems(self):
        """Сломанный файл + недоступная headless-проверка: код 2, а не 3.

        При коде 3 модель по контракту не читает stdout и потеряла бы
        сведения о конкретных проблемах сломанного файла.
        """
        broken = Path(self.root, "src", "broken.gd")
        broken.write_text("extends Node\nfunc broken(\n", encoding="utf-8")
        good = Path(self.root, "src", "good.gd")
        good.write_text("extends Node\n\nfunc _ready() -> void:\n\tprint(1)\n",
                        encoding="utf-8")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--godot", str(Path(self.root, "no_such_godot.exe")),
            "--validation", "required", "check",
            "res://src/broken.gd", "res://src/good.gd"])
        self.assertEqual(rc, 2, "проблемы файла нельзя терять за кодом сбоя: %s" % out)
        self.assertIn("path: res://src/broken.gd", out)
        self.assertIn("headless: unavailable", out)
        self.assertNotIn("files clean", err)

    def test_check_finds_defect_in_tail_of_large_gd(self):
        """Дефект в хвосте большого .gd обязан находиться, а не теряться.

        Раньше линтер получал только первые 200000 символов, и файл в 629 КБ
        с заведомым мусором в хвосте рапортовался как «1 files clean».
        """
        big = Path(self.root, "src", "big.gd")
        body = ["extends Node", ""]
        body.extend("# заполнитель %06d %s" % (i, "x" * 40) for i in range(9000))
        body.append("func tail_broken(")  # дефект строго после старого лимита
        big.write_text("\n".join(body) + "\n", encoding="utf-8")
        self.assertGreater(len(big.read_text(encoding="utf-8")), 200000)
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "check", "res://src/big.gd"])
        self.assertEqual(rc, 2, "дефект в хвосте потерян: %s" % out)
        self.assertIn("truncated: false", out)
        self.assertIn("не закрыта", out)

    def test_check_truncated_file_is_never_reported_clean(self):
        """Файл больше лимита линтера: честный отказ, а не «clean»."""
        huge = Path(self.root, "src", "huge.gd")
        huge.write_text("extends Node\n\n"
                        + ("# заполнитель %s\n" % ("y" * 60)) * 40000,
                        encoding="utf-8")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "check", "res://src/huge.gd"])
        self.assertNotEqual(rc, 0, "усечённый файл нельзя считать чистым: %s" % out)
        self.assertEqual(rc, 2, err)
        self.assertIn("truncated: true", out)
        self.assertIn("частичная проверка", out)
        self.assertIn("НЕ проверен", out)
        self.assertNotIn("files clean", err)

    def test_check_reports_truncated_false_for_normal_file(self):
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "check", "res://src/player.gd"])
        self.assertEqual(rc, 0, err)
        self.assertIn("truncated: false", out)

    def test_check_never_reports_clean_for_uncheckable_files(self):
        """`.md`/`.png`/`project.godot` не проверяются — «clean» о них ложь."""
        Path(self.root, "notes.md").write_text("# Notes\n", encoding="utf-8")
        Path(self.root, "img.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "check",
            "res://notes.md", "res://img.png", "res://project.godot"])
        self.assertNotEqual(rc, 0, "непроверяемые файлы не могут быть 'clean': %s" % out)
        self.assertEqual(rc, 2, err)
        self.assertNotIn("files clean", err)
        self.assertEqual(out.count("checked: false"), 3, out)
        self.assertIn("checked: 0/3", out)
        self.assertIn("check_skipped:", out)
        self.assertIn("не проверяется этим каналом", out)

    def test_check_mixed_batch_reports_checked_fraction(self):
        """Смешанный набор показывает, сколько файлов реально проверено."""
        Path(self.root, "img.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "check",
            "res://src/player.gd", "res://img.png"])
        self.assertIn("checked: 1/2", out)
        self.assertIn("checked: true", out)
        self.assertIn("checked: false", out)
        self.assertNotIn("files clean", err)

    def test_check_fully_checkable_batch_is_unchanged(self):
        """Полностью проверяемый набор сохраняет прежнее поведение."""
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "check", "res://src/player.gd"])
        self.assertEqual(rc, 0, err)
        self.assertIn("checked: true", out)
        self.assertIn("checked: 1/1", out)
        self.assertIn("files clean", err)

    def test_check_reports_headless_status_for_non_godot_extension(self):
        script = Path(self.root, "src", "tool.py")
        script.write_text("VALUE = 1\n", encoding="utf-8")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "check", "res://src/tool.py"])
        self.assertEqual(rc, 0, err)
        self.assertIn("headless: not-applicable", out)

    def test_check_action_judges_without_writing(self):
        payload = {"text": "```agent_action\n%s\n```" % json.dumps({
            "action": "patch_file", "path": "res://src/player.gd",
            "search": "var hp = 100", "replace": "var hp = 80"})}
        request = self.request_file(payload, "judge.json")
        before = Path(self.root, "src", "player.gd").read_text()
        rc, out, err = run_bridge(self.access_base("project") + [
            "check_action", "--request", request])
        self.assertEqual(rc, 0, err)
        self.assertIn('"acceptable": true', out)
        self.assertEqual(Path(self.root, "src", "player.gd").read_text(), before)

    def test_repair_scene_applies_only_deterministic_fixes_and_rolls_back(self):
        scene = Path(self.root, "repair.tscn")
        original = ('[gd_scene load_steps=9 format=3]\n\n'
            '[node name="Root" type="Node"]\n'
            'material = SubResource("1_mat")\n'
            '[/node]\n\n'
            '[sub_resource type="StandardMaterial3D" id="1_mat"]\n'
            'albedo_color = Color(1, 0, 0, 1)\n')
        scene.write_text(original, encoding="utf-8")
        request = self.request_file({"action": "repair_scene",
            "path": "res://repair.tscn"}, "repair.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)
        plan_id = self.plan_id(out)
        self.assertEqual(scene.read_text(), original)
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "apply", "--request", request,
            "--plan-id", plan_id])
        self.assertEqual(rc, 0, err)
        entry_id = self.entry_id(out)
        fixed = scene.read_text()
        self.assertNotIn("[/node]", fixed)
        self.assertIn('load_steps=2', fixed)
        self.assertLess(fixed.index('[sub_resource'), fixed.index('[node'))
        rc, out, err = run_bridge(self.access_base("project") + [
            "write", "rollback", "--entry-id", entry_id])
        self.assertEqual(rc, 0, err)
        self.assertEqual(scene.read_text(), original)

    def test_repair_scene_refuses_ambiguous_problem_without_fix(self):
        scene = Path(self.root, "ambiguous.tscn")
        scene.write_text('[gd_scene format=3]\n\n'
            '[ext_resource type="Script" path="res://missing.gd" id="1"]\n'
            '[node name="Root" type="Node"]\n'
            'script = ExtResource("1")\n', encoding="utf-8")
        request = self.request_file({"action": "repair_scene",
            "path": "res://ambiguous.tscn"}, "ambiguous.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 2, err)
        self.assertIn("no deterministic repair", out)

    def test_rename_symbol_via_write_and_rollback(self):
        player = Path(self.root, "src", "player.gd")
        player.write_text("class_name Player\nextends Node\n\n"
            "func take_damage(amount: int):\n\tpass\n", encoding="utf-8")
        consumer = Path(self.root, "src", "consumer.gd")
        consumer.write_text("extends Node\nvar player: Player\n\n"
            "func run():\n\tplayer.take_damage(1)\n", encoding="utf-8")
        request = self.request_file({"action": "rename_symbol", "kind": "function",
            "declaration": "res://src/player.gd:4", "old_name": "take_damage",
            "new_name": "apply_damage"}, "symbol.json")
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "preview", "--request", request])
        self.assertEqual(rc, 0, err)
        plan_id = self.plan_id(out)
        self.assertIn("take_damage", player.read_text())
        rc, out, err = run_bridge(self.access_base("project") + [
            "--validation", "off", "write", "apply", "--request", request,
            "--plan-id", plan_id])
        self.assertEqual(rc, 0, err)
        entry_id = self.entry_id(out)
        self.assertIn("apply_damage", player.read_text())
        self.assertIn("apply_damage", consumer.read_text())
        rc, out, err = run_bridge(self.access_base("project") + [
            "write", "rollback", "--entry-id", entry_id])
        self.assertEqual(rc, 0, err)
        self.assertIn("take_damage", player.read_text())
        self.assertIn("take_damage", consumer.read_text())

    # --- status -------------------------------------------------------------

    def test_status_server_down_exit3_clean_message(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()  # порт гарантированно свободен -> соединение откажут
        rc, out, err = run_bridge(self.base + ["--port", str(port), "--timeout", "1", "status"])
        self.assertEqual(rc, 3, err)
        self.assertIn("error", err.lower())
        self.assertNotIn("Traceback", out + err)
        # пользователь должен понять, что офлайн-команды всё равно доступны
        self.assertIn("offline", (out + err).lower())

    # --- токен / user_data_dir ----------------------------------------------

    def test_token_read_from_user_data_dir(self):
        udd = tempfile.TemporaryDirectory(prefix="bridge_udd_")
        self.addCleanup(udd.cleanup)
        Path(udd.name, "godot_agent_token.txt").write_text("  sekret-token \n", encoding="utf-8")
        self.assertEqual(agent_bridge._read_token(udd.name), "sekret-token")
        self.assertEqual(agent_bridge._read_token(os.path.join(udd.name, "nope")), "")

    def test_project_name_parsed_from_project_godot(self):
        self.assertEqual(agent_bridge._project_name(self.root), "Bridge Test Proj")

    def test_usage_error_exit4(self):
        rc, out, err = run_bridge(self.base + ["api"])  # без имени класса
        self.assertEqual(rc, 4, err)
        self.assertNotIn("Traceback", out + err)


if __name__ == "__main__":
    unittest.main()
