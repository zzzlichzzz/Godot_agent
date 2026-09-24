# -*- coding: utf-8 -*-
"""Security-policy regressions for the main HTTP/write boundary."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import main
import server_state
import file_refactor
import symbol_refactor
from server_state import STATE


class AccessPolicyFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="access_policy_flow_")
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        for rel in (
                "project.godot", "src/game.gd", "addons/demo/demo.gd",
                "addons/Godot_agent/plugin.cfg",
                "addons/Godot_agent/godot_agent/agent_panel.gd"):
            path = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("extends Node\n" if rel.endswith(".gd") else "[plugin]\n")
        self.addon_dir = os.path.join(
            self.root, "addons", "Godot_agent", "godot_agent")
        self._saved = {key: STATE.get(key) for key in (
            "project_root", "addon_dir", "allow_addons", "allow_self_edit",
            "pending_action", "pending_batch", "pending_plan",
            "pending_transaction", "pending_refactor", "pending_file_refactor",
            "pending_node_refactor", "pending_scene_action",
            "pending_project_settings_action", "pending_resource_action",
            "pending_validation", "content_parts", "plan_parts")}
        server_state.clear_pending_confirmations()
        STATE.update(project_root=self.root, addon_dir=self.addon_dir,
                     allow_addons=False, allow_self_edit=False,
                     current_chat_id="policy-flow")

    def tearDown(self):
        server_state.clear_pending_confirmations()
        for key, value in self._saved.items():
            if value is None:
                STATE.pop(key, None)
            else:
                STATE[key] = value

    def test_text_addon_intent_does_not_override_explicit_permissions(self):
        # A stale/legacy diagnostic flag must not grant access.
        STATE["addon_intent"] = True
        result = main._apply_write_step(
            {"action": "create_file", "path": "res://addons/demo/new.gd",
             "content": "extends Node\n"}, self.root)
        self.assertFalse(result["ok"])
        self.assertFalse(os.path.exists(os.path.join(
            self.root, "addons", "demo", "new.gd")))

    def test_self_edit_pending_is_stale_after_permission_is_revoked(self):
        STATE["allow_self_edit"] = True
        action = {"action": "create_file",
                  "path": "res://addons/Godot_agent/godot_agent/generated.gd",
                  "content": "extends Node\n"}
        with main.app.test_request_context("/chat", method="POST", json={}):
            response = main._package_model_reply("Self edit", action, self.root,
                                                 allow_followup=False)
        body = response.get_json()
        self.assertIsNotNone(body.get("pending_action"), body)
        self.assertFalse(os.path.exists(os.path.join(self.addon_dir, "generated.gd")))

        STATE["allow_self_edit"] = False
        with main.app.test_request_context(
                "/chat/confirm_action", method="POST", json={"approved": True}):
            response, status = main.confirm_action()
        self.assertEqual(status, 409)
        self.assertEqual(response.get_json().get("code"), "stale_policy")
        self.assertFalse(os.path.exists(os.path.join(self.addon_dir, "generated.gd")))

    def test_external_addon_read_needs_addon_permission_not_prompt_word(self):
        STATE["addon_intent"] = True
        batch = main._start_read_batch(
            {"action": "read_file", "path": "res://addons/demo/demo.gd"},
            self.root)
        self.assertEqual(batch["files"][0]["status"], "blocked")

        STATE["allow_addons"] = True
        batch = main._start_read_batch(
            {"action": "read_file", "path": "res://addons/demo/demo.gd"},
            self.root)
        self.assertEqual(batch["files"][0]["status"], "pending")

    def test_external_refactor_skips_self_reference_until_self_edit(self):
        source = os.path.join(self.root, "addons", "demo", "demo.gd")
        agent_ref = os.path.join(self.addon_dir, "agent_panel.gd")
        with open(agent_ref, "a", encoding="utf-8", newline="\n") as handle:
            handle.write('\nconst DemoRef = preload("res://addons/demo/demo.gd")\n')

        external_only = file_refactor.prepare_file_rename(
            self.root, "res://addons/demo/demo.gd",
            "res://addons/demo/renamed.gd", allow_addons=True,
            allow_self_edit=False, addon_dir=self.addon_dir)
        self.assertNotIn("res://addons/Godot_agent/godot_agent/agent_panel.gd",
                         external_only["affected_paths"])

        with_self = file_refactor.prepare_file_rename(
            self.root, "res://addons/demo/demo.gd",
            "res://addons/demo/renamed.gd", allow_addons=True,
            allow_self_edit=True, addon_dir=self.addon_dir)
        self.assertIn("res://addons/Godot_agent/godot_agent/agent_panel.gd",
                      with_self["affected_paths"])

    def test_directory_relocation_rejects_entire_addons_tree(self):
        protected = os.path.join(self.addon_dir, "must_stay.gd")
        with open(protected, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("PROTECTED\n")
        STATE.update(allow_addons=True, allow_self_edit=False)
        context = {"project_root": self.root, "addon_dir": self.addon_dir,
                   "allow_addons": True, "allow_self_edit": False}
        with patch.object(server_state, "_discover_trusted_agent_dir",
                          return_value=self.addon_dir, create=True):
            response = main.app.test_client().post(
                "/project/refactor/file/preview", json=dict(
                    context, old_path="res://addons",
                    new_path="res://plugins", update_references=True))
        self.assertEqual(response.status_code, 400)
        self.assertIn("access policy", response.get_json()["error"].lower())
        self.assertTrue(os.path.isfile(protected))
        self.assertFalse(os.path.exists(os.path.join(self.root, "plugins")))
        self.assertIsNone(STATE.get("pending_file_refactor"))

    def test_direct_refactor_apply_cannot_use_tampered_prepared_state(self):
        source = os.path.join(self.addon_dir, "direct.gd")
        with open(source, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("PROTECTED\n")
        STATE.update(allow_addons=True, allow_self_edit=False)
        prepared = {
            "old_path": "res://addons/Godot_agent/godot_agent/direct.gd",
            "new_path": "res://addons/Godot_agent/godot_agent/moved.gd",
            "is_directory": False, "files": [{
                "action": "move_file",
                "path": "res://addons/Godot_agent/godot_agent/direct.gd",
                "dest": "res://addons/Godot_agent/godot_agent/moved.gd",
                "absolute": source,
                "dest_absolute": os.path.join(self.addon_dir, "moved.gd"),
                "before_hash": file_refactor._sha256(b"PROTECTED\n"),
                "before_bytes": b"PROTECTED\n", "after_bytes": b"PROTECTED\n",
                "diff": {}, "occurrences": 0,
            }],
        }
        with self.assertRaises(ValueError):
            file_refactor.apply_prepared_file_rename(
                self.root, prepared, allow_addons=True,
                allow_self_edit=False, addon_dir=self.addon_dir)
        self.assertTrue(os.path.isfile(source))
        self.assertFalse(os.path.exists(os.path.join(self.addon_dir, "moved.gd")))

    def test_init_discards_file_node_and_plan_previews(self):
        pending = {
            "pending_file_refactor": {"old_path": "res://src/game.gd"},
            "pending_node_refactor": {"scene": "res://scenes/main.tscn"},
            "pending_plan": {"chain_id": "old-chain", "steps": []},
            "content_parts": {"chunks": ["old"]},
            "plan_parts": {"parts": [{"steps": []}]},
        }
        STATE.update(pending)
        context = {"project_root": self.root, "addon_dir": self.addon_dir,
                   "allow_addons": False, "allow_self_edit": False}
        with patch.object(server_state, "_discover_trusted_agent_dir",
                          return_value=self.addon_dir, create=True):
            response = main.app.test_client().post("/init", json=context)
        self.assertEqual(response.status_code, 200, response.get_json())
        for key in pending:
            self.assertIsNone(STATE.get(key), key)
        old = pending["pending_file_refactor"]
        with patch.object(server_state, "_discover_trusted_agent_dir",
                          return_value=self.addon_dir, create=True):
            response = main.app.test_client().post(
                "/project/refactor/file/apply", json=dict(
                    context, old_path=old["old_path"],
                    new_path="res://src/renamed.gd"))
        self.assertEqual(response.status_code, 409)
        self.assertFalse(os.path.exists(os.path.join(self.root, "src", "renamed.gd")))

    def test_symbol_refactor_respects_self_reference_policy(self):
        target = os.path.join(self.root, "src", "lib.gd")
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("class_name SharedLib\nextends Node\nfunc shared():\n\tpass\n")
        agent_ref = os.path.join(self.addon_dir, "agent_panel.gd")
        with open(agent_ref, "w", encoding="utf-8", newline="\n") as handle:
            handle.write('extends Node\nvar lib: SharedLib\nfunc call_shared():\n\tlib.shared()\n')
        action = {"action": "rename_symbol", "kind": "function",
                  "declaration": "res://src/lib.gd:3",
                  "old_name": "shared", "new_name": "renamed_shared"}
        without_self = symbol_refactor.prepare_rename(
            self.root, action, allow_addons=True,
            allow_self_edit=False, addon_dir=self.addon_dir)
        self.assertNotIn("res://addons/Godot_agent/godot_agent/agent_panel.gd",
                         [item["path"] for item in without_self["files"]])
        with_self = symbol_refactor.prepare_rename(
            self.root, action, allow_addons=True,
            allow_self_edit=True, addon_dir=self.addon_dir)
        self.assertIn("res://addons/Godot_agent/godot_agent/agent_panel.gd",
                      [item["path"] for item in with_self["files"]])

    def test_editor_result_restores_reservation_when_policy_changes(self):
        STATE.update({
            "allow_addons": True, "allow_self_edit": True,
            "pending_action": {"action": "edit_scene"},
            "pending_scene_action": {
                "action": {"action": "edit_scene"},
                "scene": "res://addons/demo/scene.tscn",
                "action_id": "a" * 32, "execution_token": "token",
                "entry_id": "entry", "state": "executing",
                "policy_snapshot": {"allow_addons": True,
                                    "allow_self_edit": True,
                                    "addon_dir": os.path.realpath(self.addon_dir)},
            },
        })
        body = {"action_id": "a" * 32, "execution_token": "token",
                "editor_action_kind": "scene", "success": True,
                "scene_hash": "b" * 64}
        STATE["allow_addons"] = False
        with patch.object(
                main.history, "restore_reserved_change",
                return_value=(True, "restored", ["res://addons/demo/scene.tscn"])) as restore:
            with main.app.test_request_context(
                    "/chat/editor_action/result", method="POST", json=body):
                response, status = main.editor_action_result()
        self.assertEqual(status, 409)
        self.assertEqual(response.get_json()["code"], "stale_policy")
        self.assertTrue(response.get_json()["restored"])
        restore.assert_called_once_with(
            self.root, "entry", current_hash="b" * 64, remove_created=False)
        self.assertIsNone(STATE["pending_scene_action"])


if __name__ == "__main__":
    unittest.main()
