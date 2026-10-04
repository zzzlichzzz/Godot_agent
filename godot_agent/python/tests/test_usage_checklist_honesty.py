# -*- coding: utf-8 -*-
"""Синтетика: чеклист мест не должен обещать то, что не произойдёт.

Замер (Этап B). `analyze_rename` — read-only анализ, он не знает ни про
allow_unverified, ни про mode. `_usage_checklist` строил галочки так:

    checked = confidence != "dynamic"

А confidence для недоказанной ссылки равен "probable", значит на замере:

    usage res://src/arena.gd:4 conf=probable
    checklist: checked=True res://src/arena.gd:4:15   ← обещание

Панель показывает место отмеченным, пользователь жмёт «да» — а при снятой
галочке переименование ОТКАЗЫВАЕТСЯ целиком. Обещание лживое в обе стороны:
в strict место не будет переименовано (отказ), в probable тоже (мы его не
трогаем). Единственный случай, когда оно правда, — allow_unverified=true.

Значит `checked` обязан зависеть от того, ПЕРЕИМЕНУЕТСЯ ли это место на самом
деле, а не от того, насколько мы уверены в его связи.
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


def _project(prefix, arena=UNPROVEN):
    root = tempfile.mkdtemp(prefix=prefix)
    files = {"project.godot": "config_version=5\n",
             "src/player.gd": PLAYER,
             "src/typed.gd": TYPED,
             "src/arena.gd": arena}
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
class ChecklistHonesty(unittest.TestCase):
    """Галочка стоит только там, где место действительно переименуется."""

    def _checklist(self, root, **extra):
        analysis = symbol_refactor.analyze_rename(root, _action(**extra))
        return {item["id"]: item
                for item in main._usage_checklist(analysis)}

    def _unproven_id(self, root):
        analysis = symbol_refactor.analyze_rename(root, _action())
        for place in analysis["usages"]:
            if place["confidence"] == "probable":
                return "%s:%s:%s" % (place["path"], place["line"],
                                     place["column"])
        self.fail("в анализе нет недоказанной ссылки")

    # --- B.1 strict: недоказанное место НЕ обещано ---
    def test_strict_does_not_promise_unproven_place(self):
        """С флагом снятым переименование вообще откажется, поэтому обещать
        пользователю «это место будет переименовано» нельзя."""
        root = _project("chk_strict_")
        self.addCleanup(shutil.rmtree, root, True)
        place = self._checklist(root, allow_unverified=False)
        unproven = self._unproven_id(root)
        self.assertIn(unproven, place)
        self.assertFalse(
            place[unproven]["checked"],
            "strict откажется целиком, место не должно быть отмечено")

    # --- B.2 allow_unverified: место ПЕРЕИМЕНУЕТСЯ, галочка стоит ---
    def test_allow_unverified_marks_unproven_as_checked(self):
        root = _project("chk_flag_")
        self.addCleanup(shutil.rmtree, root, True)
        place = self._checklist(root, allow_unverified=True)
        unproven = self._unproven_id(root)
        self.assertTrue(
            place[unproven]["checked"],
            "при allow_unverified=true место действительно переименуется")

    # --- B.3 probable: недоказанное место НЕ переименовывается ---
    def test_probable_does_not_promise_unproven_place(self):
        """probable разрешает запись, но недоказанные ссылки НЕ трогает —
        значит и обещать их переименование нельзя."""
        root = _project("chk_probable_")
        self.addCleanup(shutil.rmtree, root, True)
        place = self._checklist(root, mode="probable")
        unproven = self._unproven_id(root)
        self.assertFalse(
            place[unproven]["checked"],
            "probable оставляет недоказанное место как есть")

    # --- B.4 доказанные места отмечены ВСЕГДА ---
    def test_proven_places_stay_checked(self):
        for extra in ({"allow_unverified": True}, {"allow_unverified": False},
                      {"mode": "probable"}, {}):
            with self.subTest(**extra):
                root = _project("chk_proven_")
                try:
                    place = self._checklist(root, **extra)
                    proven = [item for item in place.values()
                              if item.get("confidence") == "proven"]
                    self.assertTrue(proven)
                    for item in proven:
                        self.assertTrue(
                            item["checked"],
                            "доказанное место обязано быть отмечено: %s" % extra)
                finally:
                    shutil.rmtree(root, True)

    # --- B.5 динамические ссылки не отмечаются никогда ---
    def test_dynamic_places_never_checked(self):
        root = _project("chk_dyn_")
        self.addCleanup(shutil.rmtree, root, True)
        for extra in ({"allow_unverified": True}, {"mode": "probable"}):
            with self.subTest(**extra):
                place = self._checklist(root, **extra)
                for item in place.values():
                    if item.get("confidence") == "dynamic":
                        self.assertFalse(item["checked"])

    # --- B.6 чистый проект: чеклист без сюрпризов ---
    def test_clean_project_all_proven_are_checked(self):
        root = _project("chk_clean_", arena=CLEAN)
        self.addCleanup(shutil.rmtree, root, True)
        place = self._checklist(root, allow_unverified=True)
        for item in place.values():
            self.assertEqual(item["confidence"], "proven")
            self.assertTrue(item["checked"])


if __name__ == "__main__":
    unittest.main()