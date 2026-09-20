"""Живой тест: /chats/list не возвращает ошибку «браузер занят» для своего проекта во время генерации."""
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _bootstrap  # noqa: E402,F401
import main  # noqa: E402
import server_auth  # noqa: E402
import server_state as state  # noqa: E402


class ChatsListLiveTests(unittest.TestCase):
    def setUp(self):
        self.previous = dict(state.STATE)
        self.auth = dict(server_auth._bound)
        self.storage = tempfile.TemporaryDirectory(prefix="agent_chats_list_live_")
        self.token = "b" * 32
        with open(server_auth.token_path(self.storage.name), "w", encoding="utf-8") as handle:
            handle.write(self.token)
        server_auth.reset()
        self.assertTrue(server_auth.check("/init", self.token, self.storage.name)[0])
        state.clear_request_activity()
        state.STATE["progress"] = {"active": False}
        state.STATE["project_root"] = self.storage.name
        self.client = main.app.test_client()
        self.headers = {server_auth.HEADER: self.token}

    def tearDown(self):
        state.clear_request_activity()
        state.STATE.clear()
        state.STATE.update(self.previous)
        server_auth._bound.update(self.auth)
        self.storage.cleanup()

    def test_chats_list_succeeds_during_active_turn_for_same_project(self):
        ready, finish = threading.Event(), threading.Event()

        def active_turn():
            assert state.try_begin_turn_exchange()
            ready.set()
            finish.wait(5)
            state.clear_request_activity()

        worker = threading.Thread(target=active_turn)
        worker.start()
        self.assertTrue(ready.wait(5))
        try:
            # Запрос списка чатов от того же проекта во время активного хода должен возвращать 200 OK
            response = self.client.post("/chats/list", json={
                "project_root": self.storage.name,
                "user_data_dir": self.storage.name
            }, headers=self.headers)
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertIn("chats", response.get_json())
        finally:
            finish.set()
            worker.join(5)

    def test_chats_list_blocks_cross_project_during_active_turn(self):
        ready, finish = threading.Event(), threading.Event()

        def active_turn():
            assert state.try_begin_turn_exchange()
            ready.set()
            finish.wait(5)
            state.clear_request_activity()

        worker = threading.Thread(target=active_turn)
        worker.start()
        self.assertTrue(ready.wait(5))
        try:
            # Запрос списка чатов от ДРУГОГО проекта во время активного хода должен блокироваться (409)
            response = self.client.post("/chats/list", json={
                "project_root": "other-project",
                "user_data_dir": self.storage.name
            }, headers=self.headers)
            self.assertEqual(response.status_code, 409)
        finally:
            finish.set()
            worker.join(5)

    def test_chats_list_succeeds_when_progress_active(self):
        # Симулируем активный стрим/парсер модели
        state._set_progress({"phase": "отправляю запрос", "active": True})
        response = self.client.post("/chats/list", json={
            "project_root": self.storage.name,
            "user_data_dir": self.storage.name
        }, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertIn("chats", response.get_json())
        state._clear_progress()


if __name__ == "__main__":
    unittest.main()
