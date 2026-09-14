"""Runtime result retries through auth, admission, and actual Flask dispatch."""
import copy
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import main
import runtime_checks
import runtime_debug
import server_auth
import server_state


class RuntimeResultHTTPTests(unittest.TestCase):
    def setUp(self):
        self.saved_state = dict(main.STATE)
        self.saved_auth = dict(server_auth._bound)
        self.saved_cache = dict(main._RUNTIME_RESULTS)
        self.addCleanup(self.restore)
        self.directory = tempfile.TemporaryDirectory(prefix="runtime_result_http_")
        self.addCleanup(self.directory.cleanup)
        self.root = self.directory.name
        self.token = "a" * 48
        with open(server_auth.token_path(self.root), "w", encoding="ascii") as handle:
            handle.write(self.token)
        server_auth.reset()
        self.assertTrue(server_auth.check("/chat/runtime_check/result", self.token, self.root)[0])
        main.STATE.update(project_root=self.root, user_data_dir=self.root,
                          current_chat_id="result-chat", runtime_turn_id=7,
                          pending_runtime_check=None, pending_runtime_request=None)
        main._RUNTIME_RESULTS.clear()
        self.followup = self.enter_patch(patch.object(main, "_reply_once",
                                                     return_value=("Analyzed once", None)))
        self.package_model_reply = main._package_model_reply
        self.enter_patch(patch.object(main, "_package_model_reply",
                                      side_effect=lambda text, action, root, **kwargs: main.jsonify({"answer": text})))

    def enter_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def restore(self):
        main.STATE.clear()
        main.STATE.update(self.saved_state)
        server_auth._bound.update(self.saved_auth)
        main._RUNTIME_RESULTS.clear()
        main._RUNTIME_RESULTS.update(self.saved_cache)

    def prepare(self, kind="check", passed=False):
        if kind == "check":
            action = {"scene": "res://main.tscn", "timeout_ms": 3000,
                      "steps": [{"op": "assert_node", "index": 0, "exists": True}]}
            pending = runtime_checks.create_request(action, "result-chat", 7, self.root)
            pending.update(state="bound", session_id=8, run_id="run-8")
            body = dict(runtime_checks.public_request(pending), session_id=8, run_id="run-8",
                        status="ok", result={"protocol": 1, "scene": action["scene"],
                        "assertions": [{"index": 0, "op": "assert_node", "actual": passed}]})
            key = "pending_runtime_check"
        else:
            status = {"enabled": True, "protocol": 1, "sessions": [{
                "session_id": 8, "run_id": "run-8", "active": True,
                "breaked": False, "debuggable": True, "bridge_ready": True}]}
            pending = runtime_debug.create_request(
                {"action": "inspect_runtime", "sections": ["tree"]}, status, "result-chat", 7)
            pending["project_root"] = self.root
            body = dict(runtime_debug.public_request(pending), status="ok",
                        snapshot={"protocol": 1, "tree": {"nodes": []}})
            key = "pending_runtime_request"
        main.STATE[key] = pending
        return "/chat/runtime_%s/result" % kind, body, key

    def post(self, path, body):
        with main.app.test_client() as client:
            return client.post(path, json=body, headers={server_auth.HEADER: self.token})

    def test_concurrent_duplicate_is_retryable_and_followup_runs_once(self):
        for kind in ("check", "inspect"):
            with self.subTest(kind=kind):
                path, body, key = self.prepare(kind)
                entered, finish = threading.Event(), threading.Event()
                responses = []
                self.followup.reset_mock()

                def slow_followup(*_args):
                    entered.set()
                    if not finish.wait(5):
                        raise RuntimeError("test did not release model response")
                    return "Analyzed once", None

                self.followup.side_effect = slow_followup
                worker = threading.Thread(target=lambda: responses.append(self.post(path, body)), daemon=True)
                worker.start()
                try:
                    self.assertTrue(entered.wait(3))
                    duplicate = self.post(path, body)
                    self.assertEqual(duplicate.status_code, 503)
                    self.assertEqual(duplicate.get_json()["code"], "busy")
                    self.assertIs(duplicate.get_json()["retryable"], True)
                    self.assertEqual(duplicate.headers["Retry-After"], "1")
                    self.assertIsNone(main.STATE[key])
                    # The model exchange must not hold the runtime lock.
                    acquired = server_state._runtime_request_lock.acquire(timeout=0.2)
                    if acquired:
                        server_state._runtime_request_lock.release()
                    self.assertTrue(acquired)
                    self.assertFalse(server_state.try_begin_navigation())
                    with main.app.test_client() as client:
                        denied = client.post(path, data="{", content_type="application/json")
                        self.assertEqual(denied.status_code, 403)
                        large = client.post(path, data=" " * (runtime_checks.MAX_HTTP_BODY_BYTES + 1),
                                            content_type="application/json",
                                            headers={server_auth.HEADER: self.token})
                        self.assertEqual(large.status_code, 413)
                finally:
                    finish.set()
                    worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(responses[0].status_code, 200)
                replay = self.post(path, body)
                self.assertEqual(replay.status_code, 200)
                self.assertEqual(replay.get_json(), responses[0].get_json())
                self.followup.assert_called_once()
                self.followup.side_effect = None

    def test_cached_result_is_bound_to_context_and_session(self):
        for kind in ("check", "inspect"):
            for field, value in (("current_chat_id", "other-chat"), ("runtime_turn_id", 8),
                                 ("project_root", self.root + "-other"), ("user_data_dir", self.root + "-other")):
                with self.subTest(kind=kind, field=field):
                    path, body, _ = self.prepare(kind)
                    self.assertEqual(self.post(path, body).status_code, 200)
                    old = main.STATE[field]
                    main.STATE[field] = value
                    try:
                        self.assertEqual(self.post(path, body).status_code, 409)
                    finally:
                        main.STATE[field] = old
            path, body, _ = self.prepare(kind)
            original = self.post(path, body)
            for field, value in (("session_id", 9), ("run_id", "run-new"),
                                 ("chat_id", "other-chat"), ("turn_id", 8),
                                 ("project_root", self.root + "-other")):
                with self.subTest(kind=kind, field=field):
                    self.assertEqual(self.post(path, dict(body, **{field: value})).status_code, 409)
            self.assertEqual(self.post(path, body).get_json(), original.get_json())

    def test_unconsumed_result_rejects_changed_binding(self):
        for kind in ("check", "inspect"):
            for field, value in (("current_chat_id", "other-chat"), ("runtime_turn_id", 8),
                                 ("project_root", self.root + "-other")):
                path, body, key = self.prepare(kind)
                old = main.STATE[field]
                main.STATE[field] = value
                try:
                    self.assertEqual(self.post(path, body).status_code, 409)
                    self.assertIsNotNone(main.STATE[key])
                finally:
                    main.STATE[field] = old
            path, body, key = self.prepare(kind)
            for change in ({"session_id": 9}, {"run_id": "other-run"}, {"result_token": "b" * 48}):
                self.assertEqual(self.post(path, dict(body, **change)).status_code,
                                 403 if "result_token" in change else 409)
                self.assertIsNotNone(main.STATE[key])
        self.followup.assert_not_called()

    def test_reset_or_navigation_invalidates_replay_even_if_turn_number_is_reused(self):
        for kind in ("check", "inspect"):
            for invalidate in (server_state.reset_runtime_turn, server_state.clear_pending_confirmations):
                path, body, _ = self.prepare(kind)
                self.assertEqual(self.post(path, body).status_code, 200)
                invalidate()
                main.STATE["runtime_turn_id"] = 7
                self.assertEqual(self.post(path, body).status_code, 409)
        self.assertEqual(self.followup.call_count, 4)

    def test_ttl_does_not_extend_on_replay_and_pending_deadline_still_applies(self):
        for kind in ("check", "inspect"):
            path, body, _ = self.prepare(kind)
            with patch.object(main.time, "monotonic", return_value=100.0) as clock:
                original = self.post(path, body)
                self.assertEqual(original.status_code, 200)
                clock.return_value += main._RUNTIME_RESULT_TTL - 1
                self.assertEqual(self.post(path, body).get_json(), original.get_json())
                clock.return_value += 2
                self.assertEqual(self.post(path, body).status_code, 409)
                self.assertFalse(main._RUNTIME_RESULTS)
            path, body, key = self.prepare(kind)
            main.STATE[key]["deadline"] = time.time() - 1
            self.assertEqual(self.post(path, body).status_code, 410)
        self.assertEqual(self.followup.call_count, 2)

    def test_malformed_metadata_does_not_consume_or_leak_lock(self):
        changes = [{"session_id": value} for value in (None, "8", "bad", True, 8.0, [], {})]
        changes += [{"result_token": value} for value in (None, [], "\u00e9" * 48, "\ud800")]
        changes += [{"request_id": []}, {"run_id": []}, {"status": {}}]
        for kind in ("check", "inspect"):
            path, body, key = self.prepare(kind)
            pending = main.STATE[key]
            for change in changes:
                with self.subTest(kind=kind, change=change):
                    response = self.post(path, dict(body, **change))
                    self.assertEqual(response.status_code, 400)
                    self.assertIs(main.STATE[key], pending)
            with main.app.test_client() as client:
                response = client.post(path, json=[], headers={server_auth.HEADER: self.token})
                self.assertEqual(response.status_code, 400)
            # A different HTTP worker can still claim and complete the result.
            responses = []
            worker = threading.Thread(target=lambda: responses.append(self.post(path, body)), daemon=True)
            worker.start()
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(responses[0].status_code, 200)
        self.assertEqual(self.followup.call_count, 2)

    def test_terminal_validation_error_and_prebind_failure_are_replayable(self):
        for kind in ("check", "inspect"):
            path, body, _ = self.prepare(kind)
            body["result" if kind == "check" else "snapshot"] = None
            first = self.post(path, body)
            self.assertEqual(first.status_code, 400)
            replay = self.post(path, body)
            self.assertEqual(replay.status_code, 400)
            self.assertEqual(replay.get_json(), first.get_json())
        path, body, key = self.prepare()
        main.STATE[key].update(state="awaiting_bind", session_id=None, run_id="")
        body.update(status="launch_timeout", session_id=-1, run_id="")
        first = self.post(path, body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.post(path, body).get_json(), first.get_json())
        self.assertEqual(self.post(path, dict(body, session_id=8, run_id="run-8")).status_code, 409)
        self.followup.assert_not_called()

    def test_cache_size_is_bounded_and_pass_never_calls_model(self):
        first = None
        for _ in range(main._RUNTIME_RESULT_LIMIT + 1):
            path, body, _ = self.prepare(passed=True)
            if first is None:
                first = path, copy.deepcopy(body)
            response = self.post(path, body)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["passed"])
            self.assertLessEqual(len(main._RUNTIME_RESULTS), main._RUNTIME_RESULT_LIMIT)
        self.assertEqual(self.post(*first).status_code, 409)
        self.followup.assert_not_called()

    def test_packaging_cannot_start_another_model_request(self):
        actions = [
            {"action": "parse_error", "raw": "broken JSON"},
            {"action": "transaction", "operations": []},
            {"action": "edit_scene", "scene": "res://missing.tscn", "operations": []},
            {"action": "edit_project_settings", "operations": []},
            {"action": "edit_resource", "resource": "res://missing.tres", "operations": []},
            {"action": "project_command", "command": {"type": "unknown"}},
            {"action": "project_command", "command": {"type": "atomic_files", "operations": [
                {"action": "patch_file", "path": "res://missing.gd", "search": "old", "replace": "new"}]}},
            {"action": "plan", "steps": []},
            {"action": "plan", "steps": [], "continues": True},
            {"action": "read_file", "path": "res://missing.gd"},
            {"action": "create_file", "path": "res://broken.gd", "content": "func broken(:\n"},
            {"action": "create_file", "path": "res://main.tscn", "content": "raw scene"},
        ]
        with patch.object(main, "_package_model_reply", self.package_model_reply), \
                patch.object(main, "_remember"), patch.object(main, "_sync_chat_after_reply"), \
                patch.object(main, "_reply_with_self_heal", side_effect=AssertionError("extra model request")) as heal:
            for kind in ("inspect", "check"):
                for action in actions:
                    with self.subTest(kind=kind, action=action["action"]):
                        path, body, _ = self.prepare(kind)
                        main.STATE["pending_action"] = None
                        self.followup.reset_mock()
                        self.followup.return_value = ("Analysis", copy.deepcopy(action))
                        response = self.post(path, body)
                        self.assertEqual(response.status_code, 200, response.get_json())
                        self.assertIsNone(response.get_json().get("pending_action"))
                        self.followup.assert_called_once()
                        heal.assert_not_called()
                        replay = self.post(path, body)
                        self.assertEqual(replay.get_json(), response.get_json())
                        self.followup.assert_called_once()

    def test_missing_runtime_returns_local_result_without_model(self):
        path, body, _ = self.prepare()
        response = self.post(path, dict(body, status="runtime_not_running"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["passed"])
        self.followup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
