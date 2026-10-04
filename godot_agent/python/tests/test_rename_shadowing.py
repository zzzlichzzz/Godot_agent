# -*- coding: utf-8 -*-
"""Синтетические тесты п.2.3: одноимённые объявления в других файлах.

Баг: const Player = preload("res://player.gd") в ЛЮБОМ файле проекта блокировал
переименование class_name Player. Для class_name _collision возвращал первый
же item с новым именем, не различая «здесь объявлен наш символ» и «в другом
файле просто совпало имя».
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


class ShadowingDeclarations(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_shadow_")
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

    def _plan(self, code, rel="src/loader.gd", new="Avatar"):
        self._write(rel, code)
        self._reindex()
        return symbol_refactor.prepare_rename(self.root, self._action(new))


    # --- 2.3.1 чужое локальное имя Avatar в другом файле — не блокирует ---
    def test_unrelated_local_name_does_not_block(self):
        prepared = self._plan("extends Node\n\nvar Avatar = 1\n\n"
                              "func run() -> void:\n\tprint(Avatar)\n")
        self.assertIn("res://src/player.gd", [f["path"] for f in prepared["files"]])

    # --- 2.3.2 одноимённая ПЕРЕМЕННАЯ в том же скрипте — реальное затенение ---
    def test_local_variable_shadows_new_class_name(self):
        self._write("src/player.gd", PLAYER + "\nvar Avatar = 1\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("уже объявлено", str(ctx.exception))

    # --- 2.3.3 const с тем же именем в том же скрипте — тоже затенение ---
    def test_local_const_shadows_new_class_name(self):
        self._write("src/player.gd", PLAYER + "\nconst Avatar = 1\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, self._action())

    # --- 2.3.4 одноимённый класс проекта — блокирует по-настоящему ---
    def test_real_second_class_name_blocks(self):
        self._write("src/other.gd", "class_name Avatar\nextends Node\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("уже объявлено", str(ctx.exception))

    # --- 2.3.5 функция с новым именем в том же скрипте блокирует ---
    def test_local_function_blocks_rename(self):
        self._write("src/player.gd", PLAYER + "\nfunc Avatar() -> void:\n\tpass\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, self._action())

    # --- 2.3.6 предупреждение о совпадении имён попадает в отчёт ---
    def test_name_clash_is_reported_as_warning(self):
        prepared = self._plan("extends Node\n\nvar Avatar = 1\n")
        notes = prepared.get("warnings") or []
        self.assertTrue(any("Avatar" in str(n) for n in notes), notes)

    # --- 2.3.7 переименование применяется, чужой файл остаётся целым ---
    def test_apply_leaves_other_file_intact(self):
        prepared = self._plan("extends Node\n\nvar Avatar = 1\n")
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        self.assertIn("var Avatar = 1", self._read("src/loader.gd"))

    # --- Аудит 2.3: Этап 1.1 — подкласс с одноимённым членом всё ещё блокирует ---
    def test_subclass_shadowing_still_blocks(self):
        self._write("src/boss.gd", "extends Player\n\nvar Avatar = 1\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, self._action())

    # --- Аудит 2.3: Этап 1.4 — глобальные имена не обойти новой логикой ---
    def test_engine_class_still_blocked_with_clash_present(self):
        import gd_api_cache
        import history_manager
        previous = history_manager._STORAGE_OVERRIDE
        store = tempfile.mkdtemp(prefix="rename_shadow_store_")
        history_manager.set_storage_dir(store)
        try:
            gd_api_cache.save_cache(self.root, {"Sprite2D": {"inherits": "Node2D",
                                                           "methods": {},
                                                           "properties": [],
                                                           "signals": []}}, "4.5")
            self._write("src/loader.gd", "extends Node\n\nvar Sprite2D = 1\n")
            self._reindex()
            with self.assertRaises(symbol_refactor.RenameError) as ctx:
                symbol_refactor.prepare_rename(self.root, self._action("Sprite2D"))
            self.assertIn("движка", str(ctx.exception))
        finally:
            if previous is not None:
                history_manager.set_storage_dir(previous)
            else:
                history_manager._STORAGE_OVERRIDE = None
            shutil.rmtree(store, ignore_errors=True)

    # --- Аудит 2.3: переменная по-прежнему защищена в своём файле ---
    def test_variable_rename_collision_in_own_script_still_blocks(self):
        self._write("src/unit.gd", "extends Node\nvar speed = 1\nvar total = 2\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, {
                "action": "rename_symbol", "kind": "variable",
                "declaration": "res://src/unit.gd:2",
                "old_name": "speed", "new_name": "total"})
        self.assertIn("уже объявлено", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
