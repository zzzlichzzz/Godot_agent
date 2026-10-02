# -*- coding: utf-8 -*-
"""Этап 4: полнота семантического индекса — сужение отказа с доказательством.

План предупреждал: отказ может быть осознанным («не знаем весь проект — не
обещаем ничего»), поэтому сузить его можно только с доказательством.
Измерением установлено обратное предположению плана:

  1. Отказ УЖЕ не глобальный в важном смысле. Файл, который парсер осилил,
     ничего не блокирует. Блокирует ТОЛЬКО файл со статусом `partial`
     (gd_semantic_parser.py:387 — «ok» если нет errors, иначе «partial»).

  2. Отказ срабатывает по НАЛИЧИЮ partial, а НЕ по влиянию на символ.
     Проверено: файл с синтаксической ошибкой блокирует переименование
     `health`, хотя к `health` никакого отношения не имеет.

  3. Ключевое: разбор файла со статусом `partial` ПРИГОДЕН. Замерено на файле
     с ошибкой в конце:

         parse_status=partial
         errors=['line 6: declaration without a name']
         declarations=[('function','health_helper'), ('parameter','health'),
                       ('variable','unit')]
         references=[..., ('BaseEnemy','type'), ...]

     Парсер знает, что `health` — параметр, а `BaseEnemy` — тип. Отказ
     выбрасывает ДОКАЗУЕМЫЕ сведения и заставляет разбираться вручную там,
     где мы и так всё знаем.

Значит правильный отказ — не «файл не разобран», а «в ЭТОМ файле мы не
уверены»: сузить его до случаев, где сломанный файл действительно может
касаться нашего символа, и честно сказать о риске в остальных.
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


BASE = ('class_name BaseEnemy\nextends Node\n\nvar health := 10\n\n'
        'func take_damage(n: int) -> int:\n\thealth -= n\n\treturn health\n')
MIDDLE = ('extends "res://src/base.gd"\n\nfunc tick() -> int:\n'
          '\thealth -= 1\n\treturn health\n')
TYPED = "extends Node\n\nvar unit: BaseEnemy\n"
ARENA = "extends Node\n\nfunc fire(unit: BaseEnemy) -> void:\n\tunit.take_damage(1)\n"

# partial, разбор ПРИГОДЕН, но символа НЕ упоминает: на него отказ не должен
# распространяться. Именно такой случай разблокирует сужение отказа.
BROKEN_BUT_USABLE = ('extends Node\n\nfunc helper(amount):\n'
                     '\tvar counter := 1\n\treturn counter\n\tvar = \n')
# partial, и файл УЧАСТВУЕТ в иерархии: его игнорировать нельзя.
#
# Замер: парсер ставит `partial` ТОЛЬКО на «объявлении без имени»
# (gd_semantic_parser.py:387). Проверены распространённые повреждения
# синтаксиса — `func broken(:`, незакрытый блок, `end` без блока, смешанные
# отступы — и все они дают `ok`. Поэтому фикстура строит именно
# «объявление без имени», иначе тест проверял бы несуществующий случай.
BROKEN_IN_HIERARCHY = 'extends "res://src/base.gd"\n\nvar = \n'


def _project(files, prefix="stage4_"):
    root = tempfile.mkdtemp(prefix=prefix)
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    build_index(root)
    return root


def _clean(**extra):
    files = {"project.godot": "config_version=5\n", "src/base.gd": BASE,
             "src/slime.gd": MIDDLE, "src/typed.gd": TYPED,
             "src/arena.gd": ARENA}
    files.update(extra)
    return files


def _action(**extra):
    action = {"action": "rename_symbol", "kind": "variable",
              "declaration": "res://src/base.gd:4",
              "old_name": "health", "new_name": "hp"}
    action.update(extra)
    return action
# __APPEND__
class UnrelatedBrokenFileDoesNotBlock(unittest.TestCase):
    """Сломанный файл ВНЕ иерархии и БЕЗ упоминания имени — не повод отказ."""

    def setUp(self):
        self.root = _project(_clean(**{"src/broken.gd": BROKEN_BUT_USABLE}))
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_rename_succeeds(self):
        """Главное требование этапа: чужой сломанный файл не блокирует."""
        prepared = symbol_refactor.prepare_rename(self.root, _action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        with open(os.path.join(self.root, "src", "base.gd"),
                  encoding="utf-8") as handle:
            self.assertIn("var hp := 10", handle.read())

    def test_broken_file_reported_as_warning(self):
        """Пользователь обязан УЗНАТЬ, что в проекте есть неразобранный файл:
        переименование прошло, но это не значит «проект полностью проверен»."""
        prepared = symbol_refactor.prepare_rename(self.root, _action())
        joined = " ".join(str(item) for item in (prepared.get("warnings") or []))
        self.assertIn("broken.gd", joined)

    def test_broken_file_itself_is_not_written(self):
        prepared = symbol_refactor.prepare_rename(self.root, _action())
        self.assertNotIn("res://src/broken.gd",
                         [item["path"] for item in prepared["files"]])

    def test_hierarchy_still_fully_renamed(self):
        """Сужение отказа не имеет права тихо уменьшать объём правильной
        работы: доказуемые ссылки в НЕСЛОМАННЫХ файлах обязаны обновиться."""
        prepared = symbol_refactor.prepare_rename(self.root, _action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        with open(os.path.join(self.root, "src", "slime.gd"),
                  encoding="utf-8") as handle:
            self.assertIn("hp -= 1", handle.read())


class BrokenFileInsideHierarchyStillBlocks(unittest.TestCase):
    """Файл В иерархии отказать обязан: мы не знаем, что в нём переименовать."""

    def setUp(self):
        self.root = _project(_clean(**{"src/slime_broken.gd":
                                       BROKEN_IN_HIERARCHY}))
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_refusal_remains(self):
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, _action())

    def test_nothing_written_on_refusal(self):
        try:
            symbol_refactor.prepare_rename(self.root, _action())
        except symbol_refactor.RenameError:
            pass
        with open(os.path.join(self.root, "src", "base.gd"),
                  encoding="utf-8") as handle:
            self.assertIn("var health := 10", handle.read())


class BrokenFileMentioningSymbolNeedsDecision(unittest.TestCase):
    """Сломанный файл, УПОМИНАЮЩИЙ наше имя, нельзя молча пропустить.

    Парсер разобрал файл частично, и мы НЕ знаем, все ли вхождения он увидел.
    Отказ — безопасный выбор; при разрешении такой файл обязан быть назван.
    """

    def setUp(self):
        self.root = _project(_clean(**{
            "src/broken.gd": ('extends Node\n\nfunc helper(health):\n'
                              '\tvar unit: BaseEnemy\n\treturn unit\n\tvar = \n')}))
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_symbol_in_partial_file_is_flagged_or_refused(self):
        try:
            prepared = symbol_refactor.prepare_rename(self.root, _action())
        except symbol_refactor.RenameError:
            return  # безопасный отказ допустим
        notes = prepared.get("unverified_references") or []
        warnings = " ".join(str(item)
                            for item in (prepared.get("warnings") or []))
        self.assertTrue(
            any("broken.gd" in str(n) for n in notes) or "broken.gd" in warnings,
            "упоминание символа в неразобранном файле обязано попасть в отчёт")
# __APPEND__
class PartialParseIsNotSilentlyTrusted(unittest.TestCase):
    """Разбор partial пригоден, но это НЕ значит «мы всё доказали»."""

    def test_shadowed_parameter_in_partial_file_is_not_renamed(self):
        """В сломанном файле есть параметр `health` — доказанно другая
        сущность. Переименовывать её нельзя даже при суженом отказе."""
        root = _project(_clean(**{
            "src/broken.gd": ('extends Node\n\nfunc helper(health):\n'
                              '\treturn health\n\tvar = \n')}))
        self.addCleanup(shutil.rmtree, root, True)
        try:
            prepared = symbol_refactor.prepare_rename(root, _action())
        except symbol_refactor.RenameError:
            return
        symbol_refactor.apply_prepared_rename(root, prepared)
        with open(os.path.join(root, "src", "broken.gd"),
                  encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("func helper(health)", text)
        self.assertNotIn("helper(hp)", text)


class CleanProjectUnaffected(unittest.TestCase):
    """Регресс: без сломанных файлов поведение прежнее."""

    def setUp(self):
        self.root = _project(_clean())
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_no_partial_warnings_on_clean_project(self):
        prepared = symbol_refactor.prepare_rename(self.root, _action())
        joined = " ".join(str(item) for item in (prepared.get("warnings") or []))
        self.assertNotIn("не удалось разобрать", joined.lower())

    def test_clean_rename_still_works(self):
        prepared = symbol_refactor.prepare_rename(self.root, _action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        with open(os.path.join(self.root, "src", "base.gd"),
                  encoding="utf-8") as handle:
            self.assertIn("var hp := 10", handle.read())


if __name__ == "__main__":
    unittest.main()