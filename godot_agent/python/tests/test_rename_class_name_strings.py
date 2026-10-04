# -*- coding: utf-8 -*-
"""Этап 5: строки, которые ДОКАЗУЕМО содержат имя класса.

Проблема. `ClassDB.instantiate("Player")` после переименования класса в
Avatar гарантированно роняет проект в рантайме: имя класса в строке осталось
старым. Сейчас такое место попадает в dynamic_references и в strict является
ОТКАЗОМ (symbol_refactor.py:1718).

Почему до сих пор нельзя было просто переименовать строку. Строки с именем
символа встречаются в четырёх разных ролях:

    ClassDB.instantiate("Player")   # API ПРИНИМАЕТ ИМЯ КЛАССА -> можно
    load("res://src/player.gd")     # путь к файлу -> это rename_file
    print("Player")                 # текст для человека -> нельзя
    data.get("Player")              # ключ словаря -> нельзя

Переименование «всех строк, равных имени» сломало бы лог и словари. Поэтому
правило узкое: переименовываем строку, когда API по контракту Godot принимает
имя класса И переименовывается именно class_name.

Граница этапа: только class_name и только перечисленные API. Ничего больше.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

from godot_tools import symbol_refactor
from minilich.ml_project_index import build_index


PLAYER = "class_name Player\nextends Node2D\n"
SPAWNER = ('extends Node\n\nfunc make() -> Node2D:\n'
           '\treturn ClassDB.instantiate("Player")\n')
# Та же строка, но в РОЛЯХ, где она не имя класса.
# ВНИМАНИЕ: data.get("Player") и data.set("Player", 1) — ЭТО обращение к
# движку по имени члена, поэтому strict на таком проекте законно отказывает.
# Проверять «строка не переименована» здесь нельзя: переименование просто не
# дойдёт до записи. Для проверки границы используем probable.
MIXED = ('extends Node\n\nfunc run(data: Dictionary) -> void:\n'
         '\tprint("готово: Player")\n\tprint(data.get("Player"))\n'
         '\tdata.set("Player", 1)\n')


def _project(files, prefix="stage5_"):
    root = tempfile.mkdtemp(prefix=prefix)
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    build_index(root)
    return root


def _action(**extra):
    action = {"action": "rename_symbol", "kind": "class_name",
              "declaration": "res://src/player.gd:1",
              "old_name": "Player", "new_name": "Avatar"}
    action.update(extra)
    return action


def _read(root, rel):
    with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as handle:
        return handle.read()
# __APPEND__
class ClassNameStringIsRenamed(unittest.TestCase):
    """Доказуемый случай: API принимает имя класса."""

    def setUp(self):
        self.root = _project({"project.godot": "config_version=5\n",
                              "src/player.gd": PLAYER,
                              "src/spawner.gd": SPAWNER})
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_instantiate_string_is_renamed(self):
        prepared = symbol_refactor.prepare_rename(self.root, _action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn('ClassDB.instantiate("Avatar")',
                      _read(self.root, "src/spawner.gd"))

    def test_strict_no_longer_refuses_on_instantiate(self):
        """Главная ценность этапа: доказуемый случай больше не отказывает.
        Иначе каждое такое место требовало бы probable вручную."""
        prepared = symbol_refactor.prepare_rename(self.root, _action())
        self.assertEqual(prepared.get("unverified_references") or [], [])
        self.assertEqual(
            prepared.get("dynamic_references") or [], [],
            "доказанная строка не должна оставаться в отчёте как "
            "непроверенная")

    def test_renamed_file_is_in_transaction(self):
        prepared = symbol_refactor.prepare_rename(self.root, _action())
        self.assertIn("res://src/spawner.gd",
                      [item["path"] for item in prepared["files"]])

    def test_no_risk_is_reported_for_renamed_string(self):
        prepared = symbol_refactor.prepare_rename(self.root, _action())
        joined = " ".join(str(item) for item in (prepared.get("warnings") or []))
        self.assertNotIn("spawner.gd", joined)


class NonClassStringsUntouched(unittest.TestCase):
    """Строка с тем же текстом, но НЕ имя класса, обязана остаться."""

    def setUp(self):
        self.root = _project({"project.godot": "config_version=5\n",
                              "src/player.gd": PLAYER,
                              "src/mixed.gd": MIXED})
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_plain_text_is_not_renamed(self):
        prepared = symbol_refactor.prepare_rename(
            self.root, _action(mode="probable"))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn('print("готово: Player")',
                      _read(self.root, "src/mixed.gd"))

    def test_dictionary_key_is_not_renamed(self):
        """Ключ словаря «Player» — это данные, а не имя класса. Переименование
        сломает доступ к данным и НЕ должно происходить."""
        prepared = symbol_refactor.prepare_rename(
            self.root, _action(mode="probable"))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        text = _read(self.root, "src/mixed.gd")
        self.assertIn('data.get("Player")', text)
        self.assertIn('data.set("Player", 1)', text)

    def test_member_name_strings_are_not_renamed(self):
        """has_method/set/get/call принимают имя ЧЛЕНА. Переименовывать их при
        переименовании class_name нельзя — это другой символ."""
        root = _project({"project.godot": "config_version=5\n",
                         "src/player.gd": PLAYER,
                         "src/member.gd": (
                             'extends Node\n\nfunc probe(obj: Node) -> void:\n'
                             '\tprint(obj.has_method("Player"))\n'
                             '\tobj.set("Player", 1)\n'
                             '\tobj.call("Player")\n')})
        self.addCleanup(shutil.rmtree, root, True)
        prepared = symbol_refactor.prepare_rename(
            root, _action(mode="probable"))
        symbol_refactor.apply_prepared_rename(root, prepared)
        text = _read(root, "src/member.gd")
        self.assertIn('has_method("Player")', text)
        self.assertIn('obj.set("Player", 1)', text)
        self.assertIn('obj.call("Player")', text)
# __APPEND__
# --- граница: переименовывается только class_name ---
    def test_function_rename_does_not_touch_class_string(self):
        """Строка «Player» — имя КЛАССА. Переименование метода не имеет права
        её трогать, даже если текст совпал."""
        root = _project({"project.godot": "config_version=5\n",
                         "src/player.gd": PLAYER
                         + "\nfunc deal_damage() -> void:\n\tpass\n",
                         "src/spawner.gd": SPAWNER})
        self.addCleanup(shutil.rmtree, root, True)
        prepared = symbol_refactor.prepare_rename(root, {
            "action": "rename_symbol", "kind": "function",
            "declaration": "res://src/player.gd:4",
            "old_name": "deal_damage", "new_name": "apply_damage"})
        symbol_refactor.apply_prepared_rename(root, prepared)
        self.assertIn('ClassDB.instantiate("Player")',
                      _read(root, "src/spawner.gd"))

    def test_dynamic_still_reported_for_member_strings(self):
        """Недоказуемые строки остаются в отчёте: механизм не должен исчезнуть
        вместе с появлением доказуемого случая.

        Отчёт строится для известных Godot-приёмников (ClassDB/Node/Object) —
        произвольный `obj.call(...)` им не является и в отчёт не попадает.
        Именно эти случаи мы и обязаны оставить видимыми.

        В strict недоказуемая динамика остаётся ОТКАЗОМ — это осознанно, и
        допустимый исход здесь любой из двух: отказ со списком мест или
        успешная подготовка с тем же списком в dynamic_references."""
        root = _project({"project.godot": "config_version=5\n",
                         "src/player.gd": PLAYER,
                         "src/member.gd": (
                             'extends Node\n\nfunc probe() -> bool:\n'
                             '\treturn has_method("Player")'
                             ' and Node.has_signal("Player")\n')})
        self.addCleanup(shutil.rmtree, root, True)
        try:
            prepared = symbol_refactor.prepare_rename(root, _action())
        except symbol_refactor.RenameError as exc:
            self.assertIn("member.gd", str(exc),
                          "отказ обязан называть проблемное место")
            return
        joined = " ".join(str(item)
                          for item in (prepared.get("dynamic_references") or []))
        self.assertIn("member.gd", joined,
                      "недоказуемая строка по имени члена обязана остаться "
                      "в отчёте")

    def test_unknown_receiver_string_is_not_a_reference(self):
        """Вызов НЕ из списка известных API работы с именем (`lookup`) — такой
        текст не считаем обращением к символу и не блокируем им переименование.

        Проверять obj.call("Player") здесь нельзя: call() в списке есть, и
        отказ на нём в strict — правильное поведение."""
        root = _project({"project.godot": "config_version=5\n",
                         "src/player.gd": PLAYER,
                         "src/member.gd": (
                             'extends Node\n\nfunc probe(obj: Object):\n'
                             '\tprint(obj.lookup("Player"))\n')})
        self.addCleanup(shutil.rmtree, root, True)
        prepared = symbol_refactor.prepare_rename(root, _action())
        joined = " ".join(str(item)
                          for item in (prepared.get("dynamic_references") or []))
        self.assertNotIn("member.gd", joined)

    def test_other_class_name_apis_are_renamed(self):
        """is_class/class_exists/is_parent_class по контракту тоже принимают
        имя класса — правило не должно работать только для instantiate."""
        root = _project({"project.godot": "config_version=5\n",
                         "src/player.gd": PLAYER,
                         "src/probe.gd": (
                             'extends Node\n\nfunc check() -> bool:\n'
                             '\treturn ClassDB.class_exists("Player")'
                             ' and not ClassDB.is_parent_class("Player")\n')})
        self.addCleanup(shutil.rmtree, root, True)
        prepared = symbol_refactor.prepare_rename(root, _action())
        symbol_refactor.apply_prepared_rename(root, prepared)
        text = _read(root, "src/probe.gd")
        self.assertIn('class_exists("Avatar")', text)
        self.assertIn('is_parent_class("Avatar")', text)


if __name__ == "__main__":
    unittest.main()