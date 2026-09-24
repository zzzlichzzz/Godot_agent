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
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path

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
        self.base = ["--root", self.root, "--no-builtin-cache"]

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
