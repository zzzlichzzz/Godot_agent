# -*- coding: utf-8 -*-
"""Синтетические тесты п.3.3: члены вложенных классов.

Раньше члены вложенных классов отклонялись outright: «Переименование членов
вложенных классов пока не поддерживается безопасно». Правило должно быть
строгим: переименовываем только то, что реально принадлежит вложенному
классу, и не трогаем одноимённые члены внешнего скрипта.
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


SCRIPT = """class_name Unit
extends Node

class Inner:
\tsignal died

\tfunc hit() -> void:
\t\tdied.emit()
\t\tself.hit()
\t\thit()

func outer() -> void:
\tpass
"""


class NestedClassMembers(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_nested_")
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

    def _action(self, kind="function", line=7, old="hit", new="strike"):
        return {"action": "rename_symbol", "kind": kind,
                "declaration": "res://src/unit.gd:%d" % line,
                "old_name": old, "new_name": new}

    def _rename(self, kind="function", line=7, old="hit", new="strike"):
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action(kind, line, old, new))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        return self._read("src/unit.gd")

    # --- 3.3.1 функция вложенного класса + self/голый вызовы ---
    def test_nested_method_rename(self):
        unit = self._rename()
        self.assertIn("func strike() -> void:", unit)
        self.assertIn("self.strike()", unit)
        self.assertIn("\t\tstrike()", unit)
        self.assertNotIn("func hit()", unit)

    # --- 3.3.2 сигнал вложенного класса ---
    def test_nested_signal_rename(self):
        unit = self._rename("signal", 5, "died", "expired")
        self.assertIn("signal expired", unit)
        self.assertIn("expired.emit()", unit)

    # --- 3.3.3 одноимённый член ВНЕШНЕГО скрипта не трогается ---
    def test_outer_same_named_method_is_untouched(self):
        self._write("src/unit.gd", SCRIPT.replace(
            "func outer() -> void:\n\tpass",
            "func outer() -> void:\n\thit()\n\nfunc hit() -> void:\n\tpass"))
        self._reindex()
        unit = self._rename()
        self.assertIn("func strike() -> void:", unit)
        # Внешний hit и его вызов остались нетронутыми.
        self.assertIn("func hit() -> void:", unit)
        self.assertIn("\thit()", unit)

    # --- 3.3.4 коллизия: член с новым именем внутри того же вложенного класса ---
    def test_collision_in_same_nested_class_is_refused(self):
        self._write("src/unit.gd", SCRIPT.replace(
            "\t\thit()\n", "\t\thit()\n\n\tfunc strike() -> void:\n\t\tpass\n"))
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("уже объявлено", str(ctx.exception))
        self.assertIn("func hit() -> void:", self._read("src/unit.gd"))

    # --- Аудит 3.3: глубокая вложенность (класс в классе) ---
    def test_deeply_nested_method_rename(self):
        self._write("src/unit.gd", """class_name Unit
extends Node

class Outer:
\tclass Deep:
\t\tfunc hit() -> void:
\t\t\tpass
""")
        self._reindex()
        unit = self._rename(line=6)
        self.assertIn("func strike() -> void:", unit)

    # --- Аудит 3.3: откат возвращает исходные имена ---
    def test_rollback_restores_nested_member(self):
        import history_manager
        before = self._read("src/unit.gd")
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        result = symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("func strike()", self._read("src/unit.gd"))
        ok, _msg, _force, _paths, _diff = history_manager.rollback_entry(
            self.root, result["entry_id"])
        self.assertTrue(ok)
        self.assertEqual(self._read("src/unit.gd"), before)

    # --- Аудит 3.3: класс внутри функции по-прежнему недоступен ---
    def test_class_inside_function_still_refused(self):
        self._write("src/unit.gd", """class_name Unit
extends Node

func build() -> void:
\tclass Local:
\t\tfunc hit() -> void:
\t\t\tpass
""")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, self._action(line=7))


if __name__ == "__main__":
    unittest.main()
