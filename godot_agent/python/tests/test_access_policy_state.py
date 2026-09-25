# -*- coding: utf-8 -*-
"""Strict state parsing for independent add-on/self-edit capabilities."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import project_tools
import server_state


class AccessPolicyStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="access_policy_state_")
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.agent = os.path.join(self.root, "addons", "RenamedAgent", "core")
        os.makedirs(self.agent)
        self._saved = {key: server_state.STATE.get(key) for key in (
            "project_root", "addon_dir", "allow_addons", "allow_self_edit")}

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                server_state.STATE.pop(key, None)
            else:
                server_state.STATE[key] = value

    def test_trusted_agent_root_is_derived_from_source_mode(self):
        inner = os.path.join(self.root, "addons", "RenamedWrapper", "godot_agent")
        module = os.path.join(inner, "python", "server", "server_state.py")
        os.makedirs(os.path.dirname(module), exist_ok=True)
        with open(module, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# server\n")
        self.assertEqual(os.path.normcase(server_state._discover_trusted_agent_dir(
            self.root, module_path=module)),
            os.path.normcase(os.path.realpath(inner)))

    def test_trusted_agent_root_is_derived_from_frozen_executable(self):
        inner = os.path.join(self.root, "addons", "AnotherWrapper", "godot_agent")
        executable = os.path.join(
            inner, "python", "dist", "godot_agent_server", "godot_agent_server.exe")
        os.makedirs(os.path.dirname(executable), exist_ok=True)
        with open(executable, "wb") as handle:
            handle.write(b"MZ")
        self.assertEqual(os.path.normcase(server_state._discover_trusted_agent_dir(
            self.root, executable=executable, frozen=True)),
            os.path.normcase(os.path.realpath(inner)))

    def test_client_addon_dir_is_never_the_authorization_root(self):
        other = os.path.join(self.root, "addons", "other")
        os.makedirs(other, exist_ok=True)
        server_state.STATE.update(
            project_root=self.root, addon_dir=self.agent,
            allow_addons=True, allow_self_edit=False)
        with patch.object(server_state, "_discover_trusted_agent_dir",
                          return_value=self.agent, create=True):
            for bad in (None, os.path.join(self.root, "outside"),
                        os.path.join(self.root, "addons", "missing"), other):
                with self.subTest(bad=bad), self.assertRaises(
                        server_state.SessionContextError):
                    server_state._apply_session_context({
                        "project_root": self.root, "addon_dir": bad,
                        "allow_addons": True, "allow_self_edit": True})
                self.assertIs(server_state.STATE["allow_addons"], True)
                self.assertIs(server_state.STATE["allow_self_edit"], False)
                self.assertEqual(server_state.STATE["addon_dir"], self.agent)
        self.assertFalse(project_tools.can_write_project_path(
            "res://addons/RenamedAgent/core/agent.gd", self.root,
            allow_addons=True, allow_self_edit=False, addon_dir=self.agent))

    def test_missing_addon_dir_fails_closed_without_client_authority(self):
        server_state.STATE.update(
            project_root=self.root, addon_dir=None,
            allow_addons=False, allow_self_edit=False)
        with patch.object(server_state, "_discover_trusted_agent_dir",
                          return_value=self.agent, create=True):
            server_state._apply_session_context({
                "project_root": self.root, "allow_addons": True,
                "allow_self_edit": True})
        self.assertEqual(server_state.STATE["addon_dir"], self.agent)
        self.assertIs(server_state.STATE["allow_addons"], False)
        self.assertIs(server_state.STATE["allow_self_edit"], False)
        self.assertFalse(project_tools.can_write_project_path(
            "res://addons/other/evil.gd", self.root,
            allow_addons=True, allow_self_edit=False, addon_dir=None))

    def test_defaults_false_and_exact_booleans_only(self):
        server_state.STATE.update(project_root=self.root, addon_dir=None,
                                  allow_addons=False, allow_self_edit=False)
        with patch.object(server_state, "_discover_trusted_agent_dir",
                          return_value=self.agent, create=True):
            server_state._apply_session_context({
                "project_root": self.root, "addon_dir": self.agent,
                "allow_addons": 1, "allow_self_edit": "true"})
            self.assertIs(server_state.STATE["allow_addons"], False)
            self.assertIs(server_state.STATE["allow_self_edit"], False)
            server_state._apply_session_context({"allow_addons": True})
        self.assertIs(server_state.STATE["allow_addons"], False)

    def test_valid_client_metadata_enables_only_requested_capability(self):
        with patch.object(server_state, "_discover_trusted_agent_dir",
                          return_value=self.agent, create=True):
            snapshot = server_state._apply_session_context({
                "project_root": self.root, "addon_dir": self.agent,
                "allow_addons": True, "allow_self_edit": False})
        self.assertEqual(snapshot, {
            "allow_addons": True, "allow_self_edit": False,
            "addon_dir": os.path.realpath(self.agent)})
        self.assertTrue(server_state._policy_matches(snapshot))
        server_state.STATE["allow_self_edit"] = True
        self.assertFalse(server_state._policy_matches(snapshot))



if __name__ == "__main__":
    unittest.main()
