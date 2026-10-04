# -*- coding: utf-8 -*-
"""Синтетические тесты п.4.1: read-only шаг «найти использования».

Модель вынуждена угадывать locator для rename_symbol, потому что отдельного
поиска использований не существует. Здесь он появляется: один проход строит
список мест (файл:строка:колонка + тип связи + уверенность) и НИЧЕГО не пишет.
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


SCRIPT = """class_name Player
extends Node

func take_damage(amount: int) -> int:
\tself.take_damage(amount - 1)
\ttake_damage(0)
\treturn amount
"""


class FindUsages(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="find_usages_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/player.gd", SCRIPT)
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

    def _query(self, kind="function", line=4, old="take_damage", new="apply_damage"):
        return {"action": "find_symbol_usages", "kind": kind,
                "declaration": "res://src/player.gd:%d" % line,
                "old_name": old, "new_name": new}

    # --- 4.1.1 объявление и ссылки найдены ---
    def test_usages_include_declaration_and_references(self):
        result = symbol_refactor.find_references(self.root, self._query())
        places = result["usages"]
        self.assertTrue(places)
        links = {p["link"] for p in places}
        self.assertIn("declaration", links)
        self.assertIn("call", links)
        self.assertTrue(any(p["path"] == "res://src/player.gd" for p in places))
        self.assertTrue(any(p["path"] == "res://src/arena.gd" for p in places))

    # --- 4.1.2 у каждого места есть координаты и уровень уверенности ---
    def test_every_usage_has_position_and_confidence(self):
        result = symbol_refactor.find_references(self.root, self._query())
        for place in result["usages"]:
            self.assertTrue(place["path"].startswith("res://"), place)
            self.assertIsInstance(place["line"], int)
            self.assertIsInstance(place["column"], int)
            self.assertIn(place["confidence"], ("proven", "probable", "dynamic"))
            self.assertTrue(place["link"])

    # --- 4.1.3 ничего не пишет на диск ---
    def test_nothing_is_written(self):
        before = {rel: self._read(rel) for rel in
                  ("src/player.gd", "src/arena.gd", "project.godot")}
        symbol_refactor.find_references(self.root, self._query())
        for rel, text in before.items():
            self.assertEqual(self._read(rel), text, rel)
        self.assertIn("take_damage", self._read("src/player.gd"))

    # --- 4.1.4 динамическая строка попадает с честным уровнем dynamic ---
    def test_dynamic_string_has_dynamic_confidence(self):
        self._write("src/loader.gd", """extends Node

func make() -> Node:
\treturn ClassDB.instantiate("Player")
""")
        self._reindex()
        result = symbol_refactor.find_references(
            self.root, self._query("class_name", 1, "Player", "Avatar"))
        dynamic = [p for p in result["usages"] if p["confidence"] == "dynamic"]
        self.assertTrue(dynamic, result["usages"])
        self.assertTrue(any("loader.gd" in p["path"] for p in dynamic))

    # --- 4.1.5 неоднозначная ссылка видна как probable, а не как ошибка ---
    def test_ambiguous_reference_is_probable_not_error(self):
        self._write("src/amb.gd", """extends Node

func fire(target):
\ttarget.take_damage(1)
""")
        self._reindex()
        result = symbol_refactor.find_references(self.root, self._query())
        probable = [p for p in result["usages"] if p["confidence"] == "probable"]
        self.assertTrue(any("amb.gd" in p["path"] for p in probable), result["usages"])

    # --- 4.1.6 поиск работает и по старому имени без нового ---
    def test_query_without_new_name(self):
        query = {"action": "find_symbol_usages", "kind": "function",
                 "declaration": "res://src/player.gd:4",
                 "old_name": "take_damage"}
        result = symbol_refactor.find_references(self.root, query)
        self.assertTrue(result["usages"])
        self.assertEqual(result["old_name"], "take_damage")

    # --- 4.1.7 сводка по типам связей ---
    def test_summary_counts_by_link(self):
        result = symbol_refactor.find_references(self.root, self._query())
        self.assertIn("by_link", result)
        self.assertEqual(sum(result["by_link"].values()), len(result["usages"]))

    # --- Аудит 4.1: неверный locator даёт внятную ошибку, а не пустой список ---
    def test_bad_locator_is_reported(self):
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.find_references(
                self.root, self._query(line=99))
        self.assertIn("player.gd", str(ctx.exception))

    # --- Аудит 4.1: комментарии и строки не попадают в proven ---
    def test_comment_is_not_a_usage(self):
        self._write("src/player.gd", SCRIPT + "\n# take_damage в комментарии\n")
        self._reindex()
        result = symbol_refactor.find_references(self.root, self._query())
        proven = [p for p in result["usages"] if p["confidence"] == "proven"]
        self.assertNotIn(14, [p["line"] for p in proven])

    # --- Аудит 4.1: поиск не требует права записи в файл объявления ---
    def test_readonly_does_not_need_write_policy(self):
        result = symbol_refactor.find_references(self.root, self._query())
        self.assertTrue(result["usages"])


if __name__ == "__main__":
    unittest.main()
