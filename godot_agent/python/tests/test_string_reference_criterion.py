# -*- coding: utf-8 -*-
"""Критерий готовности: print("ClassName") не блокирует переименование класса
и не переименовывается, а ClassDB.instantiate("ClassName") переименовывается
ВМЕСТЕ с классом, потому что по контракту Godot принимает имя класса.

ИЗМЕНЕНИЕ КРИТЕРИЯ (Этап 5). Раньше здесь было наоборот: instantiate считался
недоказуемой динамикой и блокировал переименование в strict. Теперь он
доказуем: сигнатура API однозначно говорит, что принимается имя класса, значит
строка обязана меняться вместе с классом, иначе проект падает в рантайме.

Что осталось НЕДОКАЗУЕМЫМ и по-прежнему блокирует — обращение по имени ЧЛЕНА
(`node.call("X")`, `set("X")`). Граница принципиальна: имя класса переименовываем,
имя свойства или метода — нет.

Тот же контракт проверяется и в test_rename_string_guard.py и
test_rename_class_name_strings; здесь он зафиксирован отдельным набором,
потому что это критерий приёмки, а не частный случай реализации.
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


class StringReferenceCriterion(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="crit_string_")
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

    def _action(self, **extra):
        action = {"action": "rename_symbol", "kind": "class_name",
                  "declaration": "res://src/player.gd:1",
                  "old_name": "Player", "new_name": "Avatar"}
        action.update(extra)
        return action

    # --- критерий 3a: print("Player") — обычный текст, не блокирует ---
    def test_print_does_not_block(self):
        self._write("src/a.gd", "extends Node\n\nfunc log() -> void:\n\tprint(\"Player\")\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        self.assertIn('print("Player")', self._read("src/a.gd"))

    # --- критерий 3b: ClassDB.instantiate("Player") переименовывается ---
    def test_classdb_instantiate_is_renamed_with_class(self):
        """Доказуемая ссылка: API по контракту принимает имя класса.

        Возможный страх «это же опасно» закрывается рассуждением: оставить
        строку старой хуже, чем переименовать её. Старое имя в строке после
        переименования класса — гарантированная ошибка в рантайме, то есть
        проект был бы сломан НАВЕРНЯКА. Переименование же ломает проект
        только в том маловероятном случае, когда «Player» в этой строке
        означал совсем другой класс, — но тогда такое имя и не равнялось бы
        старому имени нашего класса, а совпадение возможно лишь как тень.
        """
        self._write("src/b.gd", "extends Node\n\nfunc make() -> Node:\n"
                                "\treturn ClassDB.instantiate(\"Player\")\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        self.assertIn('ClassDB.instantiate("Avatar")', self._read("src/b.gd"))

    # --- критерий 3c: доказанное место НЕ попадает в отчёт как риск ---
    def test_proven_class_string_is_not_reported_as_risk(self):
        """Доказанное место не должно пугать пользователя: если оно и в отчёте
        числится риском, значит переименование всё равно где-то не применится."""
        self._write("src/b.gd", "extends Node\n\nfunc make() -> Node:\n"
                                "\treturn ClassDB.instantiate(\"Player\")\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        joined = " ".join(str(item)
                          for item in (prepared.get("dynamic_references") or []))
        self.assertNotIn("src/b.gd", joined)

    # --- критерий 3d: НЕДОКАЗУЕМАЯ ссылка (имя члена) — отказ в strict ---
    def test_unproven_member_string_still_blocks(self):
        """Граница критерия сместилась, но не исчезла: node.call("Player") —
        имя ЧЛЕНА, переписать его нельзя, поэтому strict обязан отказать."""
        self._write("src/b.gd", "extends Node\n\nfunc make(node: Node) -> Node:\n"
                                "\treturn node.call(\"Player\")\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        message = str(ctx.exception)
        self.assertIn("src/b.gd", message)
        # Отказ не должен оставить проект изменённым «наполовину».
        self.assertIn("class_name Player", self._read("src/player.gd"))
        self.assertNotIn("class_name Avatar", self._read("src/player.gd"))
        # Подсказка: что именно сделать дальше.
        self.assertTrue("probable" in message or "вручную" in message, message)

    # --- критерий 3e: probable — осознанный выход, риск виден, но не блокирует ---
    def test_probable_mode_accepts_and_reports(self):
        """В probable недоказуемая ссылка видна в отчёте, но не мешает. Строка
        при этом ОСТАЁТСЯ как есть: снять блокировку — не значит уметь
        переписать обращение по имени члена."""
        self._write("src/b.gd", "extends Node\n\nfunc make(node: Node) -> Node:\n"
                                "\treturn node.call(\"Player\")\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action(mode="probable"))
        self.assertTrue(prepared["dynamic_references"])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        # Строка осталась как была — её нельзя доказать.
        self.assertIn('node.call("Player")', self._read("src/b.gd"))

    # --- критерий 3e: set() по имени — тоже блокирует в strict ---
    def test_set_by_name_blocks(self):
        self._write("src/c.gd", "extends Node\n\nfunc apply(n: Node) -> void:\n"
                                "\tn.set(\"Player\", 5)\n")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("set()", str(ctx.exception))

    # --- критерий 3f: комментарий и присваивание строки не блокируют ---
    def test_comment_and_assignment_do_not_block(self):
        self._write("src/d.gd", "extends Node\n\n"
                                "# Player тут только в комментарии\n"
                                "func run() -> void:\n"
                                "\tvar label = \"Player\"\n\tprint(label)\n")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))


if __name__ == "__main__":
    unittest.main()
