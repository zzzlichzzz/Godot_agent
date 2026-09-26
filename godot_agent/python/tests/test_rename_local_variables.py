# -*- coding: utf-8 -*-
"""Синтетические тесты п.3.4: локальные переменные внутри функций.

Раньше отказ шёл сразу: «Переименование локальных переменных внутри функций
пока не поддерживается безопасно». Теперь поддерживается, но со всеми
инвариантами: тень параметра не трогается, одноимённые локальные переменные
в ДРУГИХ функциях — другая сущность, откат работает.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

from godot_tools import symbol_refactor
from minilich import ml_project_index


SCRIPT = """extends Node

func compute() -> int:
\tvar total = 0
\ttotal += 1
\treturn total
"""


class LocalVariables(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_local_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/unit.gd", SCRIPT)
        self._reindex()

    def _write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def _read(self, rel):
        with open(os.path.join(self.root, *rel.split("/")), "r", encoding="utf-8") as handle:
            return handle.read()

    def _reindex(self):
        ml_project_index.build_index(self.root)

    def _action(self, line=4, old="total", new="sum_all"):
        return {"action": "rename_symbol", "kind": "variable",
                "declaration": "res://src/unit.gd:%d" % line,
                "old_name": old, "new_name": new}

    def _rename(self, line=4, old="total", new="sum_all"):
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action(line, old, new))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        return self._read("src/unit.gd")

    # --- 3.4.1 объявление и все ссылки внутри функции ---
    def test_local_variable_rename(self):
        unit = self._rename()
        self.assertIn("var sum_all = 0", unit)
        self.assertIn("sum_all += 1", unit)
        self.assertIn("return sum_all", unit)
        self.assertNotIn("total", unit)

    # --- 3.4.2 одноимённая локальная переменная в ДРУГОЙ функции не трогается ---
    def test_same_name_in_other_function_is_untouched(self):
        self._write("src/unit.gd", SCRIPT + """
func other() -> int:
\tvar total = 9
\treturn total
""")
        self._reindex()
        unit = self._rename()
        self.assertIn("var sum_all = 0", unit)
        self.assertIn("var total = 9", unit)

    # --- 3.4.3 тень параметра не трогается ---
    def test_parameter_shadowing_is_untouched(self):
        self._write("src/unit.gd", SCRIPT + """
func with_param(total: int) -> int:
\treturn total
""")
        self._reindex()
        unit = self._rename()
        self.assertIn("func with_param(total: int) -> int:", unit)
        self.assertIn("\treturn total", unit)
        self.assertIn("var sum_all = 0", unit)

    # --- 3.4.4 одноимённый член скрипта не трогается ---
    def test_member_variable_is_untouched(self):
        # SCRIPT уже начинается с extends Node, поэтому дописываем только
        # член скрипта: 1 extends, 2 пусто, 3 var total, 4 пусто, 5 func.
        self._write("src/unit.gd", "var total = 5\n\n" + SCRIPT)
        self._reindex()
        unit = self._rename(line=6)
        self.assertIn("var total = 5", unit)
        self.assertIn("var sum_all = 0", unit)

    # --- 3.4.5 коллизия в той же функции блокирует ---
    def test_collision_in_same_function_is_refused(self):
        self._write("src/unit.gd", SCRIPT.replace(
            "\treturn total", "\tvar sum_all = 2\n\treturn total"))
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("уже объявлено", str(ctx.exception))
        self.assertIn("var total = 0", self._read("src/unit.gd"))

    # --- Аудит 3.4: локальная переменная НЕ трогает .tscn ---
    def test_local_variable_does_not_touch_scene(self):
        self._write("src/other.gd", "extends Node2D\n@export var total: int = 3\n")
        self._write("scenes/other.tscn", (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://src/other.gd" id="1_o"]\n\n'
            '[node name="Other" type="Node2D"]\n'
            'script = ExtResource("1_o")\n'
            'total = 8\n'))
        self._reindex()
        self._rename()
        self.assertIn("total = 8", self._read("scenes/other.tscn"))
        self.assertIn("@export var total: int = 3", self._read("src/other.gd"))

    # --- Аудит 3.4: откат возвращает исходное имя ---
    def test_rollback_restores_local_variable(self):
        import history_manager
        before = self._read("src/unit.gd")
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        result = symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("sum_all", self._read("src/unit.gd"))
        ok, _msg, _force, _paths, _diff = history_manager.rollback_entry(
            self.root, result["entry_id"])
        self.assertTrue(ok)
        self.assertEqual(self._read("src/unit.gd"), before)

    # --- Аудит 3.4: локальная переменная в подклассе ---
    def test_local_variable_in_subclass(self):
        self._write("src/base.gd", "class_name Base\nextends Node\n")
        self._write("src/unit.gd", SCRIPT.replace("extends Node", "extends Base"))
        self._reindex()
        unit = self._rename()
        self.assertIn("var sum_all = 0", unit)


if __name__ == "__main__":
    unittest.main()
