# -*- coding: utf-8 -*-
"""Синтетические тесты п.2.4: гранулярность отказа (strict/probable/dynamic).

Баг: одна непроверенная ссылка где угодно убивала многофайловую транзакцию
целиком. Нужен режим, где пользователь осознанно принимает риск.

Уровни:
  strict   (по умолчанию) — переименовываем всегда, неоднозначность = отказ;
  probable — по флагу действия: доказанные ссылки переименовываются,
            недоказанные уходят в отчёт, но не блокируют;
  dynamic  — ссылки, найденные только по строке, идут в отчёт всегда.
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


class RefusalGranularity(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_levels_")
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

    def _action(self, mode=None, new="Avatar"):
        action = {"action": "rename_symbol", "kind": "class_name",
                  "declaration": "res://src/player.gd:1",
                  "old_name": "Player", "new_name": new}
        if mode is not None:
            action["mode"] = mode
        return action

    def _ambiguous_project(self):
        # Неизвестный ресивер: target не типизирован, доказать связь нельзя.
        self._write("src/arena.gd", "extends Node\n\nfunc fire(target):\n"
                                  "\ttarget.spawn(Player)\n")
        self._reindex()


    # --- 2.4.1 strict (по умолчанию) — неоднозначность блокирует ---
    def test_strict_is_the_default(self):
        self._ambiguous_project()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        # Термин сменился с «неоднозначные» на «недоказанные» вместе с
        # Этапом 1 гранулярности отказа: доказуемо-чужие ссылки отказом не
        # являются, отказывает ровно недоказанная. Суть проверки та же —
        # strict отказывает, и отказ называет проблемное место.
        message = str(ctx.exception)
        self.assertIn("недоказанные", message)
        self.assertIn("res://src/arena.gd", message)

    def test_explicit_strict_blocks(self):
        self._ambiguous_project()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, self._action("strict"))

    # --- 2.4.2 probable — риск принимается, но попадает в отчёт ---
    def test_probable_mode_reports_instead_of_blocking(self):
        self._ambiguous_project()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("probable"))
        notes = prepared.get("unverified_references") or []
        self.assertTrue(notes, "непроверенные ссылки обязаны быть в отчёте")
        self.assertTrue(any("arena.gd" in str(n) for n in notes), notes)

    def test_probable_mode_still_renames_proven_references(self):
        self._write("src/typed.gd", "extends Node\n\nvar unit: Player\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("probable"))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        self.assertIn("var unit: Avatar", self._read("src/typed.gd"))

    # --- 2.4.3 dynamic: strict блокирует, probable — отчёт без блокировки ---
    def test_dynamic_reference_blocks_strict_and_reports_probable(self):
        # Используем node.call("Player"), а НЕ ClassDB.instantiate("Player"):
        # с Этапом 5 последний признан доказуемым (API принимает имя класса)
        # и переименовывается вместе с классом, а strict больше не отказывает.
        # Недоказуемая ссылка — это обращение по имени ЧЛЕНА.
        self._write("src/loader.gd", "extends Node\n\nfunc make(node: Node) -> Node:\n"
                                    "\treturn node.call(\"Player\")\n")
        self._reindex()
        # Критерий приёмки: dynamic-ссылка по строке в strict блокирует,
        # в probable — видна в отчёте, но не мешает.
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action("strict"))
        self.assertEqual(getattr(ctx.exception, "code", ""), "unsafe")
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("probable"))
        self.assertTrue(prepared.get("dynamic_references"))

    # --- 2.4.4 отчёт виден в public_prepared и в диффе/подтверждении ---
    def test_unverified_references_reach_public_payload(self):
        self._ambiguous_project()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("probable"))
        public = symbol_refactor.public_prepared(prepared)
        self.assertTrue(public.get("unverified_references"))
        self.assertEqual(public.get("mode"), "probable")

    # --- 2.4.5 неизвестный режим отклоняется, а не игнорируется ---
    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action("turbo"))
        self.assertIn("mode", str(ctx.exception))

    # --- 2.4.6 probable НЕ отключает жёсткие проверки ---
    def test_probable_mode_keeps_hard_guards(self):
        self._write("src/other.gd", "class_name Avatar\nextends Node\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action("probable"))
        self.assertIn("уже объявлено", str(ctx.exception))

    # --- Аудит 2.4: риск виден в ТЕКСТЕ ПОДТВЕРЖДЕНИЯ, а не только в json ---
    def test_risk_reaches_confirmation_text(self):
        import main
        self._ambiguous_project()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("probable"))
        public = symbol_refactor.public_prepared(prepared)
        public["action"] = "rename_symbol"
        text = main._describe_action(public)
        self.assertIn("ВНИМАНИЕ", text)
        self.assertIn("непроверенных ссылок", text)
        self.assertIn("probable", text)

    def test_clean_rename_has_no_warning_suffix(self):
        import main
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        public = symbol_refactor.public_prepared(prepared)
        public["action"] = "rename_symbol"
        self.assertNotIn("ВНИМАНИЕ", main._describe_action(public))

    # --- Аудит 2.4: high_level_actions принимает поле mode ---
    def test_high_level_action_accepts_mode(self):
        import high_level_actions
        result = high_level_actions.compile_action(self.root, {
            "action": "project_command", "command": {
                "type": "rename_symbol", "kind": "class_name",
                "declaration": "res://src/player.gd:1",
                "old_name": "Player", "new_name": "Avatar",
                "mode": "probable"}})
        self.assertEqual(result.get("mode"), "probable")

    # --- Аудит 2.4: probable не должен тихо ломать политику доступа ---
    def test_probable_mode_respects_write_policy(self):
        self._write("addons/pack/helper.gd", "extends Node\n\nvar unit: Player\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("probable"))
        self.assertNotIn("res://addons/pack/helper.gd",
                         [f["path"] for f in prepared["files"]])


if __name__ == "__main__":
    unittest.main()
