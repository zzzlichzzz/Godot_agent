# -*- coding: utf-8 -*-
"""Переименование const, объявление и использования которого в ОДНОМ файле.

Бывший repro_rename_const_same_file.py. Репро перенесён в трекаемый набор
регрессий (run_integration_regressions.py): здесь проверяются гарантии на
ЖИВОМ пути панели/MCP — чеклист мест -> exclude -> prepare -> apply.

Симптом (red). Снятие ОДНОЙ галочки использования отменяло переименование
ВСЕХ использований этого файла, а объявление переименовывалось всё равно —
в выводе «DECL RENAMED» вместе с оставшейся старой ссылкой, файл оставался
сломанным.

Две причины, обе проверяются здесь:
  1) main._with_exclude разбирал id места по ПЕРВОМУ двоеточию:
     "res://src/unit.gd:7:9" -> "res://src/unit.gd" — путь путался с
     :column/:line, а номер строки терялся;
  2) symbol_refactor._usage_excluded принимал такую запись (путь без строки)
     за весь файл — ветка `path in excluded` — и снимала ВСЕ места, тогда
     как правка объявления о снятой галочке не знала вовсе.

Ожидание (green): снято ровно одно место, остальные использования вместе с
объявлением переименованы, ни одно НЕснятое место не осталось со старым
именем; снятие галочки ОБЪЯВЛЕНИЯ даёт честный отказ вместо половинчатой
правки.
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


# Строка 4 — объявление, строки 7 и 10 — использования в ТОМ ЖЕ файле.
UNIT = (
    "class_name Unit\n"
    "extends Node\n"
    "\n"
    "const MAX_HP = 100\n"
    "\n"
    "func hit() -> int:\n"
    "\treturn MAX_HP\n"
    "\n"
    "func cap() -> int:\n"
    "\treturn MAX_HP + 1\n"
)

ACTION = {"action": "rename_symbol", "kind": "const",
          "declaration": "res://src/unit.gd:4",
          "old_name": "MAX_HP", "new_name": "MAX_HEALTH"}
DECLARATION_LINE = 4
EXCLUDED_LINE = 7
OTHER_USAGE_LINE = 10


def make_project(prefix):
    root = Path(tempfile.mkdtemp(prefix=prefix))
    (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "unit.gd").write_text(UNIT, encoding="utf-8", newline="")
    ml_project_index._MEM_CACHE.clear()
    ml_project_index.build_index(str(root))
    return root


class SameFileConstRename(unittest.TestCase):
    """Объявление и использования const в одном файле — единая транзакция."""

    def setUp(self):
        self.root = make_project("rename_const_same_file_")
        self.addCleanup(shutil.rmtree, str(self.root), True)

    def _read(self):
        with open(self.root / "src" / "unit.gd", "r", encoding="utf-8") as handle:
            return handle.read()

    def _checklist(self):
        """Места из чеклиста панели: id, координаты, уверенность."""
        return main._usage_checklist(
            symbol_refactor.analyze_rename(str(self.root), dict(ACTION)))

    def _rename_with(self, excluded_ids):
        """Тот же путь, что у панели/MCP: чеклист -> exclude -> prepare -> apply."""
        action = main._with_exclude(dict(ACTION), excluded_ids)
        prepared = symbol_refactor.prepare_rename(str(self.root), action)
        symbol_refactor.apply_prepared_rename(str(self.root), prepared)
        return action, prepared, self._read()

    # --- снята ОДНА галочка использования: остальное переименовано ---
    def test_one_excluded_usage_keeps_the_rest_renamed(self):
        places = self._checklist()
        ids = [place["id"] for place in places]
        self.assertEqual(sorted(place["line"] for place in places),
                         [DECLARATION_LINE, EXCLUDED_LINE, OTHER_USAGE_LINE], ids)
        excluded_ids = [place["id"] for place in places
                        if place.get("line") == EXCLUDED_LINE]
        self.assertTrue(excluded_ids, ids)

        action, prepared, text = self._rename_with(excluded_ids)

        # id места разобран без потери пути и номера строки: полный id с
        # колонкой (:7:9) даёт адрес ровно этой строки, а не «весь файл».
        expected = "res://src/unit.gd:%d" % EXCLUDED_LINE
        self.assertEqual(action["exclude"], [expected])
        self.assertEqual(symbol_refactor.exclude_place(excluded_ids[0]), expected)
        self.assertEqual(
            symbol_refactor._exclude_entry("res://src/unit.gd:%d:9" % EXCLUDED_LINE),
            ("res://src/unit.gd", EXCLUDED_LINE))

        # Снятая галочка не тронута, остальные места переименованы вместе с
        # объявлением: ни одно НЕснятое место не осталось со старым именем.
        self.assertIn("\treturn MAX_HP\n", text)
        self.assertIn("const MAX_HEALTH = 100", text)
        self.assertIn("\treturn MAX_HEALTH + 1", text)
        self.assertNotIn("\treturn MAX_HP + 1", text)
        self.assertEqual(len(prepared.get("skipped_usages") or []), 1,
                         prepared.get("skipped_usages"))

    # --- снята галочка ОБЪЯВЛЕНИЯ: честный отказ, файл не тронут ---
    def test_declaration_excluded_is_refused(self):
        places = self._checklist()
        excluded_ids = [place["id"] for place in places
                        if place.get("line") == DECLARATION_LINE]
        self.assertTrue(excluded_ids, [place["id"] for place in places])
        before = self._read()

        action = main._with_exclude(dict(ACTION), excluded_ids)
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(str(self.root), action)

        self.assertIn("Снимите галочки с мест использования", str(ctx.exception))
        self.assertEqual(self._read(), before)
        self.assertIn("const MAX_HP = 100", before)
        self.assertIn("\treturn MAX_HP\n", before)


if __name__ == "__main__":
    unittest.main()
