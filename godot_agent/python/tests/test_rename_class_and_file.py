# -*- coding: utf-8 -*-
"""Синтетические тесты п.3.5: class_name + переименование файла и .uid одной транзакцией.

Раньше это были два независимых действия (rename_symbol, потом rename_file),
между которыми проект оставался в промежуточном состоянии: класс переименован,
файл — нет. Требуется одна транзакция: содержимое, имя файла и .uid едут вместе.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import history_manager
from godot_tools import symbol_refactor
from minilich import ml_project_index


class ClassNameAndFile(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_class_file_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/player.gd", "class_name Player\nextends Node\n")
        self._write("src/player.gd.uid", "uid://cplayer1\n")
        self._reindex()

    def _write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def _read(self, rel):
        with open(os.path.join(self.root, *rel.split("/")), "r", encoding="utf-8") as handle:
            return handle.read()

    def _exists(self, rel):
        return os.path.exists(os.path.join(self.root, *rel.split("/")))

    def _reindex(self):
        ml_project_index.build_index(self.root)

    def _action(self, new="Avatar", rename_file=True):
        return {"action": "rename_symbol", "kind": "class_name",
                "declaration": "res://src/player.gd:1",
                "old_name": "Player", "new_name": new,
                "rename_file": rename_file}

    # --- 3.5.1 файл и .uid переезжают вместе с переименованием класса ---
    def test_file_and_uid_move_together(self):
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        self.assertTrue(prepared.get("file_rename"))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/avatar.gd"))
        self.assertFalse(self._exists("src/player.gd"))
        self.assertEqual(self._read("src/avatar.gd.uid"), "uid://cplayer1\n")
        self.assertFalse(self._exists("src/player.gd.uid"))

    # --- 3.5.2 без флага файл остаётся на месте (обратная совместимость) ---
    def test_without_flag_file_stays(self):
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action(rename_file=False))
        self.assertFalse(prepared.get("file_rename"))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        self.assertTrue(self._exists("src/player.gd"))

    # --- 3.5.3 откат возвращает и содержимое, и имя файла, и .uid ---
    def test_rollback_restores_everything(self):
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        result = symbol_refactor.apply_prepared_rename(self.root, prepared)
        ok, message, _force, _paths, _diff = history_manager.rollback_entry(
            self.root, result["entry_id"])
        self.assertTrue(ok, message)
        self.assertIn("class_name Player", self._read("src/player.gd"))
        self.assertFalse(self._exists("src/avatar.gd"))
        self.assertEqual(self._read("src/player.gd.uid"), "uid://cplayer1\n")
        self.assertFalse(self._exists("src/avatar.gd.uid"))

    # --- 3.5.4 существующий файл с новым именем блокирует ---
    def test_existing_destination_is_refused(self):
        # Файл БЕЗ class_name, чтобы отказ пришёл именно от проверки пути,
        # а не от коллизии глобального имени класса.
        self._write("src/avatar.gd", "extends Node\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("уже существует", str(ctx.exception))
        self.assertIn("class_name Player", self._read("src/player.gd"))

    # --- 3.5.5 prepare ничего не пишет ---
    def test_prepare_writes_nothing(self):
        symbol_refactor.prepare_rename(self.root, self._action())
        self.assertTrue(self._exists("src/player.gd"))
        self.assertIn("class_name Player", self._read("src/player.gd"))
        self.assertFalse(self._exists("src/avatar.gd"))

    # --- Аудит 3.5: подготовленный план виден в diff до записи ---
    def test_file_rename_is_visible_in_plan(self):
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        public = symbol_refactor.public_prepared(prepared)
        self.assertEqual(public.get("file_rename"),
                         {"from": "res://src/player.gd", "to": "res://src/avatar.gd"})

    # --- Аудит 3.5: старый хэш защищает от гонки ---
    def test_stale_hash_blocks_apply(self):
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        self._write("src/player.gd", "class_name Player\nextends Node\n# manual\n")
        with self.assertRaises(symbol_refactor.StaleRenameError):
            symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertTrue(self._exists("src/player.gd"))
        self.assertFalse(self._exists("src/avatar.gd"))
    # --- Аудит 3.5: сбой переноса не оставляет файл на старом месте ---
    def test_failed_move_restores_original(self):
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        original_replace = symbol_refactor._replace_file

        def fail_once_on_uid(source, destination):
            # Падаем ровно на переносе .uid: сам .gd к этому моменту уже
            # переехал, и его обязано вернуть восстановление.
            if destination.endswith("avatar.gd.uid"):
                raise OSError("injected move failure")
            return original_replace(source, destination)

        symbol_refactor._replace_file = fail_once_on_uid
        try:
            with self.assertRaises(OSError):
                symbol_refactor.apply_prepared_rename(self.root, prepared)
        finally:
            symbol_refactor._replace_file = original_replace
        # Скрипт вернулся на старое место и с прежним содержимым.
        self.assertTrue(self._exists("src/player.gd"))
        self.assertIn("class_name Player", self._read("src/player.gd"))
        self.assertFalse(self._exists("src/avatar.gd"))
        self.assertEqual(self._read("src/player.gd.uid"), "uid://cplayer1\n")

    # --- Аудит 3.5: файл без .uid тоже переносится ---
    def test_move_without_uid_file(self):
        os.remove(os.path.join(self.root, "src", "player.gd.uid"))
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/avatar.gd"))
        self.assertFalse(self._exists("src/player.gd"))

    # --- Аудит 3.5: многословное имя даёт snake_case-файл ---
    def test_multiword_class_name_snake_case_file(self):
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action(new="DarkKnightBoss"))
        self.assertEqual(prepared["file_rename"]["to"],
                         "res://src/dark_knight_boss.gd")
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name DarkKnightBoss",
                      self._read("src/dark_knight_boss.gd"))



    # --- Аудит 3.5: сцена со ссылкой на переименовываемый скрипт ---
    # Регрессия: cc23e7f переносил .gd + .uid, но не переписывал
    # [ext_resource path=...] — сцена оставалась на несуществующем пути,
    # и узел терял скрипт.
    def test_scene_reference_follows_the_renamed_script(self):
        self._write("scenes/hero.tscn", (
            "[gd_scene load_steps=2 format=3]\n\n"
            "[ext_resource type=\"Script\" path=\"res://src/player.gd\" id=\"1\"]\n\n"
            "[node name=\"Hero\" type=\"Node2D\"]\n"
            "script = ExtResource(\"1\")\n"))
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        paths = [f["path"] for f in prepared["files"]]
        self.assertIn("res://scenes/hero.tscn", paths,
                      "ссылающаяся сцена обязана попасть в транзакцию")
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        scene = self._read("scenes/hero.tscn")
        self.assertIn("path=\"res://src/avatar.gd\"", scene)
        self.assertNotIn("path=\"res://src/player.gd\"", scene)
        self.assertTrue(self._exists("src/avatar.gd"))

    # --- Аудит 3.5: preload() в другом скрипте обновляется ---
    def test_preload_reference_follows_the_renamed_script(self):
        self._write("src/loader.gd", "extends Node\n\n"
                                     "const P = preload(\"res://src/player.gd\")\n")
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("res://src/loader.gd", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("preload(\"res://src/avatar.gd\")", self._read("src/loader.gd"))

    # --- Аудит 3.5: ссылка в файле, который нельзя ЗАПИСАТЬ, отказывает ---
    # project.godot читается, но политика записи его запрещает: такой файл
    # виден поиску, и перенос скрипта разорвал бы ссылку — значит отказ.
    def test_unwritable_reference_blocks_file_rename(self):
        self._write("scenes/hero.tscn", (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://src/player.gd" id="1"]\n\n'
            '[node name="Hero" type="Node2D"]\n'
            'script = ExtResource("1")\n'))
        # Запрещаем ЗАПИСАТЬ в сцену, оставляя чтение: ссылка видна
        # поиску, но переписать её нельзя, поэтому перенос разорвал бы её.
        # Подменяем именно в symbol_refactor: он импортирует функцию
        # по имени при загрузке модуля, и правка project_tools не влияет.
        original = symbol_refactor.can_write_project_path
        symbol_refactor.can_write_project_path = (
            lambda path, *a, **k: False if str(path).endswith("hero.tscn")
            else original(path, *a, **k))
        try:
            with self.assertRaises(symbol_refactor.RenameError) as ctx:
                symbol_refactor.prepare_rename(self.root, self._action())
        finally:
            symbol_refactor.can_write_project_path = original
        self.assertIn("hero.tscn", str(ctx.exception))
        self.assertTrue(self._exists("src/player.gd"))
        self.assertFalse(self._exists("src/avatar.gd"))

if __name__ == "__main__":
    unittest.main()
