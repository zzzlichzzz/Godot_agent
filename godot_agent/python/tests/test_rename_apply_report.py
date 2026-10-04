# -*- coding: utf-8 -*-
"""Синтетика: после переименования модель должна знать, ЧТО именно изменилось.

Замер (Этап C). После применения модель получает ответ:

    [Система]: Символ Player безопасно переименован в Avatar (3 файл(ов), 2 ссылок).

Из этого она не может понять ни где искать, ни что именно было непроверенным.
Требование заказчика: писать нейросети, какие файлы были изменены автоматически,
чтобы она могла позже сама проверить нужное место.

Значит ответ обязан содержать:
  * список изменённых файлов (иначе модель не знает, куда смотреть);
  * число мест, переименованных БЕЗ доказательства, и их координаты
    (иначе она считает, что все ссылки проверены).
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
from server_state import STATE


def _history_storage():
    """Текущее переопределение хранилища истории (или None, если не задано)."""
    import history_manager
    return getattr(history_manager, "_STORAGE_OVERRIDE", None)


def set_storage(store):
    """Тот же приём, что в test_rename_usages_checklist: правим приватный
    атрибут напрямую, потому что публичного чтения состояния хранилища нет."""
    import history_manager
    history_manager._STORAGE_OVERRIDE = store


PLAYER = "class_name Player\nextends Node2D\n"
TYPED = "extends Node\n\nvar unit: Player\n"
UNPROVEN = "extends Node\n\nfunc fire(target):\n\ttarget.spawn(Player)\n"
CLEAN = "extends Node\n"


class ApplyReport(unittest.TestCase):
    """Ответ после применения перечисляет файлы и непроверенные места."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="apply_report_")
        self.store = tempfile.mkdtemp(prefix="apply_report_store_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(shutil.rmtree, self.store, True)
        self.previous_store = _history_storage()
        self.addCleanup(self._restore_store)
        set_storage(self.store)
        for rel, text in (("project.godot", "config_version=5\n"),
                          ("src/player.gd", PLAYER),
                          ("src/typed.gd", TYPED),
                          ("src/arena.gd", UNPROVEN)):
            path = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        build_index(self.root)
        for key in ("pending_action", "pending_refactor", "pending_validation",
                    "pending_transaction", "pending_file_refactor",
                    "pending_node_refactor", "pending_plan"):
            STATE.pop(key, None)
        STATE.update({"project_root": self.root, "pending_action": None,
                      "pending_refactor": None, "pending_validation": None,
                      "addon_intent": False, "addon_dir": None,
                      "godot_executable": ""})
        # Панель и сеть заглушиваем: тест проверяет ответ сервера.
        for name in ("_remember", "_sync_chat_after_reply", "_refresh_fs_snapshot",
                     "_remember_file", "_touch_file_read"):
            setattr(main, name, lambda *_a, **_k: None)
        setattr(main, "_current_chat_info", lambda: ("c", "t"))

    def _restore_store(self):
        import history_manager
        if self.previous_store is not None:
            history_manager.set_storage_dir(self.previous_store)
        else:
            history_manager._STORAGE_OVERRIDE = None

    def _read(self, rel):
        with open(os.path.join(self.root, *rel.split("/")),
                  "r", encoding="utf-8") as handle:
            return handle.read()

    def _action(self, **extra):
        action = {"action": "rename_symbol", "kind": "class_name",
                  "declaration": "res://src/player.gd:1",
                  "old_name": "Player", "new_name": "Avatar"}
        action.update(extra)
        return action

    def _confirm(self, **extra):
        """Готовит план через РЕАЛЬНЫЙ путь подготовки и подтверждает его.

        План собирается вручную нельзя: confirm_action проверяет policy-метку
        (_stamp_policy) и отвечает stale_policy, если её нет. Поэтому идём
        тем же путём, что реальный запрос: _package_model_reply -> confirm.
        """
        payload, status = self._package(self._action(**extra))
        self.assertEqual(status, 200, payload)
        self.assertIsNotNone(payload.get("pending_action"), payload)
        with main.app.test_request_context(
                "/chat/confirm_action", method="POST",
                json={"approved": True}):
            response = main.confirm_action()
        if isinstance(response, tuple):
            return response[0].get_json(), response[1]
        return response.get_json(), response.status_code

    def _package(self, action, allow_followup=False):
        """Прогоняет подготовку действия тем же путём, что и живой запрос."""
        setattr(main, "_reply_with_self_heal",
                lambda followup, root: (followup, None))
        with main.app.test_request_context("/chat", method="POST", json={}):
            response = main._package_model_reply(
                "Переименовываю.", action, self.root,
                allow_followup=allow_followup)
        if isinstance(response, tuple):
            return response[0].get_json(), response[1]
        return response.get_json(), response.status_code
# __APPEND__
# --- C.1 ответ перечисляет ИЗМЕНЁННЫЕ ФАЙЛЫ ---
    def test_answer_lists_changed_files(self):
        payload, status = self._confirm(allow_unverified=True)
        self.assertEqual(status, 200)
        answer = payload["answer"]
        for rel in ("src/player.gd", "src/typed.gd", "src/arena.gd"):
            self.assertIn(rel, answer, answer)

    def test_payload_exposes_changed_paths_structurally(self):
        """Структурное поле надёжнее текста: модель читает json."""
        payload, _status = self._confirm(allow_unverified=True)
        self.assertTrue(payload.get("changed_paths"))
        for item in payload["changed_paths"]:
            self.assertIn(item, payload["answer"], payload["answer"])

    # --- C.2 ответ называет места, переименованные БЕЗ доказательства ---
    def test_answer_names_unproven_places(self):
        payload, _status = self._confirm(allow_unverified=True)
        answer = payload["answer"]
        self.assertRegex(answer.lower(), r"не доказ|без доказательств|unproven")
        self.assertIn("arena.gd", answer)

    def test_payload_exposes_unproven_places(self):
        payload, _status = self._confirm(allow_unverified=True)
        notes = payload.get("unverified_references")
        self.assertTrue(notes, list(payload.keys()))
        self.assertTrue(any("arena.gd" in str(n) for n in notes), notes)

    # --- C.3 честный случай: проверено всё -> ложной тревоги нет ---
    def test_clean_case_has_no_unproven_wording(self):
        path = os.path.join(self.root, "src", "arena.gd")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(CLEAN)
        build_index(self.root)
        payload, _status = self._confirm(allow_unverified=True)
        answer = payload["answer"]
        self.assertNotRegex(
            answer.lower(), r"не доказ|без доказательств|unproven")
        self.assertEqual(payload.get("unverified_references") or [], [])
        # Файлы перечислены даже когда всё доказано — это нужно модели для
        # последующей проверки, а не только в случае проблемы.
        self.assertIn("typed.gd", answer)

    # --- C.4 сам факт переименования не ломается ---
    def test_rename_still_applied(self):
        self._confirm(allow_unverified=True)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        self.assertIn("var unit: Avatar", self._read("src/typed.gd"))
        self.assertIn("target.spawn(Avatar)", self._read("src/arena.gd"))


if __name__ == "__main__":
    unittest.main()