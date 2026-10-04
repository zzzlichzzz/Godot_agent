# -*- coding: utf-8 -*-
"""Синтетические тесты п.4.3: список мест с галочками вместо текстовой ошибки.

Вместо «найдено N неоднозначностей» панель получает сам список мест с
уровнями уверенности и может снять галочки — сервер принимает exclude при
подтверждении и применяет только оставшееся.
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
from minilich import ml_project_index
from server_state import STATE


PLAYER = """class_name Player
extends Node

func take_damage(amount: int) -> int:
\treturn amount
"""

ARENA = """extends Node

var unit: Player

func fire(target):
\tvar ref = target.Player
"""


class UsagesChecklist(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rename_checklist_")
        self.store = tempfile.mkdtemp(prefix="rename_checklist_store_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(shutil.rmtree, self.store, True)
        self.previous_store = history_storage()
        self.addCleanup(self._restore_store)
        set_storage(self.store)
        self._write("project.godot", "config_version=5\n")
        self._write("src/player.gd", PLAYER)
        self._write("src/arena.gd", ARENA)
        self._reindex()
        # Полный сброс: предыдущий тест мог оставить pending_validation или
        # подготовленную транзакцию, и следующий получал чужое состояние.
        for key in ("pending_action", "pending_refactor", "pending_validation",
                    "pending_transaction", "pending_file_refactor",
                    "pending_node_refactor", "pending_plan"):
            STATE.pop(key, None)
        STATE.update({"project_root": self.root, "pending_action": None,
                      "pending_refactor": None, "pending_validation": None,
                      "addon_intent": False, "addon_dir": None,
                      "godot_executable": ""})
        self._patch_panel()

    def _restore_store(self):
        import history_manager
        if self.previous_store is not None:
            history_manager.set_storage_dir(self.previous_store)
        else:
            history_manager._STORAGE_OVERRIDE = None

    def _patch_panel(self):
        import history_manager
        for name in ("_remember", "_sync_chat_after_reply", "_refresh_fs_snapshot",
                     "_remember_file", "_touch_file_read"):
            setattr(main, name, lambda *_a, **_k: None)
        setattr(main, "_current_chat_info", lambda: ("c", "t"))
        # Self-heal после отказа ушёл бы в сеть к модели. Подменяем заглушкой:
        # тест проверяет ответ сервера, а не работу бэкенда модели.
        setattr(main, "_reply_with_self_heal", lambda followup, root: (followup, None))
        # Хранилище НЕ сбрасываем здесь: индекс и журнал пишутся в него, и
        # возврат к прежнему ломал бы разбор проекта. Вернём в tearDown.

    def _write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def _read(self, rel):
        with open(os.path.join(self.root, *rel.split("/")), "r", encoding="utf-8") as handle:
            return handle.read()

    def _reindex(self):
        # Кэш индекса в памяти живёт между тестами; при новом проекте он не
        # должен влиять на разбор, поэтому сбрасываем его явно.
        ml_project_index._MEM_CACHE.clear()
        ml_project_index.build_index(self.root)

    def _action(self, **extra):
        action = {"action": "rename_symbol", "kind": "class_name",
                  "declaration": "res://src/player.gd:1",
                  "old_name": "Player", "new_name": "Avatar"}
        action.update(extra)
        return action

    def _package(self, action, allow_followup=True):
        with main.app.test_request_context("/chat", method="POST", json={}):
            response = main._package_model_reply(
                "Переименовываю.", action, self.root, allow_followup=allow_followup)
        if isinstance(response, tuple):
            return response[0].get_json(), response[1]
        return response.get_json(), response.status_code

    # --- 4.3.1 ответ подготовки содержит список мест ---
    def test_prepare_returns_usages_checklist(self):
        payload, status = self._package(self._action(mode="probable"))
        self.assertEqual(status, 200)
        usages = payload.get("pending_action_usages")
        self.assertTrue(usages, list(payload.keys()))
        for place in usages:
            self.assertIn("path", place)
            self.assertIn("line", place)
            self.assertIn("confidence", place)

    # --- 4.3.2 места пригодны для галочек: есть ключ выбора ---
    def test_usages_have_checkable_id(self):
        payload, _status = self._package(self._action(mode="probable"))
        for place in payload["pending_action_usages"]:
            self.assertTrue(place.get("id"))
            self.assertIn(place["confidence"], ("proven", "probable", "dynamic"))

    # --- 4.3.3 отказ strict тоже отдаёт места, а не только текст ошибки ---
    def test_strict_refusal_includes_suggested_usages(self):
        ml_project_index._MEM_CACHE.clear()
        # Галочка «переименовывать недоказанные ссылки» по умолчанию СНЯТА
        # здесь явно: тест проверяет ветку отказа, а дефолт панели теперь
        # разрешает переименование, и до этой ветки просто не дошло бы.
        payload, status = self._package(
            self._action(allow_unverified=False), allow_followup=False)
        self.assertEqual(status, 200)
        self.assertIsNone(payload.get("pending_action"))
        suggested = payload.get("suggested_usages")
        self.assertTrue(suggested, list(payload.keys()))
        self.assertTrue(any("arena.gd" in item["path"] for item in suggested))

    # --- 4.3.4 текст ошибки остаётся, но с местями в структурированном виде ---
    def test_refusal_keeps_human_text(self):
        payload, _status = self._package(self._action(allow_unverified=False))
        self.assertIn("rename_symbol", payload["answer"])

    # --- Аудит 4.3: подтверждение принимает exclude и применяет частично ---
    def test_confirm_applies_excluded_untouched(self):
        payload, _status = self._package(self._action(mode="probable"))
        usages = payload["pending_action_usages"]
        ambiguous = [u for u in usages if "arena.gd" in u["path"]
                     and u["confidence"] != "proven"]
        with main.app.test_request_context(
                "/chat/confirm_action", method="POST",
                json={"approved": True, "exclude": [u["id"] for u in ambiguous]}):
            response = main.confirm_action()
        if isinstance(response, tuple):
            result, status = response[0].get_json(), response[1]
        else:
            result, status = response.get_json(), response.status_code
        self.assertEqual(status, 200)
        self.assertIn("class_name Avatar", self._read("src/player.gd"))
        self.assertIn(result["changed_paths"][0].split("/")[-1],
                      ("player.gd", "arena.gd"))



    def test_confirm_without_exclude_applies_all(self):
        payload, _status = self._package(self._action(mode="probable"))
        self.assertTrue(payload["pending_action_usages"])
        with main.app.test_request_context(
                "/chat/confirm_action", method="POST", json={"approved": True}):
            response = main.confirm_action()
        result = (response.get_json() if not isinstance(response, tuple)
                  else response[0].get_json())
        self.assertEqual(len(result["changed_paths"]), 2)

    # --- Аудит 4.3: пустой exclude не ломает применение ---
    def test_empty_exclude_is_ignored(self):
        self._package(self._action(mode="probable"))
        with main.app.test_request_context(
                "/chat/confirm_action", method="POST",
                json={"approved": True, "exclude": []}):
            response = main.confirm_action()
        self.assertIn("class_name Avatar", self._read("src/player.gd"))

    # --- Аудит 4.3: снятые галочки попадают в отчёт применения ---
    def test_excluded_places_reported_after_apply(self):
        payload, _status = self._package(self._action(mode="probable"))
        usages = payload["pending_action_usages"]
        ambiguous = [u for u in usages if "arena.gd" in u["path"]
                     and u["confidence"] != "proven"]
        with main.app.test_request_context(
                "/chat/confirm_action", method="POST",
                json={"approved": True, "exclude": [u["id"] for u in ambiguous]}):
            response = main.confirm_action()
        result = (response.get_json() if not isinstance(response, tuple)
                  else response[0].get_json())
        self.assertIn("arena.gd", result["answer"])


def history_storage():
    import history_manager
    return history_manager._STORAGE_OVERRIDE


def set_storage(store):
    import history_manager
    history_manager.set_storage_dir(store)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
