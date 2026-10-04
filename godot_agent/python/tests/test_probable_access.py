# -*- coding: utf-8 -*-
"""Этап 3: доступ к режиму probable — он реализован, но недостижим.

Замер. `MODES = ("strict", "probable")` объявлено, `probable` обрабатывается в
`prepare_rename`, но НИКТО его не выставляет: ни панель, ни агент, ни MCP. То
есть функция есть, а путь к ней закрыт.

Почему это важно именно сейчас. После Этапа 1 у системы две РАЗНЫЕ вещи, и их
нельзя смешивать:

  * `allow_unverified` (галочка) — снимает блокировку с НЕДОКАЗАННЫХ ссылок,
    но строка по-прежнему блокирует в strict: ClassDB.instantiate("Player")
    после переименования класса гарантированно падает в рантайме.

  * `probable` — единственный способ обойти ИМЕННО это: в probable динамическая
    ссылка не блокирует (symbol_refactor.py:1718), и пользователь принимает
    риск сознательно.

То есть probable и галочка ДОПОЛНЯЮТ друг друга: галочка не снимает блокировку
с динамики, а probable — снимает. Без доступа к probable галочка даёт
переименование, которое всё равно упрётся в динамику, и единственный оставшийся
способ — дописывать mode вручную в JSON.

Границы этапа: семантику probable НЕ трогаем, только доступность.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import main
from godot_tools import symbol_refactor
from minilich.ml_project_index import build_index


PLAYER = "class_name Player\nextends Node2D\n"
TYPED = "extends Node\n\nvar unit: Player\n"
UNPROVEN = "extends Node\n\nfunc fire(target):\n\ttarget.spawn(Player)\n"
# НЕДОКАЗУЕМАЯ строковая ссылка: имя ЧЛЕНА объекта по строке.
# ВНИМАНИЕ: здесь НЕльзя писать ClassDB.instantiate("X") — с Этапом 5 такой
# вызов признан доказуемым (API принимает имя класса) и переименовывается
# вместе с классом, а strict больше не отказывает. Подробности — в
# test_rename_class_name_strings.
DYNAMIC = ("extends Node\n\nfunc make(node: Node) -> Node:\n"
           "\treturn node.call(\"Player\")\n")


def _project(prefix, files):
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
# __APPEND__
class ProbableSemanticsUnchanged(unittest.TestCase):
    """Этап не меняет смысл probable — он уже реализован и работает."""

    def setUp(self):
        self.root = _project("probable_sem_", {
            "project.godot": "config_version=5\n",
            "src/player.gd": PLAYER,
            "src/typed.gd": TYPED,
            "src/arena.gd": UNPROVEN,
            "src/loader.gd": DYNAMIC})
        self.addCleanup(shutil.rmtree, self.root, True)

    # --- 3.1 strict по умолчанию: динамика блокирует ---
    def test_strict_is_still_the_default(self):
        self.assertEqual(symbol_refactor.MODES[0], "strict")

    def test_strict_blocks_dynamic(self):
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, _action())
        self.assertEqual(getattr(ctx.exception, "code", ""), "unsafe")

    # --- 3.2 probable снимает блокировку с динамики ---
    def test_probable_passes_dynamic(self):
        prepared = symbol_refactor.prepare_rename(
            self.root, _action(mode="probable"))
        self.assertTrue(prepared.get("dynamic_references"))
        self.assertEqual(prepared.get("mode"), "probable")

    def test_probable_does_not_rename_dynamic_string(self):
        """probable снимает БЛОКИРОВНУЮ, а не саму ссылку: обращение по имени
        члена остаётся как есть, потому что переписать его нельзя.

        Именно этим probable отличается от доказуемой строки с именем класса
        (ClassDB.instantiate), которая с Этапом 5 переименовывается."""
        prepared = symbol_refactor.prepare_rename(
            self.root, _action(mode="probable"))
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        with open(os.path.join(self.root, "src", "loader.gd"),
                  "r", encoding="utf-8") as handle:
            self.assertIn('node.call("Player")', handle.read())

    # --- 3.3 probable и галочка НЕ взаимозаменяемы ---
    def test_flag_alone_does_not_unblock_dynamic(self):
        """Ключевое различие режимов: галочка не снимает блокировку с динамики.
        Если бы это было не так, probable стал бы не нужен."""
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(
                self.root, _action(allow_unverified=True))

    def test_flag_with_probable_reaches_dynamic(self):
        prepared = symbol_refactor.prepare_rename(
            self.root, _action(mode="probable", allow_unverified=True))
        self.assertEqual(prepared.get("mode"), "probable")


class ModeReachesAction(unittest.TestCase):
    """Выбранный режим должен доезжать до действия без потерь."""

    def test_project_command_passes_mode(self):
        """Путь агента: project_command -> rename_symbol."""
        import high_level_actions
        root = _project("probable_cmd_", {"project.godot": "config_version=5\n"})
        self.addCleanup(shutil.rmtree, root, True)
        result = high_level_actions.compile_action(root, {
            "action": "project_command", "command": {
                "type": "rename_symbol", "kind": "class_name",
                "declaration": "res://src/player.gd:1",
                "old_name": "Player", "new_name": "Avatar",
                "mode": "probable"}})
        self.assertEqual(result.get("mode"), "probable")

    def test_unknown_mode_is_still_rejected(self):
        root = _project("probable_bad_", {"project.godot": "config_version=5\n"})
        self.addCleanup(shutil.rmtree, root, True)
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(root, _action(mode="turbo"))
        self.assertIn("mode", str(ctx.exception))
# __APPEND__
class PanelCanChooseMode(unittest.TestCase):
    """Панель обязана давать ВИДИМЫЙ выбор, а не молчаливый."""

    PANEL = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir,
                         "agent_panel.gd")

    def setUp(self):
        with open(self.PANEL, "r", encoding="utf-8") as handle:
            self.source = handle.read()

    def test_panel_has_mode_choice_control(self):
        self.assertRegex(
            self.source,
            r"rename_mode|probable_toggle|mode_select",
            "в панели нет элемента выбора режима")

    def test_panel_persists_mode_choice(self):
        """Выбор должен переживать перезапуск редактора."""
        self.assertRegex(self.source, r"func\s+_save_rename_mode")
        self.assertRegex(self.source, r"func\s+_load_rename_mode")

    def test_panel_sends_mode_in_policy_body(self):
        match = re.search(r"func\s+_policy_body.*?\n\nfunc", self.source, re.S)
        self.assertIsNotNone(match, "не найдена _policy_body")
        self.assertIn("rename_mode", match.group(0))

    def test_mode_default_is_strict(self):
        """Дефолт обязан остаться strict: включённая по умолчанию галочка из
        Этапа 1 не должна молча включать probable, потому что probable снимает
        блокировку с динамических ссылок.

        Проверяем не «в коде нет слова probable» (оно законно встречается как
        принимаемое значение), а конкретную границу: ОТСУТСТВИЕ файла
        настроек возвращает strict.
        """
        match = re.search(r"func\s+_load_rename_mode.*?\n\nfunc",
                          self.source, re.S)
        self.assertIsNotNone(match, "не найден загрузчик режима")
        body = match.group(0)
        no_file = re.search(
            r"if not FileAccess\.file_exists\(RENAME_MODE_SETTING_FILE\):"
            r"\s*\n\s*return\s+\"([a-z]+)\"", body)
        self.assertIsNotNone(
            no_file, "нет явного возврата при отсутствии файла настроек")
        self.assertEqual(
            no_file.group(1), "strict",
            "без файла настроек режим обязан быть strict, а не probable")


class ConfirmationExplainsRisk(unittest.TestCase):
    """Текст подтверждения обязан объяснять риск probable."""

    def test_probable_is_named_in_confirmation_text(self):
        root = _project("probable_text_", {
            "project.godot": "config_version=5\n",
            "src/player.gd": PLAYER,
            "src/typed.gd": TYPED,
            "src/loader.gd": DYNAMIC})
        self.addCleanup(shutil.rmtree, root, True)
        prepared = symbol_refactor.prepare_rename(
            root, _action(mode="probable"))
        public = symbol_refactor.public_prepared(prepared)
        public["action"] = "rename_symbol"
        self.assertIn("probable", main._describe_action(public))

    def test_probable_text_mentions_dynamic_risk(self):
        """Пользователь обязан понять, ЧТО именно он соглашается оставить
        непроверенным — иначе «probable» звучит как безобидное ускорение."""
        root = _project("probable_dyn_", {
            "project.godot": "config_version=5\n",
            "src/player.gd": PLAYER,
            "src/loader.gd": DYNAMIC})
        self.addCleanup(shutil.rmtree, root, True)
        prepared = symbol_refactor.prepare_rename(
            root, _action(mode="probable"))
        public = symbol_refactor.public_prepared(prepared)
        public["action"] = "rename_symbol"
        self.assertRegex(main._describe_action(public).lower(),
                         r"динамическ|строк")


if __name__ == "__main__":
    unittest.main()