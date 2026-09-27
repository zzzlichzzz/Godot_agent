# -*- coding: utf-8 -*-
"""Критерий готовности: print("ClassName") не блокирует переименование класса,
а ClassDB.instantiate("ClassName") — блокирует, с понятным сообщением.

Тот же контракт проверяется и в test_rename_string_guard.py; здесь он
зафиксирован отдельным набором, потому что это критерий приёмки, а не
частный случай реализации.
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


PLAYER = "class_name Player\nextends Node2D\n\nfunc hit() -> void:\n\tpass\n"


class StringReferenceCriterion(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="crit_string_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/player.gd", PLAYER)
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

    def _action(self, **extra):
        action = {"action": "rename_symbol", "kind": "class_name",
                  "declaration": "res://src/player.gd:1",
                  "old_name": "Player", "new_name": "Avatar"}
        action.update(extra)
        return action

    # --- критерий 3a: print("Player") — обычный текст, не блокирует ---
    def test_print_does_not_block(self):
        self._write("src/a.gd", "extends Node\n\nfunc log() -> void:\n\tprint(\"Player\")\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        self.assertIn('print("Player")', self._read("src/a.gd"))

    # --- критерий 3b: ClassDB.instantiate("Player") блокирует ---
    def test_classdb_instantiate_blocks(self):
        self._write("src/b.gd", "extends Node\n\nfunc make() -> Node:\n"
                                "\treturn ClassDB.instantiate(\"Player\")\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        # Отказ не должен оставить проект изменённым «наполовину».
        self.assertIn("class_name Player", self._read("src/player.gd"))
        self.assertNotIn("class_name Avatar", self._read("src/player.gd"))

    # --- критерий 3c: сообщение объясняет, что делать ---
    def test_refusal_message_is_actionable(self):
        self._write("src/b.gd", "extends Node\n\nfunc make() -> Node:\n"
                                "\treturn ClassDB.instantiate(\"Player\")\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        message = str(ctx.exception)
        self.assertIn("ClassDB.instantiate", message)
        self.assertIn("src/b.gd", message)
        # Подсказка: что именно сделать дальше.
        self.assertTrue("probable" in message or "вручную" in message, message)

    # --- критерий 3d: probable — осознанный выход, риск виден, но не блокирует ---
    def test_probable_mode_accepts_and_reports(self):
        self._write("src/b.gd", "extends Node\n\nfunc make() -> Node:\n"
                                "\treturn ClassDB.instantiate(\"Player\")\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action(mode="probable"))
        self.assertTrue(prepared["dynamic_references"])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        # Строка осталась как была — её нельзя доказать.
        self.assertIn('ClassDB.instantiate("Player")', self._read("src/b.gd"))

    # --- критерий 3e: set() по имени — тоже блокирует в strict ---
    def test_set_by_name_blocks(self):
        self._write("src/c.gd", "extends Node\n\nfunc apply(n: Node) -> void:\n"
                                "\tn.set(\"Player\", 5)\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("set()", str(ctx.exception))

    # --- критерий 3f: комментарий и присваивание строки не блокируют ---
    def test_comment_and_assignment_do_not_block(self):
        self._write("src/d.gd", "extends Node\n\n"
                                "# Player тут только в комментарии\n"
                                "func run() -> void:\n"
                                "\tvar label = \"Player\"\n\tprint(label)\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))


if __name__ == "__main__":
    unittest.main()
