# -*- coding: utf-8 -*-
"""Синтетика: check_action (MCP-судья) обязан РАСКРЫВАТЬ недоказанные ссылки.

Дыра, найденная замером на живом коде. `check_action` — локальный судья,
который спрашивает «это действие безопасно?». Он звал prepare_rename напрямую
и печатал одно evidence:

    Safe rename resolves 1 references in 2 files   -> score 97

При allow_unverified=true это ЗВУЧИТ как «всё доказано», хотя часть мест
переименована без доказательства, и судья об этом молчит. Замерено:
с флагом 97, без флага 13. Разница в 84 балла — и ни одного слова о том,
что безопасность частично не доказана.

MCP-путь остаётся рабочим: судья НЕ блокирует, потому что модели положено
уметь переименовывать автоматически. Лечится честным раскрытием, а не запретом.

Плюс требование заказчика: судья обязан перечислить ИЗМЕНЁННЫЕ ФАЙЛЫ, чтобы
модель знала, что именно меняется, и могла позже сама перепроверить нужное место.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

from answer_judge import judge_answer
from minilich.ml_project_index import build_index


PLAYER = "class_name Player\nextends Node2D\n\nfunc hit() -> void:\n\tpass\n"
TYPED = "extends Node\n\nvar unit: Player\n"
UNPROVEN = "extends Node\n\nfunc fire(target):\n\ttarget.spawn(Player)\n"
CLEAN = "extends Node\n"


def _answer(action):
    return ("Проверяю проект.\n```agent_action\n%s\n```\n===DONE==="
            % json.dumps(action, ensure_ascii=False))


def _make_project(prefix, arena=UNPROVEN):
    """Сборка проекта целиком: build_index тяжёлый, но детерминированный."""
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
# __APPEND__
class JudgeDisclosure(unittest.TestCase):
    """Судья раскрывает, сколько мест переименовано без доказательства."""

    def setUp(self):
        self.root = _make_project("judge_unverified_")
        self.addCleanup(shutil.rmtree, self.root, True)

    def _judge(self, **extra):
        action = {"action": "rename_symbol", "kind": "class_name",
                  "declaration": "res://src/player.gd:1",
                  "old_name": "Player", "new_name": "Avatar"}
        action.update(extra)
        return judge_answer(self.root, _answer(action))

    # --- A.1 судья НЕ блокирует: MCP должен уметь переименовывать сам ---
    def test_mcp_path_still_allowed_to_rename_unverified(self):
        """Требование заказчика: у MCP/модели остаётся право автоматически
        переименовать недоказанное. Значит блокировкой это лечить нельзя —
        судья обязан пропустить действие, но СКАЗАТЬ о риске."""
        result = self._judge(allow_unverified=True)
        self.assertTrue(result["acceptable"], result.get("blocking"))
        self.assertEqual(result["blocking"], [])

    # --- A.2 но судья ОБЯЗАН сказать, сколько мест без доказательства ---
    def test_judge_names_unverified_risk(self):
        result = self._judge(allow_unverified=True)
        joined = " ".join(str(item) for item in result.get("evidence") or [])
        self.assertRegex(
            joined.lower(), r"не доказ|unproven|без доказательств")

    def test_judge_reports_reason_and_location(self):
        """Причина обязана быть названа и место указано: иначе модель не может
        ни понять риск, ни потом перепроверить конкретное место."""
        result = self._judge(allow_unverified=True)
        joined = " ".join(str(item) for item in result.get("evidence") or [])
        self.assertIn("res://src/arena.gd", joined)

    def test_judge_lists_changed_files(self):
        """Модель должна знать, какие файлы изменятся, иначе она не сможет
        сама перепроверить нужное место позже."""
        result = self._judge(allow_unverified=True)
        joined = " ".join(str(item) for item in result.get("evidence") or [])
        for path in ("res://src/player.gd", "res://src/typed.gd",
                     "res://src/arena.gd"):
            self.assertIn(path, joined, joined)

    # --- A.3 честный случай: недоказанных нет -> риск НЕ выдумывается ---
    def test_clean_project_has_no_risk_wording(self):
        root = _make_project("judge_clean_", arena=CLEAN)
        self.addCleanup(shutil.rmtree, root, True)
        action = {"action": "rename_symbol", "kind": "class_name",
                  "declaration": "res://src/player.gd:1",
                  "old_name": "Player", "new_name": "Avatar",
                  "allow_unverified": True}
        result = judge_answer(root, _answer(action))
        joined = " ".join(str(item) for item in result.get("evidence") or [])
        self.assertNotRegex(
            joined.lower(), r"не доказ|unproven|без доказательств")

    def test_clean_project_keeps_files_listed(self):
        root = _make_project("judge_clean2_", arena=CLEAN)
        self.addCleanup(shutil.rmtree, root, True)
        action = {"action": "rename_symbol", "kind": "class_name",
                  "declaration": "res://src/player.gd:1",
                  "old_name": "Player", "new_name": "Avatar",
                  "allow_unverified": True}
        result = judge_answer(root, _answer(action))
        joined = " ".join(str(item) for item in result.get("evidence") or [])
        self.assertIn("res://src/typed.gd", joined)

    # --- A.4 без флага поведение прежнее: судья отказывает ---
    def test_without_flag_judge_still_blocks(self):
        result = self._judge()
        self.assertFalse(result["acceptable"])
        self.assertTrue(result["blocking"])

    def test_bad_flag_type_is_refused(self):
        """Мусорное значение не должно ни проходить, ни тихо включать риск."""
        result = self._judge(allow_unverified="false")
        self.assertFalse(result["acceptable"])
        self.assertTrue(result["blocking"])

    # --- A.5 риск виден и в плоских warnings ---
    def test_risk_is_visible_in_warnings(self):
        result = self._judge(allow_unverified=True)
        warnings = result.get("warnings") or []
        # warnings — список словарей, поэтому берём именно текст сообщения.
        joined = " ".join(str(item.get("message", "")) for item in warnings)
        self.assertRegex(joined.lower(), r"could not be proven|не доказ")


if __name__ == "__main__":
    unittest.main()