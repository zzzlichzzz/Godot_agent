# -*- coding: utf-8 -*-
"""Тесты «пилы» для .gd (split_gd.py): инвентарь, скан ссылок, план, apply.

Проверяемый контракт:
  * file_inventory: extends/class_name/header_end, константы (в т.ч. многострочные
    и с прилегающим комментарием), @onready-члены, методы с точными границами
    (block_start/sig_start/body_start/end), многострочные сигнатуры, параметры
    с дефолтами, возвращаемый тип, has_await, аннотации; незакрытая сигнатура
    попадает в errors, а не в исключение;
  * suggest_groups: движковые виртуальные методы (_ready и т.п.) остаются в
    доноре, нарезка по target_lines, отказ, когда выносить нечего;
  * scan_refs: категории path/source_read/call/doc, skip-каталоги (dist,
    agent_api_cache), сам донор исключён, hard_files = «читающие исходник»;
  * plan_split: модули + обёртки + preload-константы в доноре, переписывание
    тела (члены донора -> panel.<член>, $Путь/%Имя -> get_node, self -> panel,
    движковые методы/свойства -> panel.<...>), даунгрейд вывода типа (:= -> =)
    для panel-заражённых выражений, копии констант в модуль; отказы
    (неизвестный метод, дубль метода, имя модуля, занятый целевой файл,
    аннотации, параметр panel, super, дефолт-член, пустое тело, конфликт
    preload-константы, отсутствие project.godot) и предупреждение о виртуальном;
  * apply_prepared_split: пишет модули и нового донора, обёртки сохраняют все
    имена методов (connect/call/scene не ломаются), prepared переживает
    JSON-roundtrip, устаревший донор и занятый целевой файл — StaleSplitGdError,
    чужой prepared — SplitGdError, провал Godot-проверки атомарен (созданные
    модули удалены, донор не тронут).

Тесты офлайновые: Godot не нужен, «движковое API» берётся из мини-кэша
agent_api_cache/default_api_cache.json, который кладёт фикстура.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import split_gd  # noqa: E402


# Мини-кэш ClassDB: ровно те методы/свойства, которые тесты ждут увидеть
# с префиксом `panel.`. Полный кэш проекта подменял бы ожидания fallback-списком.
API_CACHE = {
    "classes": {
        "Control": {"inherits": "CanvasItem",
                    "methods": {"get_tree": {}, "add_child": {}},
                    "properties": ["visible", "size", "position"]},
        "CanvasItem": {"inherits": "Node", "methods": {}, "properties": []},
        "Node": {"inherits": "Object", "methods": {"get_node": {}},
                 "properties": []},
        "Object": {"inherits": "", "methods": {}, "properties": []},
    }
}

DEMO = '''@tool
extends Control

const PANEL_TITLE = "Agent"
const STEP = 2

@onready var status_label: Label = $Status
var _history: Array = []


# Строит панель: константа, член донора, узел, движковое API и self.
func build_panel() -> void:
\tvar label := $Status
\tvar count := STEP + 1
\t_history.append(count)
\tstatus_label.text = PANEL_TITLE
\tvisible = true
\tget_tree().root.add_child(self)


func toggle_flag(enabled: bool = true) -> bool:
\tvar rest := _history.size() % STEP
\treturn enabled and rest == 0


func load_data() -> void:
\tawait get_tree().process_frame
\t%Spinner.visible = false


func _ready() -> void:
\tbuild_panel()
'''

GROUPS = [
    {"module": "agent_panel_part1", "funcs": ["build_panel", "toggle_flag"]},
    {"module": "agent_panel_part2", "funcs": ["load_data"]},
]


class Fixture(unittest.TestCase):
    """Временный Godot-проект: addons/Godot_agent/godot_agent + project.godot.

    Раскладка повторяет реальную, поэтому работает и автопоиск корня проекта
    (_project_root_of: addon/../../..), и относительные preload-пути модулей.
    """

    ADDON_REL = "addons/Godot_agent/godot_agent"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="split_gd_")
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.addon = os.path.join(self.root, *self.ADDON_REL.split("/"))
        os.makedirs(self.addon, exist_ok=True)
        self.write("project.godot",
                   "[application]\nconfig/name=\"SplitGdTest\"\n")
        self.write(self.ADDON_REL + "/agent_api_cache/default_api_cache.json",
                   json.dumps(API_CACHE, ensure_ascii=False, indent=1))

    def path(self, rel):
        return os.path.join(self.root, *rel.split("/"))

    def write(self, rel, text):
        abs_path = self.path(rel)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return abs_path

    def read(self, rel):
        with open(self.path(rel), "r", encoding="utf-8") as handle:
            return handle.read()

    def donor_rel(self, name="agent_panel.gd"):
        """Путь донора ОТ АДДОНА — так его ждут scan_refs/plan_split."""
        return name

    def donor_file(self, name="agent_panel.gd"):
        """Тот же донор, но от корня проекта — для файловых операций теста."""
        return self.ADDON_REL + "/" + name

    def module_file(self, name):
        """Путь модуля от корня проекта — как его пишет apply_prepared_split."""
        return self.ADDON_REL + "/" + name

    def fake_godot(self, code=0):
        """Фейковый Godot: .cmd на Windows, .sh иначе; иначе skipTest.

        split_gd запускает ровно один исполняемый файл, поэтому «python + скрипт»
        тут не подходит — нужен настоящий executable-файл платформы.
        """
        if os.name == "nt":
            rel, body = "fake_godot_%d.cmd" % code, \
                "@echo off\r\nexit /b %d\r\n" % code
        else:
            rel, body = "fake_godot_%d.sh" % code, "#!/bin/sh\nexit %d\n" % code
        abs_path = self.write(rel, body)
        if os.name != "nt":
            os.chmod(abs_path, 0o755)
        try:
            probe = subprocess.run([abs_path, "--headless"], capture_output=True,
                                   timeout=30)
        except OSError as error:
            self.skipTest("фейковый Godot не запускается: %s" % error)
        if probe.returncode != code:
            self.skipTest("фейковый Godot вернул %d вместо %d"
                          % (probe.returncode, code))
        return abs_path


class ScanTests(Fixture):
    """scan_refs: категории ссылок, skip-каталоги, исключение самого донора."""

    def setUp(self):
        super().setUp()
        self.write(self.donor_file(), DEMO)
        self.write(self.ADDON_REL + "/caller.gd",
                   "extends Node\n"
                   "\n"
                   "\n"
                   "func call_it() -> void:\n"
                   "\tpanel.build_panel()\n"
                   "\tpanel.load_data()\n")
        self.write(self.ADDON_REL + "/reader.py",
                   "SRC = open(\"agent_panel.gd\", encoding=\"utf-8\").read()\n")
        self.write(self.ADDON_REL + "/docs/note.md", "См. agent_panel.gd:12.\n")
        self.write(self.ADDON_REL + "/scenes/main.tscn",
                   "[ext_resource type=\"Script\" "
                   "path=\"res://addons/Godot_agent/godot_agent/agent_panel.gd\""
                   " id=\"1\"]\n")
        self.write(self.ADDON_REL + "/dist/gen.gd",
                   "extends Node\n"
                   "\n"
                   "\n"
                   "func gen() -> void:\n"
                   "\tpanel.build_panel()\n")
        self.write(self.ADDON_REL + "/plain.gd",
                   "extends Node\n"
                   "\n"
                   "\n"
                   "func nothing() -> void:\n"
                   "\tpass\n")

    def scan(self):
        return split_gd.scan_refs(self.addon, self.donor_rel())

    def test_categories_and_hard_files(self):
        scan = self.scan()
        self.assertEqual(scan["counts"],
                         {"path": 1, "source_read": 1, "call": 2, "doc": 1,
                          "mention": 0})
        self.assertEqual(scan["hard_files"], ["reader.py"])
        self.assertEqual(scan["soft_files"],
                         ["caller.gd", "docs/note.md", "scenes/main.tscn"])
        self.assertEqual(scan["public_methods"],
                         ["build_panel", "load_data", "toggle_flag"])
        self.assertEqual(scan["extends"], "Control")
        self.assertEqual(scan["class_name"], "")
        self.assertEqual(scan["funcs"], 4)
        self.assertFalse(scan["truncated"])

    def test_skips_generated_dirs_and_donor_itself(self):
        scan = self.scan()
        seen = {item["file"] for item in scan["occurrences"]}
        self.assertNotIn("dist/gen.gd", seen)
        self.assertNotIn("plain.gd", seen)
        self.assertNotIn(self.donor_rel(), seen)
        self.assertNotIn("agent_api_cache/default_api_cache.json", seen)

    def test_missing_donor_refused(self):
        with self.assertRaises(split_gd.SplitGdError):
            split_gd.scan_refs(self.addon, self.donor_rel("absent.gd"))


INVENTORY_TEXT = '''@tool
extends Control
class_name SawDemo

const PANEL_TITLE = "Agent"
const LIMITS = {
\t"warn": 1500,
\t"max": 2000,
}

@onready var status_label: Label = $Status
var _history: Array = []


# Строит панель.
func build_panel() -> void:
\tpass


func multi(
\ta: int,
\tb: int = 2,
) -> int:
\treturn a + b


func load_data() -> void:
\tawait get_tree().process_frame
'''

ANNOTATED = '''extends Node


@rpc("any_peer")
func ping() -> void:
\tpass
'''


class InventoryTests(Fixture):
    """file_inventory: границы блоков, константы, члены, сигнатуры, аннотации."""

    def test_header_consts_vars_and_bounds(self):
        inventory = split_gd.file_inventory(INVENTORY_TEXT)
        self.assertEqual(inventory["extends"], "Control")
        self.assertEqual(inventory["class_name"], "SawDemo")
        self.assertEqual(inventory["header_end"], 3)
        self.assertEqual(inventory["errors"], [])
        consts = {item["name"]: item for item in inventory["consts"]}
        self.assertEqual(sorted(consts), ["LIMITS", "PANEL_TITLE"])
        self.assertEqual(consts["PANEL_TITLE"]["start"], 5)
        self.assertEqual(consts["PANEL_TITLE"]["end"], 5)
        # многострочная константа склеена до закрывающей скобки
        self.assertEqual(consts["LIMITS"]["start"], 6)
        self.assertEqual(consts["LIMITS"]["end"], 9)
        self.assertIn('"max": 2000,', consts["LIMITS"]["text"])
        self.assertEqual([item["name"] for item in inventory["vars"]],
                         ["status_label", "_history"])
        self.assertEqual([item["line"] for item in inventory["vars"]], [11, 12])
        funcs = {item["name"]: item for item in inventory["funcs"]}
        self.assertEqual(sorted(funcs),
                         ["build_panel", "load_data", "multi"])
        built = funcs["build_panel"]
        # комментарий над методом — часть блока: block_start < sig_start
        self.assertEqual(built["block_start"], 15)
        self.assertEqual(built["sig_start"], 16)
        self.assertEqual(built["body_start"], 17)
        self.assertEqual(built["end"], 17)
        self.assertEqual(built["ret"], "void")
        self.assertFalse(built["has_await"])

    def test_multiline_signature_and_await(self):
        inventory = split_gd.file_inventory(INVENTORY_TEXT)
        funcs = {item["name"]: item for item in inventory["funcs"]}
        multi = funcs["multi"]
        self.assertEqual(len(multi["sig_lines"]), 4)
        self.assertEqual(multi["params"], [{"name": "a", "default": None},
                                           {"name": "b", "default": "2"}])
        self.assertEqual(multi["ret"], "int")
        self.assertEqual(multi["end"], multi["body_start"])
        self.assertTrue(funcs["load_data"]["has_await"])

    def test_annotations_collected(self):
        inventory = split_gd.file_inventory(ANNOTATED)
        func = inventory["funcs"][0]
        self.assertEqual(func["anns"], ['@rpc("any_peer")'])
        self.assertEqual(func["block_start"], 4)
        self.assertEqual(func["sig_start"], 5)

    def test_unclosed_signature_reported_as_error(self):
        inventory = split_gd.file_inventory("extends Node\n\n\nfunc broken(a: int,\n")
        self.assertTrue(inventory["errors"])
        self.assertIn("не закрыта", inventory["errors"][0])
        self.assertIn("broken", inventory["errors"][0])


class SuggestGroupsTests(Fixture):
    """suggest_groups: виртуальные методы остаются в доноре, нарезка по лимиту."""

    def test_virtuals_stay_in_donor(self):
        inventory = split_gd.file_inventory(DEMO)
        groups = split_gd.suggest_groups(inventory, "agent_panel")
        self.assertEqual(groups, [{"module": "agent_panel_part1",
                                   "funcs": ["build_panel", "toggle_flag",
                                             "load_data"]}])

    def test_chunks_by_target_lines_keep_order(self):
        inventory = split_gd.file_inventory(DEMO)
        groups = split_gd.suggest_groups(inventory, "agent_panel", target_lines=8)
        self.assertEqual(len(groups), 2)
        self.assertEqual([item["module"] for item in groups],
                         ["agent_panel_part1", "agent_panel_part2"])
        moved = [name for group in groups for name in group["funcs"]]
        self.assertEqual(moved, ["build_panel", "toggle_flag", "load_data"])
        self.assertNotIn("_ready", moved)

    def test_nothing_to_move_refused(self):
        inventory = split_gd.file_inventory("extends Node\nvar x: int = 1\n")
        with self.assertRaises(split_gd.SplitGdError):
            split_gd.suggest_groups(inventory, "agent_panel")


class PlanTests(Fixture):
    """plan_split: модули, обёртки, переписанные тела, отказы, предупреждения."""

    def _plan(self, groups=GROUPS, text=None, donor="agent_panel.gd", **kwargs):
        self.write(self.donor_file(donor), DEMO if text is None else text)
        return split_gd.plan_split(self.addon, self.donor_rel(donor), groups,
                                   **kwargs)

    def test_plan_is_read_only(self):
        self.write(self.donor_file(), DEMO)
        before = self.read(self.donor_file())
        self._plan()
        self.assertEqual(self.read(self.donor_file()), before)
        self.assertFalse(os.path.exists(self.path(
            self.module_file("agent_panel_part1.gd"))))

    def test_plan_moves_bodies_into_modules(self):
        prepared = self._plan()
        self.assertEqual(prepared["kind"], "split_gd")
        self.assertEqual([item["rel"] for item in prepared["modules"]],
                         ["agent_panel_part1.gd", "agent_panel_part2.gd"])
        self.assertEqual([item["const"] for item in prepared["modules"]],
                         ["AgentPanelPart1", "AgentPanelPart2"])
        part1 = prepared["modules"][0]["content"]
        self.assertTrue(part1.startswith("@tool\nextends RefCounted\n"))
        self.assertIn("static func build_panel(panel) -> void:", part1)
        self.assertIn("static func toggle_flag(panel, enabled: bool = true)"
                      " -> bool:", part1)
        # тело: локальные переменные без префикса, вывод типа от panel снят
        self.assertIn('\tvar label = panel.get_node("Status")', part1)
        self.assertIn("\tvar count := STEP + 1", part1)
        self.assertIn("\tpanel._history.append(count)", part1)
        self.assertIn("\tpanel.status_label.text = PANEL_TITLE", part1)
        self.assertIn("\tpanel.visible = true", part1)
        self.assertIn("\tpanel.get_tree().root.add_child(panel)", part1)
        # modulo не путается с %УникальнымИменем, но вывод типа снят
        self.assertIn("\tvar rest = panel._history.size() % STEP", part1)
        # константы скопированы, комментарий-блок уехал в модуль
        self.assertIn('const PANEL_TITLE = "Agent"', part1)
        self.assertIn("const STEP = 2", part1)
        self.assertIn("# Строит панель", part1)

    def test_unique_name_and_await_rewritten(self):
        prepared = self._plan()
        part2 = prepared["modules"][1]["content"]
        self.assertIn("static func load_data(panel) -> void:", part2)
        self.assertIn("\tawait panel.get_tree().process_frame", part2)
        self.assertIn('\tpanel.get_node("%Spinner").visible = false', part2)
        awaiters = [item for item in prepared["wrappers"] if item["await"]]
        self.assertEqual([item["name"] for item in awaiters], ["load_data"])

    def test_donor_keeps_wrappers_preloads_and_names(self):
        prepared = self._plan()
        donor = prepared["donor_content"]
        self.assertIn("# --- части (вынесены «пилой» split_gd) ---", donor)
        self.assertIn('const AgentPanelPart1 = preload("agent_panel_part1.gd")',
                      donor)
        self.assertIn('const AgentPanelPart2 = preload("agent_panel_part2.gd")',
                      donor)
        self.assertIn("# split_gd: тело — agent_panel_part1.gd", donor)
        self.assertIn("func build_panel() -> void:\n"
                      "\tAgentPanelPart1.build_panel(self)", donor)
        self.assertIn("func toggle_flag(enabled: bool = true) -> bool:\n"
                      "\treturn AgentPanelPart1.toggle_flag(self, enabled)", donor)
        self.assertIn("func load_data() -> void:\n"
                      "\tawait AgentPanelPart2.load_data(self)", donor)
        # виртуальный _ready остался в доноре, комментарий метода уехал в модуль
        self.assertIn("func _ready() -> void:\n\tbuild_panel()", donor)
        self.assertNotIn("# Строит панель", donor)
        self.assertNotIn("func build_panel(panel", donor)
        for item in prepared["wrappers"]:
            self.assertIn("func %s(" % item["name"], donor)
        self.assertEqual(prepared["stats"],
                         {"moved": 3, "modules": 2,
                          "donor_before": len(DEMO.splitlines()),
                          "donor_after": donor.count("\n") + 1})
        # тела уехали в модули: в доноре их больше нет
        self.assertNotIn("_history.append(count)", donor)
        self.assertNotIn("status_label.text = PANEL_TITLE", donor)
        # на трёх тонких методах экономия строк съедается preload-блоком и
        # строками-указателями — важно лишь, что раскол не раздувает донор
        self.assertLessEqual(prepared["stats"]["donor_after"],
                             prepared["stats"]["donor_before"])

    def test_auto_groups_when_groups_omitted(self):
        prepared = self._plan(groups=None)
        self.assertEqual([item["module"] for item in prepared["groups"]],
                         ["agent_panel_part1"])
        self.assertNotIn("_ready", prepared["groups"][0]["funcs"])

    def test_virtual_method_warns_but_plans(self):
        prepared = self._plan(groups=[{"module": "agent_panel_part1",
                                       "funcs": ["_ready"]}])
        joined = "\n".join(prepared["warnings"])
        self.assertIn("_ready", joined)
        self.assertIn("движковый виртуальный метод", joined)
        self.assertIn("func _ready(", prepared["donor_content"])

    def test_unknown_and_duplicate_methods_refused(self):
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "agent_panel_part1",
                                "funcs": ["absent"]}])
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "agent_panel_part1",
                                "funcs": ["build_panel"]},
                               {"module": "agent_panel_part2",
                                "funcs": ["build_panel"]}])
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "AgentPanelPart1",
                                "funcs": ["build_panel"]}])

    def test_existing_target_refused(self):
        self.write(self.module_file("agent_panel_part1.gd"),
                   "extends RefCounted\n")
        with self.assertRaises(split_gd.StaleSplitGdError):
            self._plan(groups=[{"module": "agent_panel_part1",
                                "funcs": ["build_panel"]}])

    def test_annotated_method_refused(self):
        text = ('extends Control\n\n\n@rpc("any_peer")\n'
                'func rpc_ping() -> void:\n\tpass\n')
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "agent_panel_part1",
                                "funcs": ["rpc_ping"]}], text=text)

    def test_panel_param_and_name_collision_refused(self):
        text = ("extends Control\n\n\nfunc ping(panel: int) -> void:\n\tpass\n")
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "agent_panel_part1",
                                "funcs": ["ping"]}], text=text)
        text = ("extends Control\n\n\nfunc ping() -> void:\n"
                "\tvar panel := 1\n\tprint(panel)\n")
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "agent_panel_part1",
                                "funcs": ["ping"]}], text=text)

    def test_super_member_default_and_empty_body_refused(self):
        super_text = ("extends Control\n\n\nfunc ping() -> void:\n"
                      "\tsuper.ready()\n")
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "agent_panel_part1",
                                "funcs": ["ping"]}], text=super_text)
        default_text = ("extends Control\n\n\nvar status_label: Label = null\n"
                        "\n\nfunc pick(node: Control = status_label) -> void:\n"
                        "\tpass\n")
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "agent_panel_part1",
                                "funcs": ["pick"]}], text=default_text)
        empty_text = ("extends Control\n\n\nfunc stub() -> void:\n"
                      "\n\nfunc other() -> void:\n\tpass\n")
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "agent_panel_part1",
                                "funcs": ["stub"]}], text=empty_text)

    def test_preload_const_conflict_and_missing_root_refused(self):
        text = ("extends Control\n\n\nconst Part1 = 1\n\n\n"
                "func ping() -> void:\n\tpass\n")
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "part1", "funcs": ["ping"]}],
                       text=text)
        os.remove(self.path("project.godot"))
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(groups=[{"module": "agent_panel_part1",
                                "funcs": ["build_panel"]}])

    def test_donor_without_methods_refused(self):
        with self.assertRaises(split_gd.SplitGdError):
            self._plan(text="extends Control\nvar x: int = 1\n")


class ApplyTests(Fixture):
    """apply_prepared_split: запись, сохранение имён, stale-отказы, атомарность."""

    def _plan(self, groups=GROUPS):
        self.write(self.donor_file(), DEMO)
        return split_gd.plan_split(self.addon, self.donor_rel(), groups)

    def test_apply_writes_modules_and_donor(self):
        prepared = self._plan()
        report = split_gd.apply_prepared_split(prepared)
        self.assertEqual(report["modules"],
                         ["agent_panel_part1.gd", "agent_panel_part2.gd"])
        self.assertEqual(report["wrappers"], 3)
        self.assertEqual(report["checks"], [])
        self.assertEqual(report["donor_lines"], prepared["stats"]["donor_after"])
        self.assertEqual(self.read(self.module_file("agent_panel_part1.gd")),
                         prepared["modules"][0]["content"])
        donor = self.read(self.donor_file())
        self.assertEqual(donor, prepared["donor_content"])
        # имена методов сохранены обёртками: connect()/call()/сцены не ломаются
        for item in prepared["wrappers"]:
            self.assertIn("func %s(" % item["name"], donor)
        self.assertFalse(os.path.exists(
            self.path(self.donor_file() + ".split_gd_tmp")))

    def test_prepared_survives_json_roundtrip(self):
        prepared = self._plan()
        loaded = json.loads(json.dumps(prepared, ensure_ascii=False))
        report = split_gd.apply_prepared_split(loaded)
        self.assertTrue(report["modules"])
        self.assertIn("AgentPanelPart1.build_panel(self)",
                      self.read(self.donor_file()))

    def test_stale_donor_refused(self):
        prepared = self._plan()
        changed = DEMO + "\n\nfunc extra() -> void:\n\tpass\n"
        self.write(self.donor_file(), changed)
        with self.assertRaises(split_gd.StaleSplitGdError):
            split_gd.apply_prepared_split(prepared)
        self.assertEqual(self.read(self.donor_file()), changed)
        self.assertFalse(os.path.exists(
            self.path(self.module_file("agent_panel_part1.gd"))))

    def test_second_apply_is_stale(self):
        prepared = self._plan()
        split_gd.apply_prepared_split(prepared)
        with self.assertRaises(split_gd.StaleSplitGdError):
            split_gd.apply_prepared_split(prepared)

    def test_existing_module_refused(self):
        prepared = self._plan()
        self.write(self.module_file("agent_panel_part1.gd"),
                   "extends RefCounted\n")
        with self.assertRaises(split_gd.StaleSplitGdError):
            split_gd.apply_prepared_split(prepared)
        self.assertEqual(self.read(self.donor_file()), DEMO)

    def test_foreign_prepared_refused(self):
        prepared = self._plan()
        prepared["kind"] = "split_refactor"
        with self.assertRaises(split_gd.SplitGdError):
            split_gd.apply_prepared_split(prepared)
        self.assertEqual(self.read(self.donor_file()), DEMO)

    def test_godot_failure_is_atomic(self):
        prepared = self._plan()
        godot = self.fake_godot(code=1)
        with self.assertRaises(split_gd.SplitGdError):
            split_gd.apply_prepared_split(prepared, godot)
        # донор не тронут, созданные модули удалены, temp не остался
        self.assertEqual(self.read(self.donor_file()), DEMO)
        for name in ("agent_panel_part1.gd", "agent_panel_part2.gd"):
            self.assertFalse(os.path.exists(self.path(self.module_file(name))))
        self.assertFalse(os.path.exists(
            self.path(self.donor_file() + ".split_gd_tmp")))
        self.assertFalse(os.path.exists(self.path(
            self.donor_file()[:-3] + ".check_tmp.gd")))

    def test_godot_success_records_checks(self):
        prepared = self._plan()
        godot = self.fake_godot(code=0)
        report = split_gd.apply_prepared_split(prepared, godot)
        self.assertEqual(len(report["checks"]), 3)
        self.assertTrue(all(item["code"] == 0 for item in report["checks"]))
        self.assertEqual(self.read(self.donor_file()), prepared["donor_content"])
        self.assertFalse(os.path.exists(self.path(
            self.donor_file()[:-3] + ".check_tmp.gd")))


if __name__ == "__main__":
    unittest.main()
