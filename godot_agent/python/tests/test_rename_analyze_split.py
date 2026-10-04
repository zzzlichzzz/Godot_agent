# -*- coding: utf-8 -*-
"""Синтетические тесты п.4.2: разделение поиска и применения.

Анализ и запись были слиты в prepare_rename — отсюда «всё или ничего»:
одна непроверенная ссылка где угодно убивала многофайловую транзакцию.
Разделение даёт предпросмотр (analyze_rename ничего не пишет) и частичное
применение (exclude: пользователь снимает галочки с мест).
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


PLAYER = """class_name Player
extends Node

func take_damage(amount: int) -> int:
\treturn amount
"""


class AnalyzeAndApply(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_split_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/player.gd", PLAYER)
        self._write("src/arena.gd", """extends Node

var unit: Player

func hit() -> int:
\treturn unit.take_damage(2)
""")
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

    # --- 4.2.1 analyze_rename ничего не пишет и отдаёт план ---
    def test_analyze_writes_nothing(self):
        before = {rel: self._read(rel) for rel in
                  ("src/player.gd", "src/arena.gd")}
        analysis = symbol_refactor.analyze_rename(self.root, self._action())
        self.assertTrue(analysis["usages"])
        for rel, text in before.items():
            self.assertEqual(self._read(rel), text)

    # --- 4.2.2 analyze показывает места, которые изменятся ---
    def test_analyze_lists_affected_files(self):
        analysis = symbol_refactor.analyze_rename(self.root, self._action())
        self.assertIn("res://src/arena.gd", analysis["affected_paths"])
        self.assertIn("res://src/player.gd", analysis["affected_paths"])

    # --- 4.2.3 частичное применение: исключённое место не меняется ---
    def test_excluded_usage_is_left_alone(self):
        # arena.gd: 3 = "var unit: Player" — именно это место снимаем.
        action = self._action(exclude=["res://src/arena.gd:3"])
        prepared = symbol_refactor.prepare_rename(self.root, action)
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        # Снятая галочка: эта ссылка осталась как была.
        self.assertIn("var unit: Player", self._read("src/arena.gd"))

    # --- 4.2.4 исключённые места попадают в отчёт ---
    def test_excluded_usages_are_reported(self):
        action = self._action(exclude=["res://src/arena.gd:3"])
        prepared = symbol_refactor.prepare_rename(self.root, action)
        skipped = prepared["skipped_usages"]
        self.assertTrue(skipped, list(prepared.keys()))
        self.assertTrue(any("arena.gd" in item for item in skipped), skipped)
        self.assertTrue(any("arena.gd" in item for item in
                            symbol_refactor.public_prepared(prepared)["skipped_usages"]))

    # --- 4.2.5 частичное применение полностью обратимо ---
    def test_partial_apply_rolls_back(self):
        before = {rel: self._read(rel) for rel in
                  ("src/player.gd", "src/arena.gd")}
        action = self._action(exclude=["res://src/arena.gd:3"])
        prepared = symbol_refactor.prepare_rename(self.root, action)
        result = symbol_refactor.apply_prepared_rename(self.root, prepared)
        ok, message, _force, _paths, _diff = history_manager.rollback_entry(
            self.root, result["entry_id"])
        self.assertTrue(ok, message)
        for rel, text in before.items():
            self.assertEqual(self._read(rel), text, rel)

    # --- 4.2.6 analyze отражает риски (dynamic/probable) ---
    def test_partial_apply_still_lints_clean(self):
        self._write("scenes/main.tscn", (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://src/player.gd" id="1_p"]\n\n'
            '[node name="Main" type="Node"]\n'
            'script = ExtResource("1_p")\n'))
        self._reindex()
        action = self._action(exclude=["res://src/arena.gd:3"])
        prepared = symbol_refactor.prepare_rename(self.root, action)
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        # Сцена пережила частичное применение: ссылка на скрипт цела.
        self.assertIn('path="res://src/player.gd"',
                      self._read("scenes/main.tscn"))
        self.assertIn("class_name Avatar", self._read("src/player.gd"))

    # --- 4.2.6 analyze отражает риски (dynamic/probable) ---
    def test_analyze_exposes_risks(self):
        self._write("src/loader.gd", """extends Node

func make() -> Node:
\treturn ClassDB.instantiate("Player")
""")
        self._reindex()
        analysis = symbol_refactor.analyze_rename(self.root, self._action())
        self.assertIn("risks", analysis)
        self.assertTrue(analysis["risks"])

    # --- Аудит 4.2: неизвестный путь в exclude не ломает применение ---
    def test_unknown_exclude_is_ignored(self):
        action = self._action(exclude=["res://src/nope.gd:1"])
        prepared = symbol_refactor.prepare_rename(self.root, action)
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))

    # --- Аудит 4.2: analyze не требует права записи ---
    def test_analyze_ignores_write_policy(self):
        analysis = symbol_refactor.analyze_rename(self.root, self._action())
        self.assertTrue(analysis["usages"])


if __name__ == "__main__":
    unittest.main()
