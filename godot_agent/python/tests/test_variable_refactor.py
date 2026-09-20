# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Comprehensive unit tests for variable and @export property refactoring."""

import os
import shutil
import tempfile
import unittest

from godot_tools import symbol_refactor
from minilich import ml_project_index


class TestVariableRefactor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="agent-var-test-")
        self.project_root = self.temp_dir
        # Create minimal project.godot
        with open(os.path.join(self.project_root, "project.godot"), "w", encoding="utf-8") as f:
            f.write('config_version=5\n[application]\nconfig/name="VarTest"\n')

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_file(self, rel_path, content):
        full = os.path.join(self.project_root, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return full

    def _read_file(self, rel_path):
        full = os.path.join(self.project_root, rel_path)
        with open(full, "r", encoding="utf-8") as f:
            return f.read()

    def test_simple_variable_rename(self):
        code = (
            "extends CharacterBody2D\n"
            "var speed = 100\n"
            "func _ready():\n"
            "    speed += 10\n"
            "    self.speed = 200\n"
        )
        self._write_file("player.gd", code)

        action = {
            "action": "rename_symbol",
            "kind": "variable",
            "declaration": "res://player.gd:2",
            "old_name": "speed",
            "new_name": "move_speed",
        }
        prepared = symbol_refactor.prepare_rename(self.project_root, action)
        self.assertEqual(len(prepared["files"]), 1)
        self.assertEqual(prepared["reference_count"], 2)

        symbol_refactor.apply_prepared_rename(self.project_root, prepared)
        after = self._read_file("player.gd")
        self.assertIn("var move_speed = 100", after)
        self.assertIn("move_speed += 10", after)
        self.assertIn("self.move_speed = 200", after)
        self.assertNotIn("var speed", after)
        self.assertNotIn("self.speed", after)

    def test_export_variable_with_tscn(self):
        code = (
            "extends CharacterBody2D\n"
            "@export var health: int = 100\n"
            "func take_damage(amount: int):\n"
            "    health -= amount\n"
        )
        tscn = (
            '[gd_scene format=3 uid="uid://test1234"]\n\n'
            '[ext_resource type="Script" path="res://player.gd" id="1_plr"]\n\n'
            '[node name="Player" type="CharacterBody2D"]\n'
            'script = ExtResource("1_plr")\n'
            'health = 42\n'
        )
        self._write_file("player.gd", code)
        self._write_file("player.tscn", tscn)

        action = {
            "action": "rename_symbol",
            "kind": "variable",
            "declaration": "res://player.gd:2",
            "old_name": "health",
            "new_name": "current_health",
        }
        prepared = symbol_refactor.prepare_rename(self.project_root, action)
        paths = [f["path"] for f in prepared["files"]]
        self.assertIn("res://player.gd", paths)
        self.assertIn("res://player.tscn", paths)

        symbol_refactor.apply_prepared_rename(self.project_root, prepared)
        after_gd = self._read_file("player.gd")
        after_tscn = self._read_file("player.tscn")

        self.assertIn("@export var current_health: int = 100", after_gd)
        self.assertIn("current_health -= amount", after_gd)
        self.assertIn("current_health = 42", after_tscn)
        self.assertNotIn("\nhealth = 42", after_tscn)

    def test_export_variable_with_tres(self):
        code = (
            "extends Resource\n"
            "@export var item_value: int = 10\n"
        )
        tres = (
            '[gd_resource type="Resource" load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://item_data.gd" id="1_item"]\n\n'
            '[resource]\n'
            'script = ExtResource("1_item")\n'
            'item_value = 99\n'
        )
        self._write_file("item_data.gd", code)
        self._write_file("potion.tres", tres)

        action = {
            "action": "rename_symbol",
            "kind": "variable",
            "declaration": "res://item_data.gd:2",
            "old_name": "item_value",
            "new_name": "gold_value",
        }
        prepared = symbol_refactor.prepare_rename(self.project_root, action)
        paths = [f["path"] for f in prepared["files"]]
        self.assertIn("res://item_data.gd", paths)
        self.assertIn("res://potion.tres", paths)

        symbol_refactor.apply_prepared_rename(self.project_root, prepared)
        after_tres = self._read_file("potion.tres")
        self.assertIn("gold_value = 99", after_tres)
        self.assertNotIn("item_value = 99", after_tres)

    def test_inheritance_subclass_rename(self):
        base_code = (
            "class_name BaseUnit\n"
            "extends Node2D\n"
            "var max_hp = 50\n"
            "func heal():\n"
            "    max_hp += 10\n"
        )
        hero_code = (
            "extends BaseUnit\n"
            "func buff():\n"
            "    max_hp += 20\n"
            "    self.max_hp = 100\n"
        )
        self._write_file("base_unit.gd", base_code)
        self._write_file("hero.gd", hero_code)

        action = {
            "action": "rename_symbol",
            "kind": "variable",
            "declaration": "res://base_unit.gd:3",
            "old_name": "max_hp",
            "new_name": "maximum_hp",
        }
        prepared = symbol_refactor.prepare_rename(self.project_root, action)
        paths = [f["path"] for f in prepared["files"]]
        self.assertIn("res://base_unit.gd", paths)
        self.assertIn("res://hero.gd", paths)

        symbol_refactor.apply_prepared_rename(self.project_root, prepared)
        after_base = self._read_file("base_unit.gd")
        after_hero = self._read_file("hero.gd")

        self.assertIn("var maximum_hp = 50", after_base)
        self.assertIn("maximum_hp += 10", after_base)
        self.assertIn("maximum_hp += 20", after_hero)
        self.assertIn("self.maximum_hp = 100", after_hero)

    def test_subclass_override_variable(self):
        parent_code = (
            "extends Node\n"
            "var score = 0\n"
        )
        child_code = (
            'extends "res://parent.gd"\n'
            "var score = 10\n"
            "func add():\n"
            "    score += 1\n"
        )
        self._write_file("parent.gd", parent_code)
        self._write_file("child.gd", child_code)

        action = {
            "action": "rename_symbol",
            "kind": "variable",
            "declaration": "res://parent.gd:2",
            "old_name": "score",
            "new_name": "total_score",
        }
        prepared = symbol_refactor.prepare_rename(self.project_root, action)
        paths = [f["path"] for f in prepared["files"]]
        self.assertIn("res://parent.gd", paths)
        self.assertIn("res://child.gd", paths)

        symbol_refactor.apply_prepared_rename(self.project_root, prepared)
        after_parent = self._read_file("parent.gd")
        after_child = self._read_file("child.gd")

        self.assertIn("var total_score = 0", after_parent)
        self.assertIn("var total_score = 10", after_child)
        self.assertIn("total_score += 1", after_child)

    def test_shadowing_protection(self):
        code = (
            "extends Node\n"
            "var speed = 10\n"
            "func set_speed(speed: int):\n"
            "    print(speed)\n"
            "func run():\n"
            "    speed = 20\n"
        )
        self._write_file("player.gd", code)

        action = {
            "action": "rename_symbol",
            "kind": "variable",
            "declaration": "res://player.gd:2",
            "old_name": "speed",
            "new_name": "velocity",
        }
        prepared = symbol_refactor.prepare_rename(self.project_root, action)
        symbol_refactor.apply_prepared_rename(self.project_root, prepared)

        after = self._read_file("player.gd")
        self.assertIn("var velocity = 10", after)
        self.assertIn("velocity = 20", after)
        # Parameter and local usage in set_speed must NOT be touched
        self.assertIn("func set_speed(speed: int):", after)
        self.assertIn("print(speed)", after)

    def test_collision_rejection(self):
        code = (
            "extends Node\n"
            "var speed = 10\n"
            "var velocity = 20\n"
        )
        self._write_file("player.gd", code)

        action = {
            "action": "rename_symbol",
            "kind": "variable",
            "declaration": "res://player.gd:2",
            "old_name": "speed",
            "new_name": "velocity",
        }
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.project_root, action)
        self.assertIn("уже объявлено", str(ctx.exception))

    def test_subclass_collision_rejection(self):
        parent_code = (
            "class_name ParentUnit\n"
            "extends Node\n"
            "var speed = 10\n"
        )
        child_code = (
            "extends ParentUnit\n"
            "var velocity = 20\n"
        )
        self._write_file("parent.gd", parent_code)
        self._write_file("child.gd", child_code)

        action = {
            "action": "rename_symbol",
            "kind": "variable",
            "declaration": "res://parent.gd:3",
            "old_name": "speed",
            "new_name": "velocity",
        }
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.project_root, action)
        self.assertIn("уже объявлен", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
