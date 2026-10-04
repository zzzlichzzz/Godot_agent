# -*- coding: utf-8 -*-
"""Синтетические тесты п.2.1: типизированные коллекции Godot 4.

Баг: контекст type определялся только по prev in (":", "->", "extends",
"as", "is"). В типизированных коллекциях имя класса стоит в квадратных
скобках: Array[Player] -> блок. Это норма Godot 4, то есть блокировался
почти любой типизированный проект.
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


class TypedCollections(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_typed_")
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

    def _action(self, new="Avatar"):
        return {"action": "rename_symbol", "kind": "class_name",
                "declaration": "res://src/player.gd:1",
                "old_name": "Player", "new_name": new}

    def _rename(self, code, new="Avatar"):
        self._write("src/user.gd", code)
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action(new))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        return self._read("src/user.gd")
    # --- 2.1.1 Array[Player] ---
    def test_array_of_class(self):
        after = self._rename("extends Node\n\nvar units: Array[Player] = []\n")
        self.assertIn("var units: Array[Avatar] = []", after)

    # --- 2.1.2 Dictionary[String, Player] ---
    def test_dictionary_of_class(self):
        after = self._rename(
            "extends Node\n\nvar roster: Dictionary[String, Player] = {}\n")
        self.assertIn("Dictionary[String, Avatar]", after)

    # --- 2.1.3 вложенные Array[Array[Player]] ---
    def test_nested_array_of_class(self):
        after = self._rename(
            "extends Node\n\nvar grid: Array[Array[Player]] = []\n")
        self.assertIn("Array[Array[Avatar]]", after)

    # --- 2.1.4 var x: Array[Player] = [] с присваиванием ---
    def test_typed_array_with_literal_value(self):
        after = self._rename(
            "extends Node\n\nvar spawn: Array[Player] = []\n\n"
            "func run() -> void:\n\tspawn.append(null)\n")
        self.assertIn("Array[Avatar]", after)
        self.assertIn("spawn.append(null)", after)

    # --- 2.1.5 возвращаемый тип -> Array[Player] ---
    def test_return_type_array(self):
        after = self._rename(
            "extends Node\n\nfunc all() -> Array[Player]:\n\treturn []\n")
        self.assertIn("-> Array[Avatar]", after)

    # --- 2.1.6 is not Player / is Player должны работать как типы ---
    def test_is_not_type_check(self):
        after = self._rename(
            "extends Node\n\nfunc check(node: Node) -> bool:\n"
            "\treturn not node is Player\n")
        self.assertIn("not node is Avatar", after)

    # --- 2.1.7 PackedStringArray-подобные НЕ должны ломаться ---
    def test_unrelated_brackets_not_treated_as_type(self):
        after = self._rename(
            "extends Node\n\nvar plain: Array = []\n\n"
            "func run() -> void:\n\tvar data = [1, 2, 3]\n\tprint(data)\n")
        self.assertIn("var plain: Array = []", after)
        self.assertIn("var data = [1, 2, 3]", after)

    # --- Аудит 2.1: старая проверка keyword/property не должна ломаться ---
    def test_property_named_like_keyword_in_brackets(self):
        after = self._rename(
            "extends Node\n\nvar index: Dictionary[String, int] = {}\n\n"
            "func run() -> void:\n\tindex.clear()\n")
        self.assertIn("Dictionary[String, int]", after)
        self.assertIn("index.clear()", after)

    # --- Аудит 2.1: индексация массива players[0] НЕ должна стать типом ---
    def test_array_index_access_is_not_a_type(self):
        after = self._rename(
            "extends Node\n\nvar players: Array = []\n\n"
            "func first() -> Node:\n\treturn players[0]\n")
        self.assertIn("return players[0]", after)

    # --- Аудит 2.1: чужой класс в скобках не переименовывается ---
    def test_foreign_class_in_brackets_does_not_rename(self):
        self._write("src/user.gd",
                    "extends Node\n\nvar ids: Dictionary[String, Node] = {}\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("Dictionary[String, Node]", self._read("src/user.gd"))

    # --- Аудит 2.1: вызов конструктора в скобках [Player.new()] ---
    def test_new_call_in_brackets(self):
        after = self._rename(
            "extends Node\n\nfunc make() -> Array:\n\treturn [Player.new()]\n")
        self.assertIn("[Avatar.new()]", after)

    # --- Аудит 2.1: сигнатура с типизированными параметрами ---
    def test_typed_parameter_signature(self):
        after = self._rename(
            "extends Node\n\n"
            "func build(roster: Dictionary[String, Player]) -> Array[Player]:\n"
            "\treturn []\n")
        self.assertIn("Dictionary[String, Avatar]", after)
        self.assertIn("-> Array[Avatar]", after)


if __name__ == "__main__":
    unittest.main()
