"""Protected paths and Windows aliases must not bypass action boundaries."""
import locale
import os
import shutil
import subprocess
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
        (self.base / "src" / "visible.gd").write_text("PROJECT_TOKEN\n", encoding="utf-8")
        (self.base / "Addons" / "regular.gd").write_text("ADDON_TOKEN\n", encoding="utf-8")
        self.wrapper = self.base / "Addons" / "RenamedWrapper"
        self.agent_dir = self.wrapper / "godot_agent"
        self.agent_dir.mkdir(parents=True)
        (self.agent_dir / "agent.gd").write_text("AGENT_TOKEN\n", encoding="utf-8")
        self.extra_addon = self.base / "Addons" / "RenamedWrapperExtra"
        self.extra_addon.mkdir()
        (self.extra_addon / "extra.gd").write_text("EXTRA_TOKEN\n", encoding="utf-8")
        (self.base / ".agent_history").mkdir()
    def test_agent_addon_validation_derives_renamed_wrapper_by_segment(self):
        canonical = project_tools.validate_agent_addon_dir(self.root, self.agent_dir)
        self.assertEqual(os.path.normcase(canonical),
                         os.path.normcase(os.path.realpath(self.agent_dir)))
        for value in (
                self.base,
                self.base / "Addons",
                self.base / "Addons-extra",
                self.base / "missing" / "godot_agent",
                str(self.agent_dir) + os.sep + ".." + os.sep
                + "RenamedWrapper" + os.sep + "godot_agent"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                project_tools.validate_agent_addon_dir(self.root, value)

        self.assertTrue(project_tools.is_agent_path(
            "res://addons/RenamedWrapper/godot_agent/agent.gd",
            self.root, self.agent_dir))
        self.assertTrue(project_tools.is_agent_path(
            "res://SRC/../ADDONS/renamedwrapper/GODOT_AGENT/agent.gd",
            self.root, self.agent_dir))
        self.assertFalse(project_tools.is_agent_path(
            "res://Addons/RenamedWrapperExtra/extra.gd",
            self.root, self.agent_dir))

    def test_access_capabilities_are_independent_and_fail_closed(self):
        agent = "res://Addons/RenamedWrapper/godot_agent/agent.gd"
        regular_addon = "res://Addons/regular.gd"
        project = "res://src/visible.gd"
        cases = (
            # allow_addons, allow_self_edit, agent, regular addon
            (False, False, False, False),
            (False, True, True, False),
            (True, False, False, True),
            (True, True, True, True),
        )
        for allow_addons, allow_self_edit, agent_allowed, addon_allowed in cases:
            with self.subTest(allow_addons=allow_addons,
                              allow_self_edit=allow_self_edit):
                flags = {
                    "project_root": self.root,
                    "allow_addons": allow_addons,
                    "allow_self_edit": allow_self_edit,
                    "addon_dir": str(self.agent_dir),
                }
                for accessor in (project_tools.can_read_project_path,
                                 project_tools.can_write_project_path,
                                 project_tools.can_reference_project_path):
                    self.assertTrue(accessor(project, **flags))
                    self.assertEqual(accessor(agent, **flags), agent_allowed)
                    self.assertEqual(accessor(regular_addon, **flags), addon_allowed)
                self.assertFalse(project_tools.can_write_project_path(
                    "res://src/../PROJECT.GODOT", **flags))

        for path in ("res://.agent_history/journal.json",
                     "res://../secret.txt"):
            self.assertFalse(project_tools.can_read_project_path(
                path, self.root, allow_addons=True, allow_self_edit=True,
                addon_dir=str(self.agent_dir)))



    def test_classification_assertions_and_policy_snapshot(self):
        addon_dir = str(self.agent_dir)
        settings = project_tools.classify_project_path(
            "res://src/../PROJECT.GODOT", self.root, addon_dir)
        self.assertEqual(settings["kind"], "project_settings")
        self.assertEqual(settings["path"], "res://project.godot")
        self.assertTrue(settings["is_project_settings"])

        agent = project_tools.classify_project_path(
            "res://addons/RenamedWrapper/godot_agent/agent.gd",
            self.root, addon_dir)
        self.assertEqual(agent["kind"], "agent")
        self.assertTrue(agent["is_addon"])
        self.assertTrue(agent["is_agent"])
        self.assertIsNone(agent["error"])

        extra = project_tools.classify_project_path(
            "res://Addons/RenamedWrapperExtra/extra.gd",
            self.root, addon_dir)
        self.assertEqual(extra["kind"], "addon")
        self.assertFalse(extra["is_agent"])

        self.assertTrue(project_tools.assert_can_write_project_path(
            "res://src/visible.gd", self.root))
        with self.assertRaises(ValueError):
            project_tools.assert_can_read_project_path(
                "res://Addons/regular.gd", self.root, addon_dir=addon_dir)
        with self.assertRaises(ValueError):
            project_tools.assert_can_write_project_path(
                "res://addons/RenamedWrapper/godot_agent/agent.gd",
                self.root, addon_dir=addon_dir)
        self.assertTrue(project_tools.assert_can_write_project_path(
            "res://addons/RenamedWrapper/godot_agent/agent.gd",
            self.root, allow_self_edit=True, addon_dir=addon_dir))
        with self.assertRaises(ValueError):
            project_tools.assert_can_reference_project_path(
                "res://.AGENT_HISTORY/journal.json", self.root,
                allow_addons=True, allow_self_edit=True, addon_dir=addon_dir)

        snapshot = project_tools.policy_snapshot(
            allow_addons=True, allow_self_edit=False, addon_dir=addon_dir)
        self.assertEqual(snapshot, {
            "allow_addons": True,
            "allow_self_edit": False,
            "addon_dir": addon_dir,
        })
        snapshot["allow_addons"] = False
        self.assertTrue(project_tools.policy_snapshot()["allow_addons"] is False)

    def test_scanners_default_hide_addons_and_flags_restore_only_allowed_scope(self):
        addon_dir = str(self.agent_dir)
        project_tools.exclude_agent_addon_dirs(addon_dir)

        def paths(query, **flags):
            rows, _ = project_tools.search_project_text(self.root, query, **flags)
            return {row["path"] for row in rows}

        self.assertIn("res://src/visible.gd", paths("PROJECT_TOKEN"))
        self.assertEqual(paths("ADDON_TOKEN"), set())
        self.assertEqual(paths("AGENT_TOKEN"), set())
        self.assertEqual(paths("EXTRA_TOKEN"), set())

        self.assertIn("res://Addons/regular.gd",
                      paths("ADDON_TOKEN", allow_addons=True, addon_dir=addon_dir))
        self.assertIn("res://Addons/RenamedWrapperExtra/extra.gd",
                      paths("EXTRA_TOKEN", allow_addons=True, addon_dir=addon_dir))
        self.assertEqual(paths("AGENT_TOKEN", allow_addons=True,
                               addon_dir=addon_dir), set())
        self.assertIn("res://Addons/RenamedWrapper/godot_agent/agent.gd",
                      paths("AGENT_TOKEN", allow_self_edit=True,
                            addon_dir=addon_dir))
        self.assertEqual(paths("ADDON_TOKEN", allow_self_edit=True,
                               addon_dir=addon_dir), set())

        default_tree = project_tools.build_project_tree(self.root)
        self.assertNotIn("Addons", default_tree)
        self_tree = project_tools.build_project_tree(
            self.root, allow_self_edit=True, addon_dir=addon_dir)
        self.assertIn("RenamedWrapper", self_tree)
        self.assertIn("agent.gd", self_tree)
        self.assertNotIn("regular.gd", self_tree)

        default_overview, _ = project_tools.build_project_overview(self.root)
        self.assertNotIn("Addons", default_overview)
        self_overview, _ = project_tools.build_project_overview(
            self.root, allow_self_edit=True, addon_dir=addon_dir)
        self.assertIn("RenamedWrapper", self_overview)

        self.assertNotIn("Addons", project_tools.describe_architecture(self.root))
        self.assertIn(
            "RenamedWrapper",
            project_tools.describe_architecture(
                self.root, allow_self_edit=True, addon_dir=addon_dir))

        default_snapshot = project_tools.snapshot_files(self.root)
        self.assertFalse(any(key.startswith("Addons/") for key in default_snapshot))
        self_snapshot = project_tools.snapshot_files(
            self.root, allow_self_edit=True, addon_dir=addon_dir)
        self.assertIn("Addons/RenamedWrapper/godot_agent/agent.gd",
                      self_snapshot)

    def test_symlink_identity_uses_canonical_agent_wrapper(self):
        try:
            (self.base / "agent_alias").symlink_to(
                self.wrapper, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks not available")
        alias_path = "res://agent_alias/godot_agent/agent.gd"
        self.assertTrue(project_tools.is_agent_path(
            alias_path, self.root, self.agent_dir))
        self.assertTrue(project_tools.can_write_project_path(
            alias_path, self.root, allow_self_edit=True,
            addon_dir=str(self.agent_dir)))

    @unittest.skipUnless(os.name == "nt", "Windows directory junction")
    def test_windows_junction_uses_resolved_policy_identity(self):
        outside = Path(tempfile.mkdtemp(prefix="path_policy_outside_"))
        self.addCleanup(lambda: outside.exists() and shutil.rmtree(str(outside)))
        (outside / "secret.gd").write_text("OUTSIDE_JUNCTION_TOKEN\n", encoding="utf-8")
        outside_link = self.base / "outside_junction"
        agent_link = self.base / "agent_junction"
        for link, target in ((outside_link, outside), (agent_link, self.wrapper)):
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding=locale.getpreferredencoding(False), errors="replace")
            if result.returncode != 0:
                self.skipTest("directory junction not available: %s" % result.stdout)
            self.addCleanup(lambda p=link: os.path.isdir(p) and os.rmdir(p))

        rows, _ = project_tools.search_project_text(
            self.root, "OUTSIDE_JUNCTION_TOKEN", max_results=5)
        self.assertEqual(rows, [])
        self.assertNotIn("secret.gd", project_tools.build_project_tree(self.root))
        self.assertFalse(any("outside_junction/" in key
                             for key in project_tools.snapshot_files(self.root)))

        alias_path = "res://agent_junction/godot_agent/agent.gd"
        self.assertTrue(project_tools.is_agent_path(
            alias_path, self.root, self.agent_dir))
        rows, _ = project_tools.search_project_text(
            self.root, "AGENT_TOKEN", allow_self_edit=True,
            addon_dir=str(self.agent_dir))
        self.assertIn("res://Addons/RenamedWrapper/godot_agent/agent.gd",
                      {row["path"] for row in rows})

    def test_all_boundaries_reject_mixed_case_and_resolved_addon_paths(self):
        addon_dir = str(self.agent_dir)
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
                self.assertEqual(gather_context._allowed_path(
                    self.root, script, allow_addons=True, addon_dir=addon_dir), script)

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

    def test_context_metadata_hides_protected_main_scene_and_autoload(self):
        import gather_context
        import librarian
        protected = "res://addons/RenamedWrapper/godot_agent/private.gd"
        public = "res://src/autoload.gd"
        (self.base / "project.godot").write_text(
            "[application]\nrun/main_scene=\"%s\"\n\n[autoload]\n"
            "Agent=\"*%s\"\nGame=\"*%s\"\n" % (protected, protected, public),
            encoding="utf-8")
        (self.base / "src" / "autoload.gd").write_text("extends Node\n", encoding="utf-8")
        flags = {"allow_addons": False, "allow_self_edit": False,
                 "addon_dir": str(self.agent_dir)}
        architecture = project_tools.describe_architecture(self.root, **flags)
        self.assertNotIn(protected, architecture)
        self.assertIn(public, architecture)
        autoloads = librarian._autoloads(self.root, **flags)
        self.assertNotIn(protected, repr(autoloads))
        self.assertIn(public, repr(autoloads))
        settings = gather_context._project_settings(self.root, "", **flags)
        self.assertNotIn(protected, repr(settings))
        self.assertIn(public, repr(settings))

        flags["allow_self_edit"] = True
        self.assertIn(protected, project_tools.describe_architecture(self.root, **flags))
        self.assertIn(protected, repr(librarian._autoloads(self.root, **flags)))
        self.assertIn(protected, repr(gather_context._project_settings(self.root, "", **flags)))

    def test_policy_aware_raw_helpers_fail_closed(self):
        for accessor, args in (
                (project_tools.policy_read_project_file,
                 ("res://addons/RenamedWrapperExtra/extra.gd",)),
                (project_tools.policy_create_project_file,
                 ("res://addons/RenamedWrapperExtra/new.gd", "extends Node\n")),
                (project_tools.policy_describe_scene,
                 ("res://addons/RenamedWrapper/extra.tscn",))):
            with self.subTest(accessor=accessor.__name__):
                with self.assertRaises(ValueError):
                    accessor(self.root, *args, allow_addons=True,
                             allow_self_edit=False, addon_dir=None)

    def test_symlink_into_addon_obeys_destination_policy(self):
        try:
            (self.base / "linked").symlink_to(self.base / "Addons", target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks not available")
        self.assertTrue(project_tools.is_addon_path("res://linked/player.gd", self.root))
        self.assertEqual(gather_context._allowed_path(self.root, "res://linked/player.gd"), "")


if __name__ == "__main__":
    unittest.main()
