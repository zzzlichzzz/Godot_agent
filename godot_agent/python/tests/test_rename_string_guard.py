# -*- coding: utf-8 -*-
"""Синтетические тесты п.2.2: строковый guard различает dynamic-ссылки и текст.

Баг: любая строка, равная имени, блокировала переименование. print("Player")
и ClassDB.instantiate("Player") давали одинаковый отказ, хотя относятся к
разным классам ссылок; при этом свойства в .tscn переписываются без
вопросов — логика была непоследовательной.
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


class StringGuard(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_str_")
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

    def _plan(self, code, new="Avatar"):
        self._write("src/user.gd", code)
        self._reindex()
        return symbol_refactor.prepare_rename(self.root, self._action(new))

    # --- 2.2.1 print("Player") — обычный текст, блокировать нельзя ---
    def test_plain_log_text_does_not_block(self):
        after = self._rename(
            "extends Node\n\nfunc log_it() -> void:\n\tprint(\"Player\")\n")
        self.assertIn('print("Player")', after)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))

    # --- 2.2.2 ClassDB.instantiate("Player") — подтверждённая dynamic-ссылка ---
    def test_classdb_instantiate_is_reported_not_silently_ignored(self):
        prepared = self._plan(
            "extends Node\n\nfunc make() -> Node:\n"
            "\treturn ClassDB.instantiate(\"Player\")\n")
        notes = prepared.get("dynamic_references") or []
        self.assertTrue(notes, "динамическая ссылка обязана попасть в отчёт")
        self.assertTrue(any("instantiate" in str(n) for n in notes), notes)

    # --- 2.2.3 node.set("hp", 5) — set() по имени не блокирует молча ---
    def test_set_by_name_is_reported(self):
        prepared = self._plan(
            "extends Node\n\nfunc apply(n: Node) -> void:\n"
            "\tn.set(\"Player\", 5)\n")
        notes = prepared.get("dynamic_references") or []
        self.assertTrue(any("set" in str(n) for n in notes), notes)

    # --- 2.2.4 has_signal / emit_signal / call / is_connected ---
    def test_signal_and_call_dynamics_are_reported(self):
        prepared = self._plan(
            "extends Node\n\nfunc probe(n: Node) -> void:\n"
            "\tprint(n.has_signal(\"Player\"))\n"
            "\tn.emit_signal(\"Player\")\n"
            "\tn.call(\"Player\")\n"
            "\tprint(n.is_connected(\"Player\", Callable()))\n")
        notes = " ".join(str(n) for n in (prepared.get("dynamic_references") or []))
        for expected in ("has_signal", "emit_signal", "call", "is_connected"):
            self.assertIn(expected, notes)

    # --- 2.2.5 dynamic-ссылка обязана быть видна в diff/отчёте ---
    def test_dynamic_reference_reaches_public_payload(self):
        prepared = self._plan(
            "extends Node\n\nfunc make() -> Node:\n"
            "\treturn ClassDB.instantiate(\"Player\")\n")
        public = symbol_refactor.public_prepared(prepared)
        self.assertTrue(public.get("dynamic_references"))

    # --- 2.2.6 текст с именем в строке НЕ попадает в отчёт как dynamic ---
    def test_log_text_is_not_reported_as_dynamic(self):
        prepared = self._plan(
            "extends Node\n\nfunc log_it() -> void:\n"
            "\tprint(\"Player spawned\")\n\tprint(\"Player\")\n")
        self.assertFalse(prepared.get("dynamic_references"))

    # --- 2.2.7 действительно несовпадающий текст не трогаем ---
    def test_unrelated_string_untouched(self):
        after = self._rename(
            "extends Node\n\nvar label: String = \"hero\"\n\n"
            "func log_it() -> void:\n\tprint(label)\n")
        self.assertIn('var label: String = "hero"', after)

    # --- Аудит 2.2: connect("sig", "method") — реальная dynamic-ссылка ---
    def test_connect_with_string_args_is_reported(self):
        prepared = self._plan(
            "extends Node\n\nfunc wire(n: Node) -> void:\n"
            "\tn.connect(\"Player\", Callable())\n")
        notes = " ".join(str(n) for n in (prepared.get("dynamic_references") or []))
        self.assertIn("connect", notes)

    # --- Аудит 2.2: текст с именем ВНУТРИ фразы не считается ссылкой ---
    def test_sentence_with_name_is_not_dynamic(self):
        prepared = self._plan(
            "extends Node\n\nfunc warn() -> void:\n"
            "\tpush_error(\"Player is missing\")\n"
            "\tprint(\"spawned Player at 0,0\")\n")
        self.assertFalse(prepared.get("dynamic_references"))

    # --- Аудит 2.2: dynamic-ссылка не должна ломать применение ---
    def test_dynamic_reference_does_not_block_apply(self):
        prepared = self._plan(
            "extends Node\n\nvar unit: Player\n\n"
            "func make() -> Node:\n"
            "\treturn ClassDB.instantiate(\"Player\")\n")
        result = symbol_refactor.apply_prepared_rename(self.root, prepared)
        # user.gd меняется (тип unit), а строка остаётся как есть.
        self.assertEqual(result["file_count"], 2)
        self.assertIn('ClassDB.instantiate("Player")', self._read("src/user.gd"))
        self.assertIn("var unit: Avatar", self._read("src/user.gd"))
        self.assertIn("class_name Avatar", self._read("src/player.gd"))

    # --- Аудит 2.2: именованный аргумент set(property=...) не путать ---
    def test_named_argument_style_is_not_reported(self):
        prepared = self._plan(
            "extends Node\n\nfunc build() -> Dictionary:\n"
            "\treturn {\"Player\": 1}\n")
        self.assertFalse(prepared.get("dynamic_references"))


if __name__ == "__main__":
    unittest.main()

    unittest.main()

