# -*- coding: utf-8 -*-
"""Снятие галочек со ВСЕХ ссылок: ядро отказывает, файл не меняется.

Симптом (red). Если пользователь снял галочки со всех мест использования, а
объявление осталось отмеченным, `prepare_rename` всё равно собирал правку
объявления и отдавал её в применение. Итог — половинчатое переименование:
символ получал новое имя, а все его использования оставались со старым,
то есть файл становился сломанным, хотя операция рапортовала успех.

Ожидание (green). Ядро считает правки-ССЫЛКИ отдельно от правок-объявлений
(`reference_edits`). Если объявление правится, а ссылочных правок не
набралось ни одной, и при этом есть снятые пользователем места —
`prepare_rename` бросает `RenameError` ДО сборки плана. На диск не
записывается ничего: содержимое файла байт-в-байт прежнее, а применение
(`apply_prepared_rename`) вообще не вызывается, потому что применять нечего.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.dirname(HERE)
sys.path.insert(0, PY)
import _bootstrap  # noqa: E402,F401

import main  # noqa: E402
from godot_tools import symbol_refactor  # noqa: E402
from minilich import ml_project_index  # noqa: E402


# Строка 4 — объявление, строка 7 — ЕДИНСТВЕННОЕ использование.
UNIT = (
    "class_name Solitary\n"
    "extends Node\n"
    "\n"
    "const MAX_HP = 100\n"
    "\n"
    "func hit() -> int:\n"
    "\treturn MAX_HP\n"
)

ACTION = {"action": "rename_symbol", "kind": "const",
          "declaration": "res://src/solitary.gd:4",
          "old_name": "MAX_HP", "new_name": "MAX_HEALTH"}
DECLARATION_LINE = 4
USAGE_LINE = 7


def make_project(prefix):
    root = Path(tempfile.mkdtemp(prefix=prefix))
    (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "solitary.gd").write_text(UNIT, encoding="utf-8", newline="")
    ml_project_index._MEM_CACHE.clear()
    ml_project_index.build_index(str(root))
    return root


class LastUsageExcludedRenameRefused(unittest.TestCase):
    """Снята последняя ссылка — честный отказ вместо половинчатой правки."""

    def setUp(self):
        self.root = make_project("rename_const_exclude_last_usage_")
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.target = self.root / "src" / "solitary.gd"

    def _read_bytes(self):
        with open(self.target, "rb") as handle:
            return handle.read()

    def _checklist(self):
        """Места из чеклиста панели: id, координаты, уверенность."""
        return main._usage_checklist(
            symbol_refactor.analyze_rename(str(self.root), dict(ACTION)))

    # --- снята ЕДИНСТВЕННАЯ ссылка: объявление переименовать нельзя ---
    def test_excluding_the_only_usage_refuses_before_writing(self):
        places = self._checklist()
        ids = [place["id"] for place in places]
        self.assertEqual(sorted(place["line"] for place in places),
                         [DECLARATION_LINE, USAGE_LINE], ids)
        excluded_ids = [place["id"] for place in places
                        if place.get("line") == USAGE_LINE]
        self.assertTrue(excluded_ids, ids)
        before = self._read_bytes()

        action = main._with_exclude(dict(ACTION), excluded_ids)
        # ровно тот путь, что у панели/MCP: id -> адрес места -> exclude
        self.assertEqual(action["exclude"],
                         ["res://src/solitary.gd:%d" % USAGE_LINE])
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(str(self.root), action)

        message = str(ctx.exception)
        self.assertIn("Все ссылки сняты пользователем", message)
        # Причина отказа содержит конкретное снятое место — иначе модель не
        # поймёт, что именно вернуть в план.
        self.assertIn("solitary.gd:%d" % USAGE_LINE, message)
        # Ни одной записи на диск: отказ случился ДО применения плана.
        self.assertEqual(self._read_bytes(), before)
        self.assertIn(b"const MAX_HP = 100", before)
        self.assertIn(b"\treturn MAX_HP\n", before)
        # Применять нечего: prepare_rename не вернул план вообще.
        self.assertFalse(hasattr(ctx.exception, "files"))
        self.assertEqual(sorted(os.listdir(self.root / "src")), ["solitary.gd"])

    # --- одна галочка из двух: снятие не блокирует переименование ---
    # Проверяем на собственном проекте: чужой файл с тем же именем сделал бы
    # ссылку недоказанной и увёл бы тест в другой отказ.
    def test_excluding_one_of_two_usages_still_renames(self):
        root = Path(tempfile.mkdtemp(prefix="rename_const_exclude_one_of_two_"))
        self.addCleanup(shutil.rmtree, str(root), True)
        (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
        (root / "src").mkdir()
        (root / "src" / "pair.gd").write_text(
            "class_name Pair\n"
            "extends Node\n"
            "\n"
            "const MAX_HP = 100\n"
            "\n"
            "func hit() -> int:\n"
            "\treturn MAX_HP\n"
            "\n"
            "func cap() -> int:\n"
            "\treturn MAX_HP + 1\n",
            encoding="utf-8", newline="")
        ml_project_index._MEM_CACHE.clear()
        ml_project_index.build_index(str(root))
        action = {"action": "rename_symbol", "kind": "const",
                  "declaration": "res://src/pair.gd:4",
                  "old_name": "MAX_HP", "new_name": "MAX_HEALTH"}
        places = main._usage_checklist(
            symbol_refactor.analyze_rename(str(root), dict(action)))
        excluded_ids = [place["id"] for place in places
                        if place.get("line") == USAGE_LINE]
        self.assertEqual(len(excluded_ids), 1, [place["id"] for place in places])

        prepared = symbol_refactor.prepare_rename(
            str(root), main._with_exclude(dict(action), excluded_ids))
        self.assertEqual(len(prepared.get("skipped_usages") or []), 1,
                         prepared.get("skipped_usages"))
        # Снята одна галочка из двух — остальное переименовано, отказ не сработал.
        self.assertGreater(int(prepared.get("renamed_count") or 0), 1)


if __name__ == "__main__":
    unittest.main()
