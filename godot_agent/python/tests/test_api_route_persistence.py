"""Real Flask requests with disk faults at API chat commit boundaries."""
import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _bootstrap  # noqa: E402,F401
import _fake_selenium

_fake_selenium.install()

from flask import Flask
import api_history as H
import api_keys
import chat_routes as routes
import chat_store
import server_state as S


class ApiRoutePersistenceTests(unittest.TestCase):
    def setUp(self):
        storage = tempfile.TemporaryDirectory(prefix="api_route_persistence_")
        self.addCleanup(storage.cleanup)
        self.base = storage.name
        self.patch("os.environ", {"GODOT_AGENT_CONFIG_DIR": self.base}, dictionary=True)
        api_keys.set_base_url("custom", "http://127.0.0.1:1/v1")
        api_keys.set_model("custom", "old-model")
        api_keys.set_defaults("custom", "old-model")
        self.old = chat_store.create_chat(self.base, primed=True)
        self.cid = self.old["id"]
        chat_store.update_chat(self.base, self.cid, kind="api", provider="custom",
                               model="old-model", site_name="old site")
        chat_store.append_transcript(self.base, self.cid, "user", "keep transcript")
        self.assertTrue(H.append_exchange(self.base, self.cid, "keep question", "keep answer",
                                         usage={"prompt_tokens": 9, "completion_tokens": 4}))
        self.history_path = Path(H.history_path(self.base, self.cid))
        self.metadata_path = Path(self.base, "agent_chats.json")
        self.history_before = self.history_path.read_bytes()
        self.messages_before = H.load_messages(self.base, self.cid)
        self.metadata_before = self.metadata_path.read_bytes()
        self.config_before = Path(api_keys.config_path()).read_bytes()
        state = {"user_data_dir": self.base, "project_root": None,
                 "allow_addons": False, "allow_self_edit": False,
                 "current_chat_id": self.cid, "current_site_id": "old site",
                 "is_primed": True, "progress": {"active": False},
                 "stale_notes": {self.cid: "keep stale note"}}
        for key in ("pending_action", "pending_refactor", "pending_scene_action",
                    "pending_project_settings_action", "pending_resource_action",
                    "pending_validation", "pending_transaction", "pending_runtime_request",
                    "pending_runtime_check", "pending_batch", "pending_plan",
                    "plan_parts", "content_parts"):
            state[key] = {"chat": self.cid, "marker": key}
        self.patch("server_state.STATE", state)
        self.state_before = copy.deepcopy(state)
        self.primed = self.patch("server_state._save_primed")
        self.app = Flask(__name__)
        self.app.testing = True
        self.app.register_blueprint(routes.chats_bp)
        # Match production lifecycle. Do not manually release route admission
        # in setUp/tearDown: every real request must release it through teardown.
        self.app.teardown_request(S.clear_turn_chat)
        self.app.teardown_request(S.clear_request_activity)
        self.client = self.app.test_client()
        self.transports = [self.patch(name, side_effect=AssertionError("provider request"))
                           for name in ("openai_compat.stream_chat", "openai_compat.complete_chat",
                                        "anthropic_compat.stream_chat", "anthropic_compat.complete_chat")]

    def patch(self, target, value=unittest.mock.DEFAULT, dictionary=False, **kwargs):
        mock = patch.dict(target, value) if dictionary else patch(target, value, **kwargs)
        result = mock.start()
        self.addCleanup(mock.stop)
        return result

    def tearDown(self):
        self.assertFalse(S._activity["navigation"], "request teardown leaked admission")
        self.assertFalse(S._activity["exchange"])
        for transport in self.transports:
            transport.assert_not_called()

    def post(self, route, **body):
        response = self.client.post(route, json=body)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertFalse(S._activity["navigation"])
        return response.get_json()

    def create(self):
        return self.post("/chats/new", kind="api", provider="custom", model="new-model")

    def switch(self):
        return self.post("/chats/model", provider="custom", model="new-model")

    def assert_rejected(self, result, history=None):
        self.assertIs(result["ok"], False)
        self.assertTrue(result["error"])
        self.assertNotIn("current_id", result)
        self.assertNotIn("model", result)
        self.assertEqual(S.STATE, self.state_before)
        self.primed.assert_not_called()
        self.assertEqual(self.metadata_path.read_bytes(), self.metadata_before)
        self.assertEqual(self.history_path.read_bytes(), self.history_before if history is None else history)
        self.assertEqual(Path(api_keys.config_path()).read_bytes(), self.config_before)
        # A second real route can acquire admission after a rejected request.
        listed = self.post("/chats/list")
        self.assertEqual([c["id"] for c in listed["chats"]], [self.cid])

    def test_corrupt_history_rejects_switch_without_metadata_or_state_changes(self):
        self.history_path.write_bytes(b"{broken JSON")
        self.assert_rejected(self.switch(), history=b"{broken JSON")

    def test_append_save_false_rejects_switch(self):
        with patch.object(H, "_save", return_value=False):
            result = self.switch()
        self.assert_rejected(result)

    def test_clear_save_false_rejects_creation(self):
        with patch.object(H, "_save", return_value=False):
            result = self.create()
        self.assert_rejected(result)
        self.assertEqual(list(self.history_path.parent.glob("*.json")), [self.history_path])

    def test_clear_read_error_rejects_creation(self):
        with patch.object(H, "clear", side_effect=H.ApiHistoryError("read denied")):
            result = self.create()
        self.assert_rejected(result)

    def test_creation_never_clears_preexisting_history(self):
        other = "a" * 12
        path = Path(H.history_path(self.base, other))
        with patch.object(routes.uuid, "uuid4") as uid:
            uid.return_value.hex = other
            for data in (b"{corrupt", self.history_before):
                with self.subTest(data=data):
                    path.write_bytes(data)
                    with patch.object(H, "clear", wraps=H.clear) as clear:
                        result = self.create()
                    clear.assert_not_called()
                    self.assertEqual(path.read_bytes(), data)
                    self.assert_rejected(result)

    def test_creation_metadata_save_exception_or_false_leaves_no_visible_chat(self):
        for kwargs in ({"side_effect": OSError("metadata disk fault")}, {"return_value": False}):
            with self.subTest(kwargs=kwargs):
                with patch.object(chat_store, "_save", **kwargs):
                    result = self.create()
                self.assert_rejected(result)
                self.assertEqual(list(self.history_path.parent.glob("*.json")), [self.history_path])

    def test_creation_cleanup_failure_reports_unlisted_empty_file(self):
        with patch.object(chat_store, "_save", side_effect=OSError("metadata disk fault")):
            with patch.object(H, "delete", return_value=False):
                result = self.create()
        self.assert_rejected(result)
        orphan = [p for p in self.history_path.parent.glob("*.json") if p != self.history_path]
        self.assertEqual(len(orphan), 1)
        self.assertIn(str(orphan[0]), result["error"])
        self.assertEqual(H.load_messages(self.base, orphan[0].stem), [])

    def test_switch_metadata_failure_restores_history_even_after_cap_trimming(self):
        for kwargs in ({"side_effect": OSError("metadata disk fault")}, {"return_value": False}):
            with self.subTest(kwargs=kwargs):
                with patch.object(H, "MAX_MESSAGES", 2):
                    with patch.object(chat_store, "_save", **kwargs):
                        result = self.switch()
                self.assert_rejected(result)

    def test_switch_rollback_failure_is_explicit_and_does_not_claim_success(self):
        real_save = H._save
        calls = []

        def fail_restore(*args):
            calls.append(args)
            return real_save(*args) if len(calls) == 1 else False

        with patch.object(chat_store, "_save", side_effect=OSError("metadata disk fault")):
            with patch.object(H, "_save", side_effect=fail_restore):
                result = self.switch()
        self.assertIs(result["ok"], False)
        self.assertIn(str(self.history_path), result["error"])
        self.assertEqual(S.STATE, self.state_before)
        self.assertEqual(self.metadata_path.read_bytes(), self.metadata_before)
        self.assertEqual(Path(api_keys.config_path()).read_bytes(), self.config_before)
        self.assertEqual(H.load_messages(self.base, self.cid)[:2],
                         self.messages_before)
        self.assertEqual(len(H.load_messages(self.base, self.cid)), 3)
        self.assertIn("new-model", H.load_messages(self.base, self.cid)[-1]["content"])

    def test_successful_creation_publishes_only_complete_api_record(self):
        real_save = chat_store._save
        snapshots = []

        def save(base, chats):
            snapshots.append(copy.deepcopy(chats))
            if len(snapshots) == 1:
                self.assertEqual(S.STATE, self.state_before)
                self.assertEqual(H.load_messages(base, chats[-1]["id"]), [])
                self.assertTrue(Path(H.history_path(base, chats[-1]["id"])).exists())
            return real_save(base, chats)

        # Explicit model selection must work without writing preferences first.
        api_keys.set_model("custom", "")
        with patch.object(chat_store, "_save", side_effect=save):
            result = self.create()
        self.assertIs(result["ok"], True)
        self.assertFalse(result["warning"])
        self.assertNotEqual(result["current_id"], self.cid)
        for snapshot in snapshots:
            self.assertEqual(snapshot[-1]["kind"], "api")
            self.assertEqual(snapshot[-1]["model"], "new-model")
        self.assertEqual(S.STATE["current_chat_id"], result["current_id"])
        self.assertIsNone(S.STATE["pending_action"])
        self.assertFalse(S.STATE["is_primed"])
        self.assertEqual(self.history_path.read_bytes(), self.history_before)
        self.assertEqual(api_keys.get_model("custom"), "new-model")

    def test_switch_transcript_failure_returns_visible_warning_after_commit(self):
        real_save = chat_store._save
        calls = []

        def save(base, chats):
            calls.append(chats)
            return real_save(base, chats) if len(calls) == 1 else False

        with patch.object(chat_store, "_save", side_effect=save):
            result = self.switch()
        self.assertIs(result["ok"], True)
        self.assertNotIn("error", result)
        self.assertTrue(result["warning"])
        self.assertIn(result["warning"], result["site"])
        self.assertEqual(result["model"], "new-model")
        rec = chat_store.find_chat(self.base, self.cid)
        self.assertEqual(rec["model"], "new-model")
        self.assertNotIn(result["warning"], rec["site_name"])
        self.assertEqual(len(rec["transcript"]), 1)
        self.assertEqual(len(H.load_messages(self.base, self.cid)), 3)
        self.assertEqual(S.STATE, self.state_before)
        # Repeating the same selection is a no-op, not another history append.
        again = self.switch()
        self.assertIs(again["ok"], False)
        self.assertEqual(len(H.load_messages(self.base, self.cid)), 3)

    def test_creation_transcript_failure_keeps_effective_new_chat(self):
        with patch.object(chat_store, "append_transcript", side_effect=OSError("transcript disk fault")):
            result = self.create()
        self.assertIs(result["ok"], True)
        self.assertNotIn("error", result)
        self.assertTrue(result["warning"])
        self.assertIn(result["warning"], result["site"])
        self.assertEqual(S.STATE["current_chat_id"], result["current_id"])
        self.assertIsNone(S.STATE["pending_action"])
        rec = chat_store.find_chat(self.base, result["current_id"])
        self.assertEqual(rec["kind"], "api")
        self.assertEqual(rec["model"], "new-model")
        self.assertEqual(rec["transcript"], [])
        self.assertEqual(self.history_path.read_bytes(), self.history_before)

    def test_postcommit_preference_and_list_failures_are_warnings(self):
        with patch.object(api_keys, "set_defaults", return_value=False):
            with patch.object(chat_store, "list_chats", side_effect=OSError("list read fault")):
                result = self.switch()
        self.assertIs(result["ok"], True)
        self.assertNotIn("error", result)
        self.assertTrue(result["warning"])
        self.assertIn(result["warning"], result["site"])
        self.assertEqual(chat_store.find_chat(self.base, self.cid)["model"], "new-model")


if __name__ == "__main__":
    unittest.main()
