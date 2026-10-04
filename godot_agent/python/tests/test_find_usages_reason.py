# -*- coding: utf-8 -*-
"""Синтетика: read-поверхности обязаны называть ПРИЧИНУ недоказанности.

Замер (дыра №6). Прошлая серия этапов закрыла раскрытие в пяти местах:
check_action, мост write preview/apply, подтверждение панели, ответ после
записи, чеклист. Но осталась шестая поверхность — самая важная для модели:

    find_symbol_usages -> res://src/arena.gd:4 conf=probable note=None
    _format_usages    -> res://src/arena.gd:4:15 [identifier, probable]

То есть модель видит слово «вероятно» и НЕ видит почему. И это первый шаг,
который она делает перед переименованием: именно здесь решается, доказуемо
ли место. Без причины модель вынуждена гадать — а гадание и есть та неопределённость,
из-за которой затевался весь этап.

Информация вычисляется (функция _unverified_reason уже есть), но не доходит
до читателя. Ровно та же патология, что была в check_action и мосте.
"""
import os
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
CLEAN = "extends Node\n"

# Переменная-член с НЕТИПИЗИРОВАННЫМ ресивером: самый частый реальный случай
# из замера проекта (14 из 24 недоказанных). Причина обязана называть
# ресивер, иначе пользователь не понимает, что именно аннотировать.
UNIT = "extends Node\n\nvar score := 0\n\nfunc add() -> int:\n\tscore += 1\n\treturn score\n"
UNPROVEN_RECEIVER = "extends Node\n\nfunc fire(target):\n\ttarget.score = 5\n"


def _project(prefix, files):
    root = tempfile.mkdtemp(prefix=prefix)
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    build_index(root)
    return root


def _class_action(**extra):
    action = {"action": "find_symbol_usages", "kind": "class_name",
              "declaration": "res://src/player.gd:1",
              "old_name": "Player", "new_name": "Avatar"}
    action.update(extra)
    return action


def _variable_action(**extra):
    action = {"action": "find_symbol_usages", "kind": "variable",
              "declaration": "res://src/unit.gd:3",
              "old_name": "score", "new_name": "points"}
    action.update(extra)
    return action


class ProbableCarriesReason(unittest.TestCase):
    """Недоказанное место обязано объяснять себя."""

    def setUp(self):
        self.root = _project("reason_", {
            "project.godot": "config_version=5\n",
            "src/player.gd": PLAYER,
            "src/typed.gd": TYPED,
            "src/arena.gd": UNPROVEN})
        self.addCleanup(shutil.rmtree, self.root, True)

    def _usages(self, **extra):
        result = symbol_refactor.find_references(
            self.root, _class_action(**extra))
        return {("%s:%s" % (item["path"], item["line"])): item
                for item in result["usages"]}

    # --- E.1 у probable есть причина ---
    def test_probable_place_has_reason(self):
        usages = self._usages()
        probable = [item for item in usages.values()
                    if item["confidence"] == "probable"]
        self.assertTrue(probable, list(usages.values()))
        for item in probable:
            self.assertTrue(
                (item.get("note") or "").strip(),
                "недоказанное место обязано объяснять себя: %s" % item)

    def test_reason_is_not_empty_string(self):
        """Защита от тихой подмены: пустая строка — это то же отсутствие
        причины, только с лишним шагом."""
        usages = self._usages()
        for item in usages.values():
            if item["confidence"] == "probable":
                self.assertIsInstance(item.get("note"), str)
                self.assertNotEqual((item["note"] or "").strip(), "")

    # --- E.2 доказанные места НЕ получают ложной причины ---
    def test_proven_places_have_no_reason_noise(self):
        usages = self._usages()
        proven = [item for item in usages.values()
                  if item["confidence"] == "proven"]
        self.assertTrue(proven)
        for item in proven:
            self.assertFalse(
                (item.get("note") or "").strip(),
                "доказанному месту причина не нужна: %s" % item)

    # --- E.3 причина полезна: называет ресивер, который надо аннотировать ---
    def test_reason_names_untyped_receiver(self):
        root = _project("reason_recv_", {
            "project.godot": "config_version=5\n",
            "src/unit.gd": UNIT,
            "src/arena.gd": UNPROVEN_RECEIVER})
        self.addCleanup(shutil.rmtree, root, True)
        result = symbol_refactor.find_references(root, _variable_action())
        probable = [item for item in result["usages"]
                    if item["confidence"] == "probable"]
        self.assertTrue(probable, result["usages"])
        notes = " ".join(str(item.get("note") or "") for item in probable)
        self.assertIn("target", notes)

    # __APPEND__
class AnalyzeAndFormatCarryReason(unittest.TestCase):
    """Причина обязана дойти до текста, который читает модель."""

    def setUp(self):
        self.root = _project("reason_fmt_", {
            "project.godot": "config_version=5\n",
            "src/player.gd": PLAYER,
            "src/typed.gd": TYPED,
            "src/arena.gd": UNPROVEN})
        self.addCleanup(shutil.rmtree, self.root, True)

    # --- E.4 analyze_rename.risks называет причину ---
    def test_analyze_risks_include_reason(self):
        analysis = symbol_refactor.analyze_rename(
            self.root, _class_action(action="analyze_rename"))
        risks = analysis.get("risks") or []
        risky = [item for item in risks if "probable" in str(item)]
        self.assertTrue(risky, risks)
        for item in risky:
            self.assertIn(" — ", str(item), item)

    # --- E.5 текст для модели содержит причину ---
    def test_format_usages_shows_reason(self):
        result = symbol_refactor.find_references(self.root, _class_action())
        text = main._format_usages(result)
        line = [item for item in text.splitlines()
                if "probable" in item]
        self.assertTrue(line, text)
        for item in line:
            self.assertIn(" — ", item, item)

    def test_format_analysis_shows_reason(self):
        analysis = symbol_refactor.analyze_rename(
            self.root, _class_action(action="analyze_rename"))
        text = main._format_analysis(analysis)
        risky = [item for item in text.splitlines()
                 if "probable" in item]
        self.assertTrue(risky, text)
        for item in risky:
            self.assertIn(" — ", item, item)

    # --- E.6 обратная честность: где всё доказано, причины НЕ выдумываются ---
    def test_clean_project_has_no_reason_noise(self):
        root = _project("reason_clean_", {
            "project.godot": "config_version=5\n",
            "src/player.gd": PLAYER,
            "src/typed.gd": TYPED,
            "src/arena.gd": CLEAN})
        self.addCleanup(shutil.rmtree, root, True)
        result = symbol_refactor.find_references(root, _class_action())
        self.assertEqual(result["probable_count"], 0, result["usages"])
        for item in result["usages"]:
            self.assertFalse((item.get("note") or "").strip())

    def test_clean_project_text_has_no_reason_markers(self):
        root = _project("reason_clean2_", {
            "project.godot": "config_version=5\n",
            "src/player.gd": PLAYER,
            "src/typed.gd": TYPED,
            "src/arena.gd": CLEAN})
        self.addCleanup(shutil.rmtree, root, True)
        result = symbol_refactor.find_references(root, _class_action())
        text = main._format_usages(result)
        self.assertNotIn(" — ", text)

    # --- E.7 динамические ссылки не должны сломаться ---
    def test_dynamic_still_carries_its_reason(self):
        root = _project("reason_dyn_", {
            "project.godot": "config_version=5\n",
            "src/player.gd": PLAYER,
            "src/typed.gd": TYPED,
            "src/arena.gd": CLEAN,
            "src/loader.gd": ("extends Node\n\nfunc make() -> Node:\n"
                              "\treturn ClassDB.instantiate(\"Player\")\n")})
        self.addCleanup(shutil.rmtree, root, True)
        result = symbol_refactor.find_references(root, _class_action())
        dynamic = [item for item in result["usages"]
                   if item["confidence"] == "dynamic"]
        self.assertTrue(dynamic, result["usages"])
        for item in dynamic:
            self.assertTrue((item.get("note") or "").strip())

    # --- E.8 тень доказанно чужое место: в отчёте её быть не должно ---
    def test_local_shadow_is_not_reported_as_unproven(self):
        """Найдено при аудите: одиночная тень `var score = 1` попадала в
        probable с причиной «файл не входит в иерархию». Это ложь — тень
        доказанно другая сущность, и prepare_rename её молча пропускает.
        Модель получала ложную недоказанную ссылку и завышенный счётчик."""
        root = _project("reason_shadow_", {
            "project.godot": "config_version=5\n",
            "src/unit.gd": UNIT,
            "src/other.gd": ("extends Node\n\nfunc plain() -> int:\n"
                             "\tvar score = 1\n\treturn score\n")})
        self.addCleanup(shutil.rmtree, root, True)
        result = symbol_refactor.find_references(root, _variable_action())
        self.assertEqual(
            result["probable_count"], 0,
            "тень не должна считаться недоказанной: %s" % result["usages"])
        for item in result["usages"]:
            self.assertNotEqual(item["confidence"], "probable")
            self.assertFalse((item.get("note") or "").strip())


if __name__ == "__main__":
    unittest.main()