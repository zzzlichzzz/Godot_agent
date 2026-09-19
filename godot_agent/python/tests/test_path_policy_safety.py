"""Protected paths and Windows aliases must not bypass action boundaries."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import gather_context
import main
import project_settings_actions
import project_tools
import resource_actions
import runtime_checks
import scene_actions
import symbol_refactor
import transaction_actions


class PathPolicySafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="path_policy_")
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.base = Path(self.root)
        (self.base / "Addons").mkdir()
        (self.base / "src").mkdir()
        (self.base / "project.godot").write_text("config_version=5\n", encoding="utf-8")
        for name, text in (("player.gd", "extends Node\n"),
                           ("main.tscn", '[gd_scene format=3]\n[node name="Main" type="Node"]\n'),
                           ("theme.tres", '[gd_resource type="Theme" format=3]\n[resource]\n')):
            (self.base / "Addons" / name).write_text(text, encoding="utf-8")

    def test_all_boundaries_reject_mixed_case_and_resolved_addon_paths(self):
        for prefix in ("res://Addons/", "res://src/../Addons/"):
            with self.subTest(prefix=prefix):
                script, scene, resource = [prefix + n for n in ("player.gd", "main.tscn", "theme.tres")]
                with patch.dict(main.STATE, project_root=self.root):
                    self.assertTrue(main._is_addon_path(script))
                self.assertEqual(gather_context._allowed_path(self.root, script), "")
                operations = [
                    lambda: scene_actions.normalize_action(self.root, {"action": "edit_scene", "scene": scene,
                        "operations": [{"op": "add_node", "parent": ".", "name": "Child", "type": "Node"}]}),
                    lambda: resource_actions.normalize_action(self.root, {"action": "edit_resource", "resource": resource,
                        "operations": [{"op": "set_property", "target": [], "property": "default_font_size",
                                        "value": {"type": "int", "value": 20}}]}),
                    lambda: project_settings_actions.normalize_action(self.root, {"action": "edit_project_settings",
                        "operations": [{"op": "add_autoload", "name": "Player", "path": script}]}),
                    lambda: runtime_checks.normalize_action(self.root, {"action": "run_check", "scene": scene,
                        "steps": [{"op": "assert_node", "node": ".", "exists": True}]}),
                    lambda: symbol_refactor.prepare_rename(self.root, {"action": "rename_symbol", "kind": "function",
                        "declaration": script + ":1", "old_name": "tick", "new_name": "update_tick"}),
                ]
                for operation in operations:
                    with self.assertRaises(ValueError):
                        operation()
                self.assertEqual(gather_context._allowed_path(self.root, script, allow_addons=True), script)

    def test_private_history_and_project_settings_aliases_are_blocked(self):
        for path in ("res://.AGENT_HISTORY/journal.json", "res://src/../.AgEnT_HiStOrY/journal.json"):
            with self.assertRaises(ValueError):
                project_tools._resolve_safe_path(self.root, path)
        with self.assertRaises(transaction_actions.TransactionError):
            transaction_actions.prepare(self.root, {"action": "transaction", "operations": [
                {"action": "create_file", "path": "res://PROJECT.GODOT", "content": "overwrite"}]})

    @unittest.skipUnless(os.name == "nt", "case-insensitive filesystem alias")
    def test_transaction_refuses_two_spellings_of_same_windows_file(self):
        path = self.base / "src" / "player.gd"
        path.write_text("extends Node\nvar hp = 1\n", encoding="utf-8")
        with self.assertRaisesRegex(transaction_actions.TransactionError, "разными путями"):
            transaction_actions.prepare(self.root, {"action": "transaction", "operations": [
                {"action": "patch_file", "path": "res://src/player.gd", "search": "hp = 1", "replace": "hp = 2"},
                {"action": "create_file", "path": "res://SRC/PLAYER.GD", "content": "extends Node\n"}]})
        self.assertEqual(path.read_text(encoding="utf-8"), "extends Node\nvar hp = 1\n")

    def test_symlink_into_addon_obeys_destination_policy(self):
        try:
            (self.base / "linked").symlink_to(self.base / "Addons", target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks not available")
        self.assertTrue(project_tools.is_addon_path("res://linked/player.gd", self.root))
        self.assertEqual(gather_context._allowed_path(self.root, "res://linked/player.gd"), "")


if __name__ == "__main__":
    unittest.main()
