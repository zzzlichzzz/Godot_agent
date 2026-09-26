# -*- coding: utf-8 -*-
"""Синтетические тесты п.1.3: свойства в ИНСТАНЦИРУЮЩИХ сценах.

Баг: поиск секций шёл только по ext_resource нужного скрипта, поэтому в
родительской сцене, где узел — это instance=ExtResource("player.tscn"),
скрипта в ext_resource нет: health = 50 оставалось, а скрипт становился
max_health. Значение переопределения терялось без единой ошибки.
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


PLAYER_SCRIPT = """extends Node2D
@export var health: int = 100

func take_damage(amount: int) -> void:
\thealth -= amount
"""

PLAYER_SCENE = (
    '[gd_scene load_steps=2 format=3]\n\n'
    '[ext_resource type="Script" path="res://src/player.gd" id="1_p"]\n\n'
    '[node name="Player" type="Node2D"]\n'
    'script = ExtResource("1_p")\n'
    'health = 100\n'
)


class InstancedScenes(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_inst_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/player.gd", PLAYER_SCRIPT)
        self._write("scenes/player.tscn", PLAYER_SCENE)
        self._reindex()

    def _reindex(self):
        ml_project_index.build_index(self.root)

    def _action(self):
        return {"action": "rename_symbol", "kind": "variable",
                "declaration": "res://src/player.gd:2",
                "old_name": "health", "new_name": "max_health"}

    def _write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def _read(self, rel):
        with open(os.path.join(self.root, *rel.split("/")), "r", encoding="utf-8") as handle:
            return handle.read()

    # --- 1.3.1 переопределение в инстанцирующей сцене ---
    def test_override_in_instancing_scene(self):
        self._write("scenes/level.tscn", (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="1_lvl"]\n\n'
            '[node name="Level" type="Node2D"]\n\n'
            '[node name="Player" parent="." instance=ExtResource("1_lvl")]\n'
            'health = 50\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("res://scenes/level.tscn", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("max_health = 50", self._read("scenes/level.tscn"))
        self.assertIn("max_health = 100", self._read("scenes/player.tscn"))

    # --- 1.3.2 переопределение в нескольких инстанцирующих сценах ---
    def test_overrides_in_several_instancing_scenes(self):
        for name in ("scenes/level1.tscn", "scenes/level2.tscn", "scenes/boss.tscn"):
            self._write(name, (
                '[gd_scene load_steps=2 format=3]\n\n'
                '[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="1_lvl"]\n\n'
                '[node name="Level" type="Node2D"]\n\n'
                '[node name="Player" parent="." instance=ExtResource("1_lvl")]\n'
                'health = 50\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        paths = [f["path"] for f in prepared["files"]]
        for name in ("res://scenes/level1.tscn", "res://scenes/level2.tscn",
                     "res://scenes/boss.tscn"):
            self.assertIn(name, paths)
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        for name in ("scenes/level1.tscn", "scenes/level2.tscn", "scenes/boss.tscn"):
            self.assertIn("max_health = 50", self._read(name))

    # --- 1.3.3 одноимённое свойство ДРУГОГО типа узла — трогать нельзя ---
    def test_same_named_property_of_other_node_type_is_untouched(self):
        self._write("src/enemy.gd", "extends Node2D\n@export var health: int = 10\n")
        self._write("scenes/enemy.tscn", (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://src/enemy.gd" id="1_e"]\n\n'
            '[node name="Enemy" type="Node2D"]\n'
            'script = ExtResource("1_e")\n'
            'health = 10\n'))
        self._write("scenes/level.tscn", (
            '[gd_scene load_steps=3 format=3]\n\n'
            '[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="1_lvl"]\n'
            '[ext_resource type="PackedScene" path="res://scenes/enemy.tscn" id="2_en"]\n\n'
            '[node name="Level" type="Node2D"]\n\n'
            '[node name="Player" parent="." instance=ExtResource("1_lvl")]\n'
            'health = 50\n\n'
            '[node name="Enemy" parent="." instance=ExtResource("2_en")]\n'
            'health = 5\n'))
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        level = self._read("scenes/level.tscn")
        self.assertIn("max_health = 50", level)
        self.assertIn("health = 5", level)
        self.assertIn("health = 10", self._read("scenes/enemy.tscn"))

    # --- 1.3.4 вложенная инстанциация: сцена инстанцирует сцену, та — третью ---
    def test_nested_instancing_chain(self):
        self._write("scenes/wave.tscn", (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="1_w"]\n\n'
            '[node name="Wave" type="Node2D"]\n\n'
            '[node name="Player" parent="." instance=ExtResource("1_w")]\n'
            'health = 20\n'))
        self._write("scenes/level.tscn", (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="PackedScene" path="res://scenes/wave.tscn" id="1_lvl"]\n\n'
            '[node name="Level" type="Node2D"]\n\n'
            '[node name="Wave" parent="." instance=ExtResource("1_lvl")]\n'
            'health = 10\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        paths = [f["path"] for f in prepared["files"]]
        self.assertIn("res://scenes/wave.tscn", paths)
        self.assertIn("res://scenes/level.tscn", paths)
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("max_health = 20", self._read("scenes/wave.tscn"))
        self.assertIn("max_health = 10", self._read("scenes/level.tscn"))
    # --- Аудит 1.3: циклическое инстанцирование не должно зависать ---
    # Godot такие сцены не грузит, но обход не имеет на этом права зависнуть.
    # Гарантия: операция завершается, и ни один изменённый файл не остаётся
    # в состоянии «наполовину переименовано».
    def test_cyclic_instancing_does_not_hang(self):
        self._write("scenes/a.tscn", (
            '[gd_scene load_steps=3 format=3]\n\n'
            '[ext_resource type="PackedScene" path="res://scenes/b.tscn" id="1_b"]\n'
            '[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="2_p"]\n\n'
            '[node name="A" type="Node2D"]\n\n'
            '[node name="B" parent="." instance=ExtResource("1_b")]\n'
            'health = 1\n\n'
            '[node name="Player" parent="." instance=ExtResource("2_p")]\n'
            'health = 2\n'))
        self._write("scenes/b.tscn", (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="PackedScene" path="res://scenes/a.tscn" id="1_a"]\n\n'
            '[node name="B" type="Node2D"]\n\n'
            '[node name="A" parent="." instance=ExtResource("1_a")]\n'
            'health = 3\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        for item in prepared["files"]:
            if not item["path"].endswith(".tscn"):
                continue
            after = item["after_bytes"].decode("utf-8-sig")
            self.assertNotIn("\nhealth = ", after)
            self.assertIn("max_health = ", after)

    # --- Аудит 1.3: вложенный инстанцированный узел (parent != ".") ---
    def test_nested_instanced_node_override(self):
        self._write("scenes/level.tscn", (
            '[gd_scene load_steps=3 format=3]\n\n'
            '[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="1_lvl"]\n\n'
            '[node name="Level" type="Node2D"]\n\n'
            '[node name="Spawns" type="Node2D" parent="."]\n\n'
            '[node name="Player" parent="Spawns" instance=ExtResource("1_lvl")]\n'
            'health = 7\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("res://scenes/level.tscn", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("max_health = 7", self._read("scenes/level.tscn"))

    # --- Аудит 1.3: .tres-ресурс на базе скрипта не ломается обходом ---
    def test_tres_resource_still_supported(self):
        self._write("items/potion.tres", (
            '[gd_resource type="Resource" load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://src/player.gd" id="1_p"]\n\n'
            '[resource]\n'
            'script = ExtResource("1_p")\n'
            'health = 99\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("res://items/potion.tres", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("max_health = 99", self._read("items/potion.tres"))


if __name__ == "__main__":
    unittest.main()



if __name__ == "__main__":
    unittest.main()

