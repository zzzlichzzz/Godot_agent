# -*- coding: utf-8 -*-
"""Синтетические тесты п.1.2: связи сцен [connection] при rename_symbol.

Баг: _collect_scene_property_edits вызывался только для kind == "variable"
и правил только строки-свойства. [connection signal="died" ... method=
"_on_died"] оставался со старыми именами — Godot теряет связь молча,
операция рапортует «успешно».
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


SCRIPT_WITH_SIGNAL = """extends Node
signal died

func kill() -> void:
\tdied.emit()


func _on_died() -> void:
\tprint("dead")
"""


class SceneConnections(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_conn_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/turret.gd", SCRIPT_WITH_SIGNAL)
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

    def _signal_action(self):
        return {"action": "rename_symbol", "kind": "signal",
                "declaration": "res://src/turret.gd:2",
                "old_name": "died", "new_name": "was_destroyed"}

    def _method_action(self):
        return {"action": "rename_symbol", "kind": "function",
                "declaration": "res://src/turret.gd:8",
                "old_name": "_on_died", "new_name": "_on_was_destroyed"}

    # --- 1.2.1 сигнал + метод обработчика в одной сцене ---
    def test_signal_and_method_rename_updates_connection(self):
        self._write("scenes/main.tscn", (
            '[gd_scene format=3]\n\n'
            '[ext_resource type="Script" path="res://src/turret.gd" id="1_t"]\n\n'
            '[node name="Turret" type="Node2D"]\n'
            'script = ExtResource("1_t")\n\n'
            '[connection signal="died" from="." to="." method="_on_died"]\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._signal_action())
        self.assertIn("res://scenes/main.tscn", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        scene = self._read("scenes/main.tscn")
        self.assertIn('signal="was_destroyed"', scene)
        self.assertIn('method="_on_died"', scene)
        self.assertNotIn('signal="died"', scene)

    def test_method_rename_updates_connection(self):
        self._write("scenes/main.tscn", (
            '[gd_scene format=3]\n\n'
            '[ext_resource type="Script" path="res://src/turret.gd" id="1_t"]\n\n'
            '[node name="Turret" type="Node2D"]\n'
            'script = ExtResource("1_t")\n\n'
            '[connection signal="died" from="." to="." method="_on_died"]\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._method_action())
        self.assertIn("res://scenes/main.tscn", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        scene = self._read("scenes/main.tscn")
        self.assertIn('method="_on_was_destroyed"', scene)
        self.assertNotIn('method="_on_died"', scene)

    # --- 1.2.2 свойство и связь одновременно (переменная + сигнал) ---
    def test_property_and_connection_rename_together(self):
        self._write("src/turret.gd", """extends Node
signal died
@export var health: int = 100

func _on_died() -> void:
\tprint("dead")
""")
        self._reindex()
        self._write("scenes/main.tscn", (
            '[gd_scene format=3]\n\n'
            '[ext_resource type="Script" path="res://src/turret.gd" id="1_t"]\n\n'
            '[node name="Turret" type="Node2D"]\n'
            'script = ExtResource("1_t")\n'
            'health = 42\n\n'
            '[connection signal="died" from="." to="." method="_on_died"]\n'))
        var_action = {"action": "rename_symbol", "kind": "variable",
                      "declaration": "res://src/turret.gd:3",
                      "old_name": "health", "new_name": "current_health"}
        prepared = symbol_refactor.prepare_rename(self.root, var_action)
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        scene = self._read("scenes/main.tscn")
        self.assertIn("current_health = 42", scene)
        # переименование переменной не должно трогать связь
        self.assertIn('signal="died"', scene)
        self.assertIn('method="_on_died"', scene)
    # --- 1.2.3 две сцены с одним скриптом ---
    def test_two_scenes_with_same_script(self):
        for name in ("scenes/level1.tscn", "scenes/level2.tscn"):
            self._write(name, (
                '[gd_scene format=3]\n\n'
                '[ext_resource type="Script" path="res://src/turret.gd" id="1_t"]\n\n'
                '[node name="Turret" type="Node2D"]\n'
                'script = ExtResource("1_t")\n\n'
                '[connection signal="died" from="." to="." method="_on_died"]\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._signal_action())
        paths = [f["path"] for f in prepared["files"]]
        self.assertIn("res://scenes/level1.tscn", paths)
        self.assertIn("res://scenes/level2.tscn", paths)
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        for name in ("scenes/level1.tscn", "scenes/level2.tscn"):
            self.assertIn('signal="was_destroyed"', self._read(name))

    # --- 1.2.4 method указывает на метод ДРУГОГО узла — трогать нельзя ---
    def test_connection_to_other_node_method_is_untouched(self):
        self._write("src/other.gd", """extends Node

func _on_died() -> void:
\tprint("other")
""")
        self._reindex()
        self._write("scenes/main.tscn", (
            '[gd_scene format=3]\n\n'
            '[ext_resource type="Script" path="res://src/turret.gd" id="1_t"]\n'
            '[ext_resource type="Script" path="res://src/other.gd" id="2_o"]\n\n'
            '[node name="Turret" type="Node2D"]\n'
            'script = ExtResource("1_t")\n\n'
            '[node name="Other" type="Node" parent="."]\n'
            'script = ExtResource("2_o")\n\n'
            '[connection signal="died" from="Turret" to="Other" method="_on_died"]\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._method_action())
        self.assertNotIn("res://scenes/main.tscn", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        scene = self._read("scenes/main.tscn")
        self.assertIn('method="_on_died"', scene)
        self.assertIn("func _on_was_destroyed", self._read("src/turret.gd"))
        self.assertIn("func _on_died", self._read("src/other.gd"))

    # --- Аудит 1.2: вложенный class как цель связи не трогается ---
    # С Этапом 3.3 члены вложенных классов переименовываются, но Inner
    # недоступен из сцены, поэтому связь сцены остаётся нетронутой: её
    # method не имеет отношения к методу Inner.
    def test_connection_to_nested_class_script_is_untouched(self):
        self._write("src/nested.gd", """extends Node

class Inner:
\tfunc _on_died() -> void:
\t\tpass
""")
        self._reindex()
        self._write("scenes/main.tscn", (
            '[gd_scene format=3]\n\n'
            '[ext_resource type="Script" path="res://src/nested.gd" id="1_n"]\n\n'
            '[node name="Holder" type="Node"]\n'
            'script = ExtResource("1_n")\n\n'
            '[connection signal="died" from="." to="." method="_on_died"]\n'))
        prepared = symbol_refactor.prepare_rename(self.root, {
            "action": "rename_symbol", "kind": "function",
            "declaration": "res://src/nested.gd:4",
            "old_name": "_on_died", "new_name": "_on_was_destroyed"})
        self.assertNotIn("res://scenes/main.tscn", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn('method="_on_died"', self._read("scenes/main.tscn"))
    # --- Аудит 1.2: CRLF и BOM сохраняются, отступы связей не ломаются ---
    def test_crlf_and_bom_are_preserved(self):
        path = os.path.join(self.root, "scenes", "main.tscn")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = ('[gd_scene format=3]\r\n\r\n'
                '[ext_resource type="Script" path="res://src/turret.gd" id="1_t"]\r\n\r\n'
                '[node name="Turret" type="Node2D"]\r\n'
                'script = ExtResource("1_t")\r\n\r\n'
                '[connection signal="died" from="." to="." method="_on_died"]\r\n')
        with open(path, "wb") as handle:
            handle.write(b"\xef\xbb\xbf" + body.encode("utf-8"))
        prepared = symbol_refactor.prepare_rename(self.root, self._signal_action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        with open(path, "rb") as handle:
            raw = handle.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "BOM должен сохраниться")
        self.assertNotIn(b"\n\n", raw.replace(b"\r\n\r\n", b"@@"), "CRLF должен сохраниться")
        self.assertIn(b'signal="was_destroyed"', raw)
        self.assertNotIn(b'\r\n\n', raw)

    # --- Аудит 1.2: переименование переменной НЕ трогает связи сцен ---
    def test_variable_rename_leaves_connections_untouched(self):
        self._write("src/turret.gd", """extends Node
signal died
@export var health: int = 100
""")
        self._reindex()
        self._write("scenes/main.tscn", (
            '[gd_scene format=3]\n\n'
            '[ext_resource type="Script" path="res://src/turret.gd" id="1_t"]\n\n'
            '[node name="Turret" type="Node2D"]\n'
            'script = ExtResource("1_t")\n'
            'health = 42\n\n'
            '[connection signal="died" from="." to="." method="_on_died"]\n'))
        prepared = symbol_refactor.prepare_rename(self.root, {
            "action": "rename_symbol", "kind": "variable",
            "declaration": "res://src/turret.gd:3",
            "old_name": "health", "new_name": "current_health"})
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        scene = self._read("scenes/main.tscn")
        self.assertIn("current_health = 42", scene)
        self.assertIn('[connection signal="died" from="." to="." method="_on_died"]', scene)

    # --- Аудит 1.2: связь по узлу другого типа (без нашего скрипта) не трогается ---
    def test_connection_between_foreign_nodes_is_untouched(self):
        self._write("scenes/main.tscn", (
            '[gd_scene format=3]\n\n'
            '[ext_resource type="Script" path="res://src/turret.gd" id="1_t"]\n\n'
            '[node name="Turret" type="Node2D"]\n'
            'script = ExtResource("1_t")\n\n'
            '[node name="Timer" type="Timer" parent="."]\n\n'
            '[connection signal="died" from="Turret" to="Timer" method="_on_died"]\n'))
        prepared = symbol_refactor.prepare_rename(self.root, self._method_action())
        self.assertNotIn("res://scenes/main.tscn", [f["path"] for f in prepared["files"]])
        self.assertIn('[connection signal="died" from="Turret" to="Timer" method="_on_died"]',
                      self._read("scenes/main.tscn"))


if __name__ == "__main__":
    unittest.main()



if __name__ == "__main__":
    unittest.main()

