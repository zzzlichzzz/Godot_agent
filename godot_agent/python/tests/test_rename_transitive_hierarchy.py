# -*- coding: utf-8 -*-
"""Этап 2: транзитивное наследование КАК ДОКАЗАТЕЛЬСТВО — регресс-барьер.

История этапа важнее самого кода. План формулировал цель «self.x() во внуке
должен распознаваться» и предполагал, что не распознаётся. Измерением
установлено обратное: `_find_subclasses` обходит иерархию BFS-ом, потомки
находятся на ЛЮБОЙ глубине, и `self.x` во внуке уже переименовывается. Правки
в `_reference_is_safe` были бы лечением не того симптома, поэтому их не было.

Этот файл фиксирует найденное поведение тестом: границы, найденные замером,
должны быть защищены от следующего, кто полезет в код ради другой задачи и
сломает их, не заметив.

Ключевая тонкость, которую легко сломать «по сходству»: override и тень —
противоположные случаи, и различает их ВИД объявления, а не глубина иерархии.
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


BASE = ('class_name BaseEnemy\nextends Node\n\nvar health := 10\n\n'
        'func take_damage(n: int) -> int:\n\thealth -= n\n\treturn health\n')
MIDDLE = ('extends "res://src/base.gd"\n\nfunc tick() -> int:\n'
          '\thealth -= 1\n\treturn health\n')
# Внук (2 уровня): только обращения через self, своего объявления нет.
GRANDCHILD_CALLS = ('extends "res://src/slime.gd"\n\nfunc boss_hit() -> int:\n'
                    '\tself.health -= 5\n\treturn self.take_damage(2)\n')
# Внук объявляет var того же вида — это override, а не тень.
GRANDCHILD_OVERRIDE = ('extends "res://src/slime.gd"\n\nvar health := 999\n\n'
                       'func boss_hit() -> int:\n'
                       '\tself.health -= 5\n\treturn self.health\n')
# Внук объявляет ПЕРЕМЕННУЮ с именем МЕТОДА базы — другая сущность.
GRANDCHILD_SHADOW = ('extends "res://src/slime.gd"\n\nvar take_damage = 0\n\n'
                     'func boss_hit() -> int:\n\treturn self.take_damage\n')
# Посторонняя ссылка на класс. Тип ресивера отсутствует, поэтому она НЕ
# доказуема и в strict отказала бы — для Этапа 1 это и был исходный случай.
# Здесь она мешала: проверяем class_name, а не строгость, поэтому в проекте
# без Stage 1 берём доказуемую ссылку через аннотированный ресивер.
ARENA = "extends Node\n\nfunc fire(unit: BaseEnemy) -> void:\n\tunit.take_damage(1)\n"


class TransitiveHierarchy(unittest.TestCase):
    """A <- B <- C: потомки любой глубины доказуемо наши."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_transitive_")
        self.addCleanup(shutil.rmtree, self.root, True)

    def _write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def _read(self, rel):
        with open(os.path.join(self.root, *rel.split("/")),
                  "r", encoding="utf-8") as handle:
            return handle.read()

    def _reindex(self):
        ml_project_index._MEM_CACHE.clear()
        ml_project_index.build_index(self.root)

    def _project(self, grandchild=GRANDCHILD_CALLS):
        self._write("project.godot", "config_version=5\n")
        self._write("src/base.gd", BASE)
        self._write("src/slime.gd", MIDDLE)
        self._write("src/boss.gd", grandchild)
        self._write("src/arena.gd", ARENA)
        self._reindex()

    def _rename(self, kind, name, new, line):
        action = {"action": "rename_symbol", "kind": kind,
                  "declaration": "res://src/base.gd:%d" % line,
                  "old_name": name, "new_name": new}
        prepared = symbol_refactor.prepare_rename(self.root, action)
        symbol_refactor.apply_prepared_rename(self.root, prepared)
        return prepared

    # --- 2.1 self.member во внуке (2 уровня) ПЕРЕИМЕНОВЫВАЕТСЯ ---
    def test_self_member_in_grandchild_is_renamed(self):
        self._project(GRANDCHILD_CALLS)
        prepared = self._rename("variable", "health", "hp", 4)
        boss = self._read("src/boss.gd")
        # Прямое обращение через self во ВНУКЕ доказуемо: внук — точно
        # потомок, а self указывает на его собственный класс.
        self.assertIn("self.hp -= 5", boss)
        self.assertNotIn("self.health", boss)
        self.assertIn("res://src/boss.gd",
                      [item["path"] for item in prepared["files"]])

    def test_grandchild_rename_needs_no_unverified_flag(self):
        """Транзитивность — это ДОКАЗАТЕЛЬСТВО, а не допущение. Значит strict
        должен справиться без allow_unverified: иначе мы признали бы, что не
        доказали, хотя доказали."""
        self._project(GRANDCHILD_CALLS)
        prepared = self._rename("variable", "health", "hp", 4)
        self.assertEqual(prepared.get("unverified_references") or [], [],
                         "ссылка во внуке доказуема и не должна быть "
                         "недоказанной")

    def test_whole_chain_is_renamed(self):
        self._project(GRANDCHILD_CALLS)
        self._rename("variable", "health", "hp", 4)
        self.assertIn("var hp := 10", self._read("src/base.gd"))
        self.assertIn("hp -= 1", self._read("src/slime.gd"))
        self.assertIn("self.hp -= 5", self._read("src/boss.gd"))

    # --- 2.2 method() во внуке ПЕРЕИМЕНОВЫВАЕТСЯ ---
    def test_self_method_call_in_grandchild_is_renamed(self):
        self._project(GRANDCHILD_CALLS)
        self._rename("function", "take_damage", "apply_damage", 6)
        self.assertIn("self.apply_damage(2)", self._read("src/boss.gd"))
        self.assertIn("func apply_damage", self._read("src/base.gd"))

    def test_method_call_in_grandchild_needs_no_flag(self):
        self._project(GRANDCHILD_CALLS)
        prepared = self._rename("function", "take_damage", "apply_damage", 6)
        self.assertEqual(prepared.get("unverified_references") or [], [])

    # __APPEND__
# --- 2.3 override ТОГО ЖЕ вида — переименовывается (это один символ) ---
    def test_grandchild_override_of_same_kind_is_renamed(self):
        """var поверх var — ЭТО override. Если его не переименовать, внук
        получит новое поле, которое ничего не перекрывает, и полиморфизм
        развалится. Замером установлено: так и должно быть."""
        self._project(GRANDCHILD_OVERRIDE)
        self._rename("variable", "health", "hp", 4)
        boss = self._read("src/boss.gd")
        self.assertIn("var hp := 999", boss)
        self.assertIn("self.hp -= 5", boss)

    def test_grandchild_override_keeps_polymorphism_consistent(self):
        """Проверка «а не рассыпалось ли»: объявление во внуке и обращения
        к нему переименовываются ВМЕСТЕ."""
        self._project(GRANDCHILD_OVERRIDE)
        self._rename("variable", "health", "hp", 4)
        self.assertNotIn(
            "health", self._read("src/boss.gd"),
            "во внуке не должно остаться старого имени")

    # --- 2.4 тень РАЗНОГО вида — отказ, даже на втором уровне ---
    def test_grandchild_shadow_of_other_kind_is_refused(self):
        """Переменная с именем МЕТОДА базы — другая сущность, и её нельзя
        переименовать вместе с методом. Отказ обязателен: иначе `self.apply_damage`
        во внуке станет обращением к чужой переменной.

        Отдельно важно, что отказ работает и на глубине 2: прямой наследник
        этим guard'ом ловился, и глубина не должна быть исключением."""
        self._project(GRANDCHILD_SHADOW)
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, {
                "action": "rename_symbol", "kind": "function",
                "declaration": "res://src/base.gd:6",
                "old_name": "take_damage", "new_name": "apply_damage"})
        self.assertIn("var take_damage = 0", self._read("src/boss.gd"))
        self.assertIn("func take_damage", self._read("src/base.gd"))

    def test_refusal_names_the_shadowing_declaration(self):
        """Отказ обязан называть, ЧТО именно помешало: иначе пользователь
        ищет проблему там, где её нет."""
        self._project(GRANDCHILD_SHADOW)
        with self.assertRaises(symbol_refactor.RenameError) as ctx:
            symbol_refactor.prepare_rename(self.root, {
                "action": "rename_symbol", "kind": "function",
                "declaration": "res://src/base.gd:6",
                "old_name": "take_damage", "new_name": "apply_damage"})
        message = str(ctx.exception)
        self.assertIn("take_damage", message)
        self.assertIn("boss.gd", message)

    # --- 2.5 class_name через цепочку ---
    def test_class_name_renamed_through_the_chain(self):
        self._project(GRANDCHILD_CALLS)
        prepared = self._rename("class_name", "BaseEnemy", "Enemy", 1)
        self.assertIn("class_name Enemy", self._read("src/base.gd"))
        touched = [item["path"] for item in prepared["files"]]
        self.assertIn("res://src/arena.gd", touched,
                      "посторонний файл со ссылкой на класс тоже обновлён")

    def test_class_name_rename_has_no_unverified_in_chain(self):
        self._project(GRANDCHILD_CALLS)
        prepared = self._rename("class_name", "BaseEnemy", "Enemy", 1)
        self.assertEqual(
            [n for n in (prepared.get("unverified_references") or [])
             if "boss.gd" in str(n) or "slime.gd" in str(n)], [],
            "наследники не должны давать недоказанных ссылок на class_name")

    # --- 2.6 скрипт ВНЕ иерархии не переименовывается ---
    def test_outside_script_is_not_renamed(self):
        """Скрипт вне иерархии не наследует наш символ.

        Здесь `o` — неаннотированный ресивер, поэтому ссылка недоказуема и
        strict отказывает ЦЕЛИКОМ. Это и есть требуемое поведение: место вне
        иерархии не должно молча переименовываться вместе с нашим символом.
        Отдельно проверяем, что файл остался нетронутым.
        """
        self._project(GRANDCHILD_CALLS)
        self._write("src/outsider.gd", 'extends Node\n\nfunc touch(o):\n\to.health = 1\n')
        self._reindex()
        with self.assertRaises(symbol_refactor.RenameError):
            symbol_refactor.prepare_rename(self.root, {
                "action": "rename_symbol", "kind": "variable",
                "declaration": "res://src/base.gd:4",
                "old_name": "health", "new_name": "hp"})
        self.assertIn("o.health = 1", self._read("src/outsider.gd"))
        # Ничего не применено: отказ на подготовке, а не частичная запись.
        self.assertIn("var health := 10", self._read("src/base.gd"))

    def test_outside_script_is_absent_without_flag(self):
        """Файл вне иерархии не попадает в транзакцию, пока недоказанные
        ссылки переименовывать запрещено (strict)."""
        self._project(GRANDCHILD_CALLS)
        self._write("src/outsider.gd", 'extends Node\n\nfunc touch(o):\n\to.health = 1\n')
        self._reindex()
        action = {"action": "rename_symbol", "kind": "variable",
                  "declaration": "res://src/base.gd:4",
                  "old_name": "health", "new_name": "hp"}
        try:
            prepared = symbol_refactor.prepare_rename(self.root, action)
        except symbol_refactor.RenameError:
            return  # полный отказ тоже корректен, файл точно не тронут
        self.assertNotIn("res://src/outsider.gd",
                         [item["path"] for item in prepared["files"]])

    def test_outside_script_is_renamed_but_disclosed_with_flag(self):
        """С allow_unverified место вне иерархии ПЕРЕИМЕНОВЫВАЕТСЯ — так
        устроен режим терпимости (Этап 1). Обязательное условие при этом:
        переименование не молчит, а попадает в отчёт с причиной.

        Проверка «а не молчаливое ли это» здесь важнее самой правки: если бы
        outsider.gd менялся без записи в unverified_references, пользователь
        получил бы изменённый файл, о котором не знает.
        """
        self._project(GRANDCHILD_CALLS)
        self._write("src/outsider.gd", 'extends Node\n\nfunc touch(o):\n\to.health = 1\n')
        self._reindex()
        prepared = symbol_refactor.prepare_rename(self.root, {
            "action": "rename_symbol", "kind": "variable",
            "declaration": "res://src/base.gd:4",
            "old_name": "health", "new_name": "hp",
            "allow_unverified": True})
        self.assertIn("res://src/outsider.gd",
                      [item["path"] for item in prepared["files"]])
        notes = prepared.get("unverified_references") or []
        self.assertTrue(
            [n for n in notes if "outsider.gd" in str(n)], notes)
        self.assertEqual(prepared.get("unverified_count"), 1, notes)

    def test_direct_child_still_renamed(self):
        """Прямой наследник — базовый случай этапа. Не должен сломаться, даже
        если правки будут трогать ту же ветку кода."""
        self._write("project.godot", "config_version=5\n")
        self._write("src/base.gd", BASE)
        self._write("src/slime.gd", MIDDLE)
        self._reindex()
        self._rename("variable", "health", "hp", 4)
        self.assertIn("hp -= 1", self._read("src/slime.gd"))
        self.assertIn("var hp := 10", self._read("src/base.gd"))


if __name__ == "__main__":
    unittest.main()