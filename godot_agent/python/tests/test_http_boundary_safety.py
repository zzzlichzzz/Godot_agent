"""Real Flask requests: pre-parse limits/auth and reset/admission isolation."""
import io
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _bootstrap  # noqa: E402,F401
import main  # noqa: E402
import server_auth  # noqa: E402
import server_state as state  # noqa: E402


class HttpBoundarySafetyTests(unittest.TestCase):
    def setUp(self):
        self.previous = dict(state.STATE)
        self.auth = dict(server_auth._bound)
        self.storage = tempfile.TemporaryDirectory(prefix="agent_http_boundary_")
        self.token = "a" * 32
        with open(server_auth.token_path(self.storage.name), "w", encoding="utf-8") as handle:
            handle.write(self.token)
        server_auth.reset()
        self.assertTrue(server_auth.check("/init", self.token, self.storage.name)[0])
        state.clear_request_activity()
        state.STATE["progress"] = {"active": False}
        self.client = main.app.test_client()
        self.headers = {server_auth.HEADER: self.token}

    def tearDown(self):
        state.clear_request_activity()
        state.STATE.clear()
        state.STATE.update(self.previous)
        server_auth._bound.update(self.auth)
        self.storage.cleanup()

    def test_bad_header_is_rejected_without_json_parse_or_admission(self):
        with patch.object(main.app.request_class, "get_json", side_effect=AssertionError("JSON parsed")), \
                patch.object(state, "try_begin_turn_exchange", side_effect=AssertionError("admitted")):
            response = self.client.post("/chat/runtime_inspect/result", data=b"{bad",
                                        content_type="application/json",
                                        headers={server_auth.HEADER: "wrong"})
        self.assertEqual(response.status_code, 403)
        response = self.client.post("/init", json={},
                                    headers={server_auth.HEADER: "\u00e9"})
        self.assertEqual(response.status_code, 403)

    def test_length_limit_precedes_parse_and_state_mutation(self):
        for path, size in (("/init", 128 * 1024),
                           ("/chat/runtime_inspect/result", main.runtime_debug.MAX_HTTP_BODY_BYTES),
                           ("/chat/runtime_check/result", main.runtime_checks.MAX_HTTP_BODY_BYTES)):
            with self.subTest(path=path), patch.object(
                    main.app.request_class, "get_json", side_effect=AssertionError("JSON parsed")):
                response = self.client.post(path, data=b" " * (size + 1),
                                            content_type="application/json", headers=self.headers)
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.get_json()["code"], "request_too_large")

    def test_stream_without_content_length_is_bounded(self):
        # Werkzeug enforces the same bound while reading a terminated WSGI
        # stream, rather than trusting a missing Content-Length header.
        size = main.runtime_debug.MAX_HTTP_BODY_BYTES
        payload = b'{"snapshot":"' + b"x" * size + b'"}'
        response = self.client.open(
            "/chat/runtime_inspect/result", method="POST", headers=self.headers,
            content_type="application/json", environ_overrides={
                "wsgi.input": io.BytesIO(payload), "wsgi.input_terminated": True,
                "CONTENT_LENGTH": None})
        self.assertEqual(response.status_code, 413)

    def test_non_object_json_returns_400(self):
        for payload in ([], ["user_data_dir"], "text", 12):
            response = self.client.post("/init", json=payload, headers=self.headers)
            self.assertEqual(response.status_code, 400)

    def test_busy_requests_cannot_change_project_or_pending_state(self):
        ready, finish = threading.Event(), threading.Event()

        def active_turn():
            assert state.try_begin_turn_exchange()
            ready.set()
            finish.wait(10)
            state.clear_request_activity()

        original_root = "original-project"
        pending = {"state": "executing", "entry_id": "reserved"}
        state.STATE.update(project_root=original_root, pending_scene_action=pending)
        worker = threading.Thread(target=active_turn)
        worker.start()
        self.assertTrue(ready.wait(5))
        try:
            for route in ("/init", "/chats/list", "/chats/new", "/chats/open",
                          "/chats/rename", "/chats/delete", "/chats/model"):
                response = self.client.post(route, json={"project_root": "other-project",
                    "user_data_dir": self.storage.name, "id": "other"}, headers=self.headers)
                self.assertEqual(response.status_code, 409, (route, response.get_json()))
                self.assertEqual(state.STATE["project_root"], original_root)
                self.assertIs(state.STATE["pending_scene_action"], pending)
        finally:
            finish.set()
            worker.join(5)
        self.assertFalse(state.exchange_active())

    def test_idle_init_does_not_erase_editor_reservation(self):
        pending = {"state": "executing", "entry_id": "reserved"}
        state.STATE["pending_project_settings_action"] = pending
        response = self.client.post("/init", json={"project_root": "other-project"},
                                    headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["code"], "pending_operation")
        self.assertIs(state.STATE["pending_project_settings_action"], pending)
        self.assertTrue(state.try_begin_navigation())

    def test_live_input_excludes_send_navigation_and_other_input(self):
        entered, release = threading.Event(), threading.Event()
        responses = []

        def mirror(*_args):
            entered.set()
            if not release.wait(5):
                raise AssertionError("test did not release live input")
            return {"ok": True, "applied": True}

        def write_input():
            with main.app.test_client() as client:
                responses.append(client.post("/chat/live_input", json={"seq": 1, "text": "draft"},
                                             headers=self.headers))

        with patch.object(main._live_mirror, "apply", side_effect=mirror) as apply:
            worker = threading.Thread(target=write_input)
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                for route in ("/chat", "/chats/new"):
                    response = self.client.post(route, json={"prompt": "must not send"}, headers=self.headers)
                    self.assertEqual(response.status_code, 409)
                response = self.client.post("/chat/live_input", json={"seq": 2, "text": "other"}, headers=self.headers)
                self.assertEqual(response.get_json()["reason"], "busy")
                apply.assert_called_once()
            finally:
                release.set()
                worker.join(5)
        self.assertEqual(responses[0].status_code, 200)
        self.assertTrue(state.try_begin_turn_exchange())


if __name__ == "__main__":
    unittest.main()
