# -*- coding: utf-8 -*-
"""Синтетические тесты п.1.1: переименование функции в иерархии наследования.

Баг: _find_subclasses вызывался только для kind == "variable". Для функции
вызовы в подклассах обновлялись, а сами объявления-override — нет, плюс
вызов через ресивер, типизированный как ПОДКЛАСС, считался неоднозначностью
(all_target_classes содержал только сам класс). Итог — вызов несуществующего
метода при рапорте «успешно».
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


BASE_SCRIPT = """class_name EnemyBase
extends Node

func take_damage(amount: int) -> int:
\tvar left = amount - 1
\treturn left
"""

BASE_WITH_SIGNAL = """class_name SignalBase
extends Node

signal died

func kill() -> void:
\tdied.emit()
"""


class OverrideHierarchy(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_overrides_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self._write("project.godot", "config_version=5\n")

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

    def _action(self, kind="function", path="res://src/enemy_base.gd", line=4,
                old="take_damage", new="apply_damage"):
        return {"action": "rename_symbol", "kind": kind,
                "declaration": "%s:%d" % (path, line),
                "old_name": old, "new_name": new}


    # --- 1.1.1 базовый класс + override в подклассе, без self-вызовов ---
    def test_override_declaration_is_renamed(self):
        self._write("src/enemy_base.gd", BASE_SCRIPT)
        self._write("src/enemy.gd", """extends EnemyBase

func take_damage(amount: int) -> int:
\treturn 0
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("res://src/enemy.gd", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        base = self._read("src/enemy_base.gd")
        enemy = self._read("src/enemy.gd")
        self.assertIn("func apply_damage(amount: int) -> int:", base)
        self.assertIn("func apply_damage(amount: int) -> int:", enemy)
        self.assertNotIn("take_damage", enemy)

    # --- 1.1.2 override с self-вызовами (self.x() и голым x()) ---
    def test_override_self_calls_are_renamed(self):
        self._write("src/enemy_base.gd", BASE_SCRIPT)
        self._write("src/enemy.gd", """extends EnemyBase

func take_damage(amount: int) -> int:
\tif amount > 0:
\t\tself.take_damage(amount - 1)
\treturn take_damage(amount)
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        enemy = self._read("src/enemy.gd")
        self.assertNotIn("take_damage", enemy)
        self.assertIn("func apply_damage(amount: int) -> int:", enemy)
        self.assertIn("self.apply_damage(amount - 1)", enemy)

    # --- 1.1.3 вызов через ресивер, типизированный как подкласс ---
    def test_call_through_subclass_typed_receiver_is_renamed(self):
        self._write("src/enemy_base.gd", BASE_SCRIPT)
        self._write("src/enemy.gd", """class_name Enemy
extends EnemyBase

func take_damage(amount: int) -> int:
\treturn amount
""")
        self._write("src/arena.gd", """extends Node

var enemy: Enemy

func hit() -> int:
\treturn enemy.take_damage(3)
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("res://src/arena.gd", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        self.assertIn("enemy.apply_damage(3)", self._read("src/arena.gd"))
    # --- 1.1.4 подкласс с СОБСТВЕННЫМ одноимённым членом ---
    # Тень переменной перекрывает метод базового класса: self.take_damage()
    # в подклассе — это уже НЕ метод. Молча переименовать такое нельзя.
    def test_subclass_own_same_named_member_is_refused(self):
        self._write("src/enemy_base.gd", BASE_SCRIPT)
        self._write("src/enemy.gd", """extends EnemyBase

var take_damage = 0

func apply_now(amount: int) -> int:
\treturn self.take_damage
""")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("take_damage", self._read("src/enemy.gd"))

    # --- 1.1.5 сигнал: override-объявление в подклассе тоже переименовывается ---
    def test_signal_override_declaration_is_renamed(self):
        self._write("src/signal_base.gd", BASE_WITH_SIGNAL)
        self._write("src/tower.gd", """extends SignalBase

signal died

func kill() -> void:
\tdied.emit()
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(
            self.root, self._action("signal", "res://src/signal_base.gd", 4,
                                    "died", "was_destroyed"))
        self.assertIn("res://src/tower.gd", [f["path"] for f in prepared["files"]])
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        tower = self._read("src/tower.gd")
        self.assertIn("signal was_destroyed", tower)
        self.assertIn("was_destroyed.emit()", tower)
        self.assertNotIn("died", tower)

    # --- 1.1.6 предохранитель: остаточные объявления старого имени в иерархии ---
    def test_hierarchy_guard_rejects_uncovered_old_declarations(self):
        declarations = [{"path": "res://src/enemy.gd", "kind": "function",
                         "name": "take_damage", "owner": "script",
                         "line": 3, "start": 10, "end": 20}]
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor._assert_hierarchy_renamed(
                "function", "take_damage", "apply_damage", {"res://src/enemy.gd"},
                set(), declarations)
        self.assertIn("take_damage", str(ctx.exception))

    # --- Аудит 1.1: глубокая иерархия (внук) и подкласс через 2 уровня ---
    def test_grandchild_override_is_renamed(self):
        self._write("src/enemy_base.gd", BASE_SCRIPT)
        self._write("src/enemy.gd", """class_name Enemy
extends EnemyBase

func take_damage(amount: int) -> int:
\treturn amount
""")
        self._write("src/boss.gd", """extends Enemy

func take_damage(amount: int) -> int:
\treturn self.take_damage(amount) * 2
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        paths = [f["path"] for f in prepared["files"]]
        self.assertIn("res://src/boss.gd", paths)
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        boss = self._read("src/boss.gd")
        self.assertIn("func apply_damage(amount: int) -> int:", boss)
        self.assertIn("self.apply_damage(amount) * 2", boss)
        self.assertNotIn("take_damage", boss)

    # --- Аудит 1.1: подкласс вне политики записи не должен ломать отказ ---
    # Переименование в addons запрещено политикой: операция обязана быть
    # отклонена, а не «успешно» переписать пол-проекта.
    def test_subclass_outside_write_policy_is_refused(self):
        self._write("src/enemy_base.gd", BASE_SCRIPT)
        self._write("addons/pack/enemy.gd", """extends EnemyBase

func take_damage(amount: int) -> int:
\treturn 0
""")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("take_damage", self._read("addons/pack/enemy.gd"))

    # --- Аудит 1.1: комментарий в подклассе не трогается, строковый литерал
    # (динамическая ссылка) — честно блокирует переименование ---
    def test_comment_in_subclass_stays_intact(self):
        self._write("src/enemy_base.gd", BASE_SCRIPT)
        self._write("src/enemy.gd", """extends EnemyBase

# take_damage вызывается здесь намеренно
func take_damage(amount: int) -> int:
\treturn amount
""")
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, self._action())
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        enemy = self._read("src/enemy.gd")
        self.assertIn("# take_damage вызывается здесь намеренно", enemy)
        self.assertIn("func apply_damage(amount: int) -> int:", enemy)

    def test_string_literal_reference_blocks_rename(self):
        self._write("src/enemy_base.gd", BASE_SCRIPT)
        self._write("src/enemy.gd", """extends EnemyBase

func take_damage(amount: int) -> int:
\tvar label = "take_damage"
\treturn amount
""")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("строковая", str(ctx.exception))

    # --- Аудит 1.1: тень ПАРАМЕТРА внутри подкласса перекрывает метод ---
    def test_subclass_parameter_shadowing_is_refused(self):
        self._write("src/enemy_base.gd", BASE_SCRIPT)
        self._write("src/enemy.gd", """extends EnemyBase

func apply_now(take_damage: int) -> int:
\treturn take_damage
""")
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, self._action())
        self.assertIn("func apply_now(take_damage: int) -> int:",
                      self._read("src/enemy.gd"))


if __name__ == "__main__":
    unittest.main()


