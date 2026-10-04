# -*- coding: utf-8 -*-
"""Синтетические тесты п.4.4: типизированные отказы rename_symbol.

Отказы сводились к одному RenameError с одним текстом, поэтому и человек,
и модель не могли понять, что делать: исправить locator, выбрать другое
место или признать, что случай не поддерживается. Вводим коды:
  locator     — указано неверное место/имя, попробуй другую строку;
  unsafe      — переименование опасно (конфликт, неоднозначность);
  unsupported — случай честно не поддерживается.
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


class RefusalKinds(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_kinds_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")
        self._write("src/player.gd",
                    "class_name Player\nextends Node\n\nfunc hit() -> void:\n\tpass\n")
        self._reindex()

    def _write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def _reindex(self):
        ml_project_index.build_index(self.root)

    def _action(self, kind="function", line=4, old="hit", new="strike"):
        return {"action": "rename_symbol", "kind": kind,
                "declaration": "res://src/player.gd:%d" % line,
                "old_name": old, "new_name": new}

    # --- 4.4.1 неверный locator даёт код locator ---
    def test_wrong_locator_has_locator_code(self):
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action(line=99))
        self.assertEqual(ctx.exception.code, "locator")
        self.assertIsInstance(ctx.exception, symbol_refactor.LocatorError)

    # --- 4.4.2 неизвестный вид даёт код unsupported ---
    def test_unknown_kind_has_unsupported_code(self):
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(
                self.root, self._action(kind="property"))
        self.assertEqual(ctx.exception.code, "unsupported")

    # --- 4.4.3 запрещённое имя имеет код unsupported ---
    def test_keyword_name_has_unsupported_code(self):
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action(new="for"))
        self.assertEqual(ctx.exception.code, "unsupported")

    # --- 4.4.4 коллизия имени — это unsafe ---
    def test_collision_is_unsafe(self):
        self._write("src/player.gd", "class_name Player\nextends Node\n\n"
                                       "func hit() -> void:\n\tpass\n"
                                       "func strike() -> void:\n\tpass\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertEqual(ctx.exception.code, "unsafe")
        self.assertIsInstance(ctx.exception, symbol_refactor.UnsafeRenameError)

    # --- 4.4.5 неоднозначная ссылка в probable — не отказ strict ---
    def test_strict_ambiguity_is_unsafe(self):
        self._write("src/arena.gd", "extends Node\n\nfunc fire(t):\n\tt.hit()\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertEqual(ctx.exception.code, "unsafe")

    # --- 4.4.6 неподдерживаемый scope — код unsupported ---
    def test_unsupported_scope_has_unsupported_code(self):
        self._write("src/player.gd", "extends Node\n\nfunc build() -> void:\n"
                                       "\tclass Local:\n"
                                       "\t\tfunc hit() -> void:\n\t\t\tpass\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action(line=5))
        self.assertEqual(ctx.exception.code, "unsupported")

    # --- Аудит 4.4: все отказы остаются RenameError (обратная совместимость) ---
    def test_all_refusals_remain_rename_error(self):
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, self._action(line=99))
        for code in ("locator", "unsafe", "unsupported"):
            self.assertTrue(hasattr(symbol_refactor.RenameError("x"), "code"))

    # --- Аудит 4.4: тексты отказов остаются непустыми ---
    def test_messages_are_human_readable(self):
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action(line=99))
        self.assertIn("player.gd", str(ctx.exception))
        self.assertGreater(len(str(ctx.exception)), 20)


if __name__ == "__main__":
    unittest.main()
