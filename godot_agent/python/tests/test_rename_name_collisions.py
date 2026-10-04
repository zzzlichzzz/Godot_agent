# -*- coding: utf-8 -*-
"""Синтетические тесты п.1.4: коллизии нового имени с ClassDB и autoload.

Баг: _collision смотрел только объявления в .gd. Проверено пробы: Hero ->
Sprite2D (класс движка) и Hero -> GameState (имя autoload) проходили, а
проект падал в движке.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import gd_api_cache
import history_manager
from godot_tools import symbol_refactor
from minilich import ml_project_index


CLASSDB = {
    "Object": {"inherits": "", "methods": {}, "properties": [], "signals": []},
    "Node": {"inherits": "Object", "methods": {}, "properties": [], "signals": []},
    "Node2D": {"inherits": "Node", "methods": {}, "properties": [], "signals": []},
    "Sprite2D": {"inherits": "Node2D", "methods": {}, "properties": ["texture"],
                 "signals": []},
    "Timer": {"inherits": "Node", "methods": {}, "properties": [], "signals": []},
}


class NameCollisions(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_coll_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.store = tempfile.mkdtemp(prefix="rename_coll_store_")
        self.addCleanup(shutil.rmtree, self.store, True)
        self.previous_store = history_manager._STORAGE_OVERRIDE
        history_manager.set_storage_dir(self.store)
        self.addCleanup(setattr, history_manager, "_STORAGE_OVERRIDE",
                        self.previous_store)
        self._write("project.godot", "config_version=5\n")
        self._write("src/actor.gd", "class_name Actor\nextends Node\n")
        self._reindex()
        gd_api_cache.save_cache(self.root, dict(CLASSDB), "4.5")

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

    def _action(self, new):
        return {"action": "rename_symbol", "kind": "class_name",
                "declaration": "res://src/actor.gd:1",
                "old_name": "Actor", "new_name": new}
    # --- 1.4.1 имя класса движка ---
    def test_engine_class_name_is_refused(self):
        for name in ("Sprite2D", "Timer", "Node2D"):
            with self.assertRaises(symbol_refactor.RenameError) as ctx:
                symbol_refactor.prepare_rename(self.root, self._action(name))
            self.assertIn(name, str(ctx.exception))
        self.assertIn("class_name Actor", self._read("src/actor.gd"))

    # --- 1.4.2 имя autoload ---
    def test_autoload_name_is_refused(self):
        self._write("project.godot", (
            'config_version=5\n\n'
            '[autoload]\n\n'
            'GameState="*res://src/game_state.gd"\n'))
        self._write("src/game_state.gd", "extends Node\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action("GameState"))
        self.assertIn("GameState", str(ctx.exception))
        self.assertIn("class_name Actor", self._read("src/actor.gd"))

    # --- 1.4.3 глобальный ключ проекта (действие ввода InputMap) ---
    def test_input_map_action_name_is_refused(self):
        self._write("project.godot", (
            'config_version=5\n\n'
            '[input]\n\n'
            'move_left={\n'
            '"deadzone": 0.5\n'
            '}\n'))
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action("move_left"))
        self.assertIn("move_left", str(ctx.exception))

    # --- 1.4.4 легитимное уникальное имя должно проходить ---
    def test_unique_name_is_allowed(self):
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("Combatant"))
        self.assertIn("res://src/actor.gd", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Combatant", self._read("src/actor.gd"))

    # --- Аудит 1.4: без кэша ClassDB проверка не должна ломать обычное имя ---
    def test_rename_works_without_classdb_cache(self):
        gd_api_cache._cache["root"] = None
        gd_api_cache._cache["classes"] = {}
        gd_api_cache._cache["godot_version"] = ""
        os.remove(os.path.join(
            history_manager.get_storage_dir(self.root),
            gd_api_cache.CACHE_FILENAME))
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("Combatant"))
        self.assertTrue(prepared["files"])
        self.assertIn("class_name Actor", self._read("src/actor.gd"))
    # --- Аудит 1.4: секции project.godot вне autoload/input не считаются ---
    def test_other_project_sections_do_not_block(self):
        self._write("project.godot", (
            'config_version=5\n\n'
            '[application]\n\n'
            'config/name="Combatant Demo"\n'
            'run/main_scene="res://scenes/main.tscn"\n\n'
            '[layer_names]\n\n'
            '2d_physics/layer_1="Combatant"\n'))
        self._write("scenes/main.tscn", '[gd_scene format=3]\n\n[node name="Main" type="Node"]\n')
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("Combatant"))
        self.assertTrue(prepared["files"])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Combatant", self._read("src/actor.gd"))

    # --- Аудит 1.4: вложенные подсекции [input.xxx] не путаются с действиями ---
    def test_nested_input_sections_are_not_actions(self):
        self._write("project.godot", (
            'config_version=5\n\n'
            '[input_devices]\n\n'
            'pointing/emulate_touch_from_mouse=true\n\n'
            '[input]\n\n'
            'fire={"deadzone": 0.5}\n'))
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("emulate_touch_from_mouse"))
        self.assertTrue(prepared["files"])

    # --- Аудит 1.4: имена с дефисом/точкой в project.godot не ломают разбор ---
    def test_odd_project_godot_entries_do_not_break_parsing(self):
        self._write("project.godot", (
            'config_version=5\n\n'
            '[autoload]\n\n'
            '; GameState="*res://gone.gd"\n'
            '\n'
            '[application]\n\n'
            'config/name="A=B"\n'))
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("GameState"))
        self.assertTrue(prepared["files"])


if __name__ == "__main__":
    unittest.main()
