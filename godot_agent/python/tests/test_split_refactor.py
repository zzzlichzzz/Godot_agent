# -*- coding: utf-8 -*-
"""Тесты «пилы» (split_refactor.py): скан ссылок, инвентарь, план, фасадный apply.

Проверяемый контракт:
  * scan_refs видит импорты (в т.ч. `import x as alias`), строковые упоминания,
    доки и эвристику «чтение исходника»; skip-каталоги и ложные совпадения
    (test_target_mod.py, target_mod_extra) не цепляет;
  * file_inventory: докстрока, импорты с bindings, символы верхнего уровня
    (def/class/assign, публичные/приватные, декораторы), мутабельный state,
    склейка комментария над символом; битый .py — SplitError;
  * plan_split: авто-группы по target_lines; отказы (неизвестный символ,
    дубль, существующий файл, лимит строк, дубль имени в ядре, цикл групп,
    символ остаётся в фасаде) и предупреждения (дубль вне ядра, близко к
    лимиту, зона потребителя, мутабельный state, черновые авто-группы);
  * apply_prepared_split: пишет модули и фасад, старый путь и импортное имя
    продолжают работать (фасад реэкспортирует, кросс-импорт модулей — из
    плана); устаревший донор — StaleSplitError, план с ошибками — SplitError;
    prepared сериализуется в JSON без потерь.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import split_refactor  # noqa: E402

MINI_MAP = {
    "schema": 1,
    "core_dir": "python/godot_tools",
    "name_stoplist": ["main", "run"],
    "limits": {"line_warn": 60, "line_max": 100,
               "line_exts": [".py", ".gd"],
               "line_exempt_roles": ["workflow", "generated", "tasks",
                                     "reports"]},
    "zones": [
        {"glob": "python/godot_tools/**", "role": "core",
         "new_files": "allow"},
        {"glob": "python/tests/**", "role": "tests", "new_files": "allow",
         "check_names": False},
        {"glob": "python/tools/**", "role": "consumer", "new_files": "warn",
         "hint": "только проводка, логика — в ядре"},
        {"glob": "agent_api_cache/**", "role": "generated",
         "new_files": "deny"},
        {"glob": "**", "role": "unknown", "new_files": "warn"},
    ],
}

DEMO = '''# -*- coding: utf-8 -*-
"""Демо-модуль: константа, функции, приватный помощник и мутабельный кэш."""

import json


CONST = 10
_CACHE = {}


def alpha():
    """Возвращает CONST + 1."""
    return CONST + 1


def beta():
    """Пишет в кэш (json) и зовёт alpha: кросс-импорт между модулями."""
    _CACHE["seen"] = json.dumps({"calls": _CACHE.get("calls", 0) + 1})
    return alpha() + 1


def _helper():
    return 2
'''

GROUPS = [
    {"module": "sawdemo_part1", "symbols": ["alpha", "CONST"]},
    {"module": "sawdemo_part2", "symbols": ["beta", "_helper", "_CACHE"]},
]


class Fixture(unittest.TestCase):
    """Временный аддон с картой архитектуры; у каждого теста — свой."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="split_refactor_")
        self.addCleanup(self._tmp.cleanup)
        self.addon = str(Path(self._tmp.name) / "addon")
        self.write("docs/architecture_map.json",
                   json.dumps(MINI_MAP, ensure_ascii=False, indent=2))

    def write(self, rel, text):
        abs_path = Path(self.addon, *rel.split("/"))
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(text, encoding="utf-8")
        return rel

    def read(self, rel):
        return Path(self.addon, *rel.split("/")).read_text(encoding="utf-8")


class ScanTests(Fixture):
    """scan_refs: импорты, доки, упоминания, «чтение исходника», skip-каталоги."""

    def setUp(self):
        super().setUp()
        self.write("python/godot_tools/target_mod.py",
                   "def t():\n    return 1\n")
        self.write("python/server/user1.py",
                   "import target_mod\n"
                   "from target_mod import t\n"
                   "import target_mod as tm\n"
                   'TAG = "target_mod.py"\n'
                   "\n"
                   "\n"
                   "def use():\n"
                   "    return t()\n")
        self.write("python/server/user2.py",
                   "import os\n"
                   'SRC = open(os.path.join("godot_tools", "target_mod.py"),'
                   ' encoding="utf-8").read()\n')
        self.write("python/server/user3.py", "import target_mod_extra\n")
        self.write("python/tests/test_target_mod.py",
                   "# см. test_target_mod.py\n")
        self.write("docs/note.md",
                   "См. python/godot_tools/target_mod.py:12.\n")
        self.write("python/dist/gen.py", "import target_mod\n")

    def test_counts_and_files(self):
        scan = split_refactor.scan_refs(
            self.addon, "python/godot_tools/target_mod.py")
        self.assertEqual(scan["counts"],
                         {"import": 3, "source_read": 1, "patch": 0,
                          "mention": 1, "doc": 1})
        self.assertIn("python/server/user1.py", scan["hard_files"])
        self.assertIn("python/server/user2.py", scan["hard_files"])
        self.assertIn("docs/note.md", scan["soft_files"])
        self.assertIn("python/server/user1.py", scan["soft_files"])

    def test_skips_generated_and_lookalikes(self):
        scan = split_refactor.scan_refs(
            self.addon, "python/godot_tools/target_mod.py")
        seen = {item["rel"] for item in scan["occurrences"]}
        self.assertNotIn("python/dist/gen.py", seen)
        self.assertNotIn("python/tests/test_target_mod.py", seen)
        self.assertNotIn("python/server/user3.py", seen)

    def test_attr_patch_of_donor_is_hard_reference(self):
        """Патч атрибута донора (`mod.fn = ...`) — жёсткая ссылка.

        После разбиения фасад сохраняет атрибут, но вынесенные функции
        вызывают свои копии-импорты: патч тихо перестаёт действовать,
        поэтому файл обязан попасть в hard_files.
        """
        self.write("python/server/user4.py",
                   "import target_mod\n"
                   "\n"
                   "original = target_mod.t\n"
                   "target_mod.t = lambda: None\n")
        scan = split_refactor.scan_refs(
            self.addon, "python/godot_tools/target_mod.py")
        self.assertEqual(scan["counts"]["patch"], 1)
        self.assertIn("python/server/user4.py", scan["hard_files"])


INVENTORY_TEXT = '''"""Докстрока модуля."""

import json
from os import path as _path

# Комментарий-раздел
VALUE = 1
STATE = {}
A = B = 1
__version__ = "1"


def public():
    return json.dumps({"v": VALUE})


class Klass:
    def method(self):
        return _path


def _private():
    return _path
'''

DECORATED = '''"""Д."""

import functools


def deco(func):
    return func


@deco
def wrapped():
    return 1
'''


class InventoryTests(Fixture):
    """file_inventory: докстрока, импорты, символы, state, комментарии."""

    def test_symbols_imports_state_comments(self):
        inventory = split_refactor.file_inventory(INVENTORY_TEXT)
        self.assertEqual(inventory["docstring"], "Докстрока модуля.")
        self.assertEqual([imp["bindings"] for imp in inventory["imports"]],
                         [["json"], ["_path"]])
        by_name = {item["name"]: item for item in inventory["symbols"]}
        self.assertEqual(sorted(by_name),
                         ["Klass", "STATE", "VALUE", "_private", "public"])
        self.assertTrue(by_name["STATE"]["state"])
        self.assertFalse(by_name["VALUE"]["state"])
        self.assertTrue(by_name["VALUE"]["is_public"])
        self.assertFalse(by_name["_private"]["is_public"])
        self.assertLess(by_name["VALUE"]["line_start"],
                        by_name["VALUE"]["lineno"])
        self.assertTrue(any(item["name"] == "__version__"
                            for item in inventory["other"]))

    def test_decorators_join_symbol(self):
        inventory = split_refactor.file_inventory(DECORATED)
        wrapped = {item["name"]: item for item in inventory["symbols"]}
        wrapped = wrapped["wrapped"]
        text = split_refactor._segment_text(DECORATED.splitlines(),
                                            wrapped["line_start"],
                                            wrapped["end_lineno"])
        self.assertTrue(text.startswith("@deco"))
        self.assertEqual(wrapped["lines"], 3)

    def test_broken_python(self):
        with self.assertRaises(split_refactor.SplitError):
            split_refactor.file_inventory("def broken(:\n")


class PlanTests(Fixture):
    """plan_split: группы, отказы и предупреждения в духе гейта."""

    def test_auto_groups_and_clean_plan(self):
        self.write("python/godot_tools/simplemod.py",
                   "def f1():\n    return 1\n\n\ndef f2():\n    return 2\n"
                   "\n\ndef f3():\n    return 3\n")
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/simplemod.py", target_lines=5)
        self.assertEqual(prepared["errors"], [])
        self.assertEqual(len(prepared["modules"]), 3)
        self.assertTrue(any("черновые" in message
                            for message in prepared["warnings"]))
        self.assertEqual([module["module"] for module in prepared["modules"]],
                         ["simplemod_part1", "simplemod_part2",
                          "simplemod_part3"])

    def test_demo_plan_structure(self):
        self.write("python/godot_tools/sawdemo.py", DEMO)
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/sawdemo.py", groups=GROUPS)
        self.assertEqual(prepared["errors"], [])
        self.assertEqual(len(prepared["warnings"]), 1)
        self.assertIn("_CACHE", prepared["warnings"][0])
        modules = {module["module"]: module for module in prepared["modules"]}
        self.assertIn("def alpha(", modules["sawdemo_part1"]["text"])
        self.assertIn("CONST = 10", modules["sawdemo_part1"]["text"])
        part2 = modules["sawdemo_part2"]["text"]
        self.assertIn("import json", part2)
        self.assertIn("from sawdemo_part1 import alpha", part2)
        facade = prepared["facade"]["text"]
        self.assertTrue(facade.startswith("# -*- coding: utf-8 -*-"))
        self.assertIn("from sawdemo_part1 import", facade)
        self.assertIn("__all__", facade)
        self.assertNotIn("def alpha(", facade)
        self.assertEqual(
            prepared["moved_names"],
            ["CONST", "_CACHE", "_helper", "alpha", "beta"])
        self.assertIsNotNone(prepared["refs"])
        self.assertEqual(prepared["refs"]["counts"]["import"], 0)

    def test_unknown_and_duplicate_symbols(self):
        self.write("python/godot_tools/sawdemo.py", DEMO)
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/sawdemo.py",
            groups=[{"module": "sawdemo_part1",
                     "symbols": ["alpha", "ghost"]},
                    {"module": "sawdemo_part2", "symbols": ["alpha"]}])
        joined = "\n".join(prepared["errors"])
        self.assertIn("не найден", joined)
        self.assertIn("дважды", joined)

    def test_existing_target_and_over_limit(self):
        self.write("python/godot_tools/bigmod.py",
                   "def big():\n" + "    x = 1\n" * 110 + "    return x\n")
        self.write("python/godot_tools/bigmod_part1.py", "# занято\n")
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/bigmod.py",
            groups=[{"module": "bigmod_part1", "symbols": ["big"]}])
        joined = "\n".join(prepared["errors"])
        self.assertIn("уже существует", joined)
        self.assertIn("больше лимита", joined)

    def test_near_limit_warning(self):
        self.write("python/godot_tools/warnmod.py",
                   "def mid():\n" + "    x = 1\n" * 70 + "    return x\n")
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/warnmod.py",
            groups=[{"module": "warnmod_part1", "symbols": ["mid"]}])
        self.assertIn("близко к лимиту", "\n".join(prepared["warnings"]))

    def test_core_duplicate_error_and_consumer_warning(self):
        self.write("python/godot_tools/sawdemo.py", DEMO)
        self.write("python/godot_tools/other_core.py",
                   "def alpha():\n    return 0\n")
        self.write("python/tools/consumer_mod.py",
                   "def beta():\n    return 0\n")
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/sawdemo.py", groups=GROUPS)
        joined_errors = "\n".join(prepared["errors"])
        joined_warnings = "\n".join(prepared["warnings"])
        self.assertIn("дубль из ядра", joined_errors)
        self.assertIn("other_core.py", joined_errors)
        self.assertIn("вне ядра", joined_warnings)
        self.assertIn("consumer_mod.py", joined_warnings)

    def test_cycle_and_leftover(self):
        self.write("python/godot_tools/cyclemod.py",
                   '"""Цикл."""\n\n\ndef ping():\n    return pong()\n'
                   "\n\ndef pong():\n    return ping()\n")
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/cyclemod.py",
            groups=[{"module": "cyclemod_part1", "symbols": ["ping"]},
                    {"module": "cyclemod_part2", "symbols": ["pong"]}])
        self.assertIn("по кругу", "\n".join(prepared["errors"]))

        self.write("python/godot_tools/leftovermod.py",
                   '"""Сирота."""\n\n\ndef caller():\n    return orphan()\n'
                   "\n\ndef orphan():\n    return 1\n")
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/leftovermod.py",
            groups=[{"module": "leftovermod_part1",
                     "symbols": ["caller"]}])
        self.assertIn("оставшиеся в фасаде", "\n".join(prepared["errors"]))
        self.assertIn("не перенесённые символы",
                      "\n".join(prepared["warnings"]))

    def test_shared_state_error(self):
        self.write("python/godot_tools/statemod.py",
                   '"""Общий state."""\n\n\nSTORE = {}\n\n\n'
                   "def put():\n    STORE['a'] = 1\n\n\n"
                   "def take():\n    return STORE.get('a')\n")
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/statemod.py",
            groups=[{"module": "statemod_part1",
                     "symbols": ["put", "STORE"]},
                    {"module": "statemod_part2", "symbols": ["take"]}])
        self.assertIn("нужен нескольким группам",
                      "\n".join(prepared["errors"]))

    def test_shared_state_in_own_module_is_allowed(self):
        """Просьбу guard-а «отдельным модулем» после выноса выполняем.

        state живёт в собственном модуле, потребители импортируют один
        общий объект — ошибка снимается, остаётся предупреждение.
        """
        self.write("python/godot_tools/statemod2.py",
                   '"""Общий state отдельным модулем."""\n\n\nSTORE = {}\n\n\n'
                   "def put():\n    STORE['a'] = 1\n\n\n"
                   "def take():\n    return STORE.get('a')\n")
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/statemod2.py",
            groups=[{"module": "statemod2_data", "symbols": ["STORE"]},
                    {"module": "statemod2_part1", "symbols": ["put"]},
                    {"module": "statemod2_part2", "symbols": ["take"]}])
        joined_errors = "\n".join(prepared["errors"])
        joined_warnings = "\n".join(prepared["warnings"])
        self.assertNotIn("нужен нескольким группам", joined_errors)
        self.assertIn("вынесен отдельным модулем", joined_warnings)

    def test_consumer_zone_warning(self):
        self.write("python/tools/toolmod.py",
                   '"""Проводка."""\n\n\ndef tool_one():\n    return 1\n')
        prepared = split_refactor.plan_split(
            self.addon, "python/tools/toolmod.py",
            groups=[{"module": "toolmod_part1",
                     "symbols": ["tool_one"]}])
        joined = "\n".join(prepared["warnings"])
        self.assertIn("зона", joined)
        self.assertIn("только проводка", joined)

    def test_patched_moved_attribute_warns(self):
        """Патч атрибута переезжающего символа — предупреждение в плане."""
        self.write("python/godot_tools/patchmod.py",
                   '"""Патчи."""\n\n\n'
                   "def patcher():\n    return 1\n\n\n"
                   "def helper():\n    return patcher()\n")
        self.write("python/tests/test_patch_usage.py",
                   "import patchmod\n\n\n"
                   "def inject():\n"
                   "    patchmod.patcher = None\n"
                   "    patchmod.absent = None\n")
        prepared = split_refactor.plan_split(
            self.addon, "python/godot_tools/patchmod.py",
            groups=[{"module": "patchmod_part1",
                     "symbols": ["patcher", "helper"]}])
        joined = "\n".join(prepared["warnings"])
        self.assertIn("patcher", joined)
        self.assertIn("test_patch_usage.py", joined)
        self.assertIn("не долетит", joined)
        # Патч имени, которого нет среди переезжающих, — не про нас.
        self.assertNotIn("absent", joined)
        self.assertEqual(prepared["errors"], [])


class ApplyTests(Fixture):
    """apply_prepared_split: модули, фасад-реэкспорт, шаги отказов."""

    def _plan_demo(self):
        self.write("python/godot_tools/sawdemo.py", DEMO)
        return split_refactor.plan_split(
            self.addon, "python/godot_tools/sawdemo.py", groups=GROUPS)

    def _import_demo(self):
        gt_dir = str(Path(self.addon, "python", "godot_tools"))
        sys.path.insert(0, gt_dir)
        self.addCleanup(self._drop_path, gt_dir)
        for name in ("sawdemo", "sawdemo_part1", "sawdemo_part2"):
            self.addCleanup(self._drop_module, name)
        return importlib.import_module("sawdemo")

    @staticmethod
    def _drop_path(path):
        while path in sys.path:
            sys.path.remove(path)

    @staticmethod
    def _drop_module(name):
        sys.modules.pop(name, None)

    def test_apply_writes_modules_and_facade_reexports(self):
        prepared = self._plan_demo()
        report = split_refactor.apply_prepared_split(prepared)
        self.assertEqual(report["written"],
                         ["python/godot_tools/sawdemo_part1.py",
                          "python/godot_tools/sawdemo_part2.py"])
        self.assertEqual(report["moved"], prepared["moved_names"])
        facade = self.read("python/godot_tools/sawdemo.py")
        self.assertNotIn("def alpha(", facade)
        demo = self._import_demo()
        self.assertEqual(demo.CONST, 10)
        self.assertEqual(demo.alpha(), 11)
        self.assertEqual(demo.beta(), 12)
        self.assertEqual(demo._helper(), 2)
        self.assertEqual(demo._CACHE["seen"], '{"calls": 1}')
        part1 = sys.modules["sawdemo_part1"]
        part2 = sys.modules["sawdemo_part2"]
        self.assertIs(demo.alpha, part1.alpha)
        self.assertIs(demo._CACHE, part2._CACHE)

    def test_prepared_survives_json_roundtrip(self):
        prepared = self._plan_demo()
        loaded = json.loads(json.dumps(prepared, ensure_ascii=False))
        report = split_refactor.apply_prepared_split(loaded)
        self.assertTrue(report["written"])
        self.assertIn("__all__", self.read("python/godot_tools/sawdemo.py"))

    def test_stale_donor_refused(self):
        prepared = self._plan_demo()
        self.write("python/godot_tools/sawdemo.py",
                   DEMO + "\n\ndef gamma():\n    return 3\n")
        with self.assertRaises(split_refactor.StaleSplitError):
            split_refactor.apply_prepared_split(prepared)

    def test_plan_errors_block_apply(self):
        prepared = self._plan_demo()
        prepared["errors"] = ["искусственная ошибка"]
        with self.assertRaises(split_refactor.SplitError):
            split_refactor.apply_prepared_split(prepared)


if __name__ == "__main__":
    unittest.main()
