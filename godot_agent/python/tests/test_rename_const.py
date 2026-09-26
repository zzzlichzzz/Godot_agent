# -*- coding: utf-8 -*-
"""Синтетические тесты п.3.1: переименование констант (const).

KINDS не содержал const, поэтому любая константа проекта была неприкосновенна
для rename_symbol. Здесь проверяем, что const переименовывается вместе с
ссылками и что те же гарантии (тени, коллизии, откат) работают.
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


UNIT = """class_name Unit
extends Node

const MAX_HP = 100

func hit() -> int:
\treturn MAX_HP
"""


class ConstRename(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_const_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/unit.gd", UNIT)
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

    def _action(self, new="MAX_HEALTH", old="MAX_HP"):
        return {"action": "rename_symbol", "kind": "const",
                "declaration": "res://src/unit.gd:4",
                "old_name": old, "new_name": new}

    def _rename(self, new="MAX_HEALTH", old="MAX_HP"):
        prepared = symbol_refactor.prepare_rename(self.root, self._action(new, old))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        return prepared

    # --- 3.1.1 объявление + ссылки в том же файле ---
    def test_const_declaration_and_reference(self):
        self._rename()
        unit = self._read("src/unit.gd")
        self.assertIn("const MAX_HEALTH = 100", unit)
        self.assertIn("return MAX_HEALTH", unit)
        self.assertNotIn("MAX_HP", unit)

    # --- 3.1.2 ссылки в других файлах (через class_name) ---
    def test_references_from_other_files(self):
        self._write("src/arena.gd", """extends Node

func start() -> int:
\treturn Unit.MAX_HP
""")
        self._reindex()
        self._rename()
        self.assertIn("Unit.MAX_HEALTH", self._read("src/arena.gd"))
        self.assertIn("const MAX_HEALTH = 100", self._read("src/unit.gd"))

    # --- 3.1.3 тень: локальная переменная с тем же именем не трогается ---
    def test_shadowed_local_name_is_untouched(self):
        self._write("src/unit.gd", UNIT + """
func shadow() -> int:
\tvar MAX_HP = 5
\treturn MAX_HP
""")
        self._reindex()
        self._rename()
        unit = self._read("src/unit.gd")
        self.assertIn("const MAX_HEALTH = 100", unit)
        self.assertIn("var MAX_HP = 5", unit)
        self.assertIn("return MAX_HP", unit)

    # --- 3.1.4 коллизия в том же скрипте блокирует ---
    def test_collision_in_same_script_is_refused(self):
        self._write("src/unit.gd", UNIT + "\nconst MAX_HEALTH = 1\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("уже объявлено", str(ctx.exception))
        self.assertIn("const MAX_HP = 100", self._read("src/unit.gd"))

    # --- 3.1.5 откат возвращает исходное имя ---
    def test_rollback_restores_const(self):
        before = self._read("src/unit.gd")
        import history_manager
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        result = symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("MAX_HEALTH", self._read("src/unit.gd"))
        ok, _message, _force, _paths, _diff = history_manager.rollback_entry(
            self.root, result["entry_id"])
        self.assertTrue(ok)
        self.assertEqual(self._read("src/unit.gd"), before)

    # --- Аудит 3.1: подкласс СВОЮ константу — другая сущность, отказ ---
    # Tank.MAX_HP и Unit.MAX_HP — разные константы. Переименовывать одну,
    # оставляя вторую, бессмысленно, поэтому такое перекрытие блокирует.
    def test_subclass_redeclaring_const_is_refused(self):
        self._write("src/tank.gd", """extends Unit

const MAX_HP = 200

func cap() -> int:
\treturn MAX_HP
""")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("tank.gd", str(ctx.exception))
        self.assertIn("const MAX_HP = 100", self._read("src/unit.gd"))
        self.assertIn("const MAX_HP = 200", self._read("src/tank.gd"))

    # --- Аудит 3.1: подкласс использует НАСЛЕДОВАННУЮ константу ---
    def test_subclass_inherited_const_reference_is_renamed(self):
        self._write("src/tank.gd", """extends Unit

func cap() -> int:
\treturn MAX_HP
""")
        self._reindex()
        self._rename()
        self.assertIn("return MAX_HEALTH", self._read("src/tank.gd"))
        self.assertIn("const MAX_HEALTH = 100", self._read("src/unit.gd"))

    # --- Аудит 3.1: префиксное имя НЕ должно затрагиваться ---
    def test_prefixed_name_is_untouched(self):
        self._write("src/unit.gd", UNIT + "\nconst MAX_HP_EXTRA = 7\n")
        self._reindex()
        self._rename()
        self.assertIn("const MAX_HP_EXTRA = 7", self._read("src/unit.gd"))

    # --- Аудит 3.1: ключевое слово/строка не трогаются ---
    def test_string_and_comment_untouched(self):
        self._write("src/unit.gd", """class_name Unit
extends Node

const MAX_HP = 100

func label() -> String:
\t# MAX_HP is documented here
\treturn "MAX_HP"
""")
        self._reindex()
        self._rename()
        unit = self._read("src/unit.gd")
        self.assertIn("# MAX_HP is documented here", unit)
        self.assertIn('return "MAX_HP"', unit)
        self.assertIn("const MAX_HEALTH = 100", unit)

    # --- Аудит 3.1: свойство того же имени в .tscn НЕ меняется ---
    def test_scene_property_not_affected(self):
        self._write("src/other.gd", "extends Node2D\n@export var MAX_HP: int = 5\n")
        self._write("scenes/other.tscn", (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://src/other.gd" id="1_o"]\n\n'
            '[node name="Other" type="Node2D"]\n'
            'script = ExtResource("1_o")\n'
            'MAX_HP = 9\n'))
        self._reindex()
        self._rename()
        self.assertIn("MAX_HP = 9", self._read("scenes/other.tscn"))


if __name__ == "__main__":
    unittest.main()

    def _rename(self, new="MAX_HEALTH", old="MAX_HP"):
        prepared = symbol_refactor.prepare_rename(self.root, self._action(new, old))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        return prepared

