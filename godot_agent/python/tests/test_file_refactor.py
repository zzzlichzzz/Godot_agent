# -*- coding: utf-8 -*-
"""Unit tests for file_refactor: references search, rename transaction, and rollback."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import file_refactor
import history_manager


class FileRefactorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="file_refactor_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        # Create basic project structure
        (self.root / "project.godot").write_text(
            'config_version=5\n\n[autoload]\nPlayer="*res://src/player.gd"\nOther="*res://src/other.gd"\n',
            encoding="utf-8"
        )
        (self.root / "src").mkdir(parents=True)
        (self.root / "src" / "sub").mkdir(parents=True)
        (self.root / "scenes").mkdir(parents=True)

        # Target file to rename
        self.target_gd = self.root / "src" / "player.gd"
        self.target_gd.write_text('extends Node\nclass_name Player\n\nvar hp = 100\n', encoding="utf-8")
        (self.root / "src" / "player.gd.uid").write_text('uid://player123\n', encoding="utf-8")

        # Unrelated file with similar prefix to test boundary safety
        (self.root / "src" / "player_controller.gd").write_text(
            'extends Node\n# should not be touched\n', encoding="utf-8"
        )

        # Main script with exact references
        self.main_gd = self.root / "src" / "main.gd"
        self.main_gd.write_text(
            'extends Node\n\n'
            'const PlayerClass = preload("res://src/player.gd")\n'
            'var p = load("res://src/player.gd")\n'
            'var c = preload("res://src/player_controller.gd")\n',
            encoding="utf-8"
        )

        # Sub script with relative preload
        self.sub_gd = self.root / "src" / "sub" / "helper.gd"
        self.sub_gd.write_text(
            'extends Node\n\n'
            'const P = preload("../player.gd")\n',
            encoding="utf-8"
        )

        # Scene file with ext_resource
        self.level_tscn = self.root / "scenes" / "level.tscn"
        self.level_tscn.write_text(
            '[gd_scene load_steps=2 format=3 uid="uid://lvl1"]\n\n'
            '[ext_resource type="Script" path="res://src/player.gd" id="1_p"]\n'
            '[ext_resource type="Script" path="res://src/player_controller.gd" id="2_pc"]\n\n'
            '[node name="Level" type="Node2D"]\n',
            encoding="utf-8"
        )

    def test_find_file_references(self):
        refs = file_refactor.find_file_references(str(self.root), "res://src/player.gd")
        ref_paths = {r["path"] for r in refs}

        self.assertIn("res://src/main.gd", ref_paths)
        self.assertIn("res://src/sub/helper.gd", ref_paths)
        self.assertIn("res://scenes/level.tscn", ref_paths)
        self.assertIn("res://project.godot", ref_paths)
        self.assertNotIn("res://src/player_controller.gd", ref_paths)

    def test_prepare_file_rename_transaction(self):
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://src/player.gd", "res://src/hero.gd", update_references=True
        )
        self.assertEqual(prep["action"], "rename_file")
        self.assertEqual(prep["old_path"], "res://src/player.gd")
        self.assertEqual(prep["new_path"], "res://src/hero.gd")
        self.assertEqual(prep["reference_count"], 5)  # 2 in main, 1 in sub, 1 in scene, 1 in project.godot

        files_by_path = {f["path"]: f for f in prep["files"]}
        self.assertIn("res://src/player.gd", files_by_path)
        self.assertEqual(files_by_path["res://src/player.gd"]["action"], "move_file")
        self.assertEqual(files_by_path["res://src/player.gd"]["dest"], "res://src/hero.gd")

        # Verify patch content
        main_patch = files_by_path["res://src/main.gd"]
        self.assertIn('preload("res://src/hero.gd")', main_patch["after_bytes"].decode("utf-8"))
        self.assertIn('load("res://src/hero.gd")', main_patch["after_bytes"].decode("utf-8"))
        self.assertIn('preload("res://src/player_controller.gd")', main_patch["after_bytes"].decode("utf-8"))

        sub_patch = files_by_path["res://src/sub/helper.gd"]
        self.assertIn('preload("res://src/hero.gd")', sub_patch["after_bytes"].decode("utf-8"))

        scene_patch = files_by_path["res://scenes/level.tscn"]
        self.assertIn('path="res://src/hero.gd"', scene_patch["after_bytes"].decode("utf-8"))
        self.assertIn('path="res://src/player_controller.gd"', scene_patch["after_bytes"].decode("utf-8"))

        project_patch = files_by_path["res://project.godot"]
        self.assertIn('Player="*res://src/hero.gd"', project_patch["after_bytes"].decode("utf-8"))
        self.assertIn('Other="*res://src/other.gd"', project_patch["after_bytes"].decode("utf-8"))

    def test_apply_and_rollback(self):
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://src/player.gd", "res://src/hero.gd", update_references=True
        )
        res = file_refactor.apply_prepared_file_rename(str(self.root), prep)
        self.assertTrue(res["entry_id"])

        # 1. Verify filesystem after rename
        self.assertFalse((self.root / "src" / "player.gd").exists())
        self.assertFalse((self.root / "src" / "player.gd.uid").exists())
        self.assertTrue((self.root / "src" / "hero.gd").exists())
        self.assertTrue((self.root / "src" / "hero.gd.uid").exists())
        self.assertEqual((self.root / "src" / "hero.gd.uid").read_text(encoding="utf-8"), "uid://player123\n")

        # Verify patched files
        self.assertIn('preload("res://src/hero.gd")', self.main_gd.read_text(encoding="utf-8"))
        self.assertIn('preload("res://src/hero.gd")', self.sub_gd.read_text(encoding="utf-8"))
        self.assertIn('path="res://src/hero.gd"', self.level_tscn.read_text(encoding="utf-8"))
        self.assertIn('Player="*res://src/hero.gd"', (self.root / "project.godot").read_text(encoding="utf-8"))

        # 2. Rollback
        ok, msg, needs_force, paths, diff = history_manager.rollback_last(str(self.root))
        self.assertTrue(ok, msg)

        # 3. Verify filesystem after rollback
        self.assertTrue((self.root / "src" / "player.gd").exists())
        self.assertTrue((self.root / "src" / "player.gd.uid").exists())
        self.assertFalse((self.root / "src" / "hero.gd").exists())
        self.assertFalse((self.root / "src" / "hero.gd.uid").exists())

        # Verify references restored
        self.assertIn('preload("res://src/player.gd")', self.main_gd.read_text(encoding="utf-8"))
        self.assertNotIn('preload("res://src/hero.gd")', self.main_gd.read_text(encoding="utf-8"))
        self.assertIn('preload("../player.gd")', self.sub_gd.read_text(encoding="utf-8"))
        self.assertIn('path="res://src/player.gd"', self.level_tscn.read_text(encoding="utf-8"))
        self.assertIn('Player="*res://src/player.gd"', (self.root / "project.godot").read_text(encoding="utf-8"))

    def test_relocate_file_to_subfolder_with_internal_relative_paths(self):
        # Setup files for relocation
        (self.root / "base.gd").write_text('extends Node\nclass_name BaseEntity\n', encoding="utf-8")
        (self.root / "src" / "weapon.gd").write_text('extends Node\nclass_name Weapon\n', encoding="utf-8")
        (self.root / "src" / "shield.gd").write_text('extends Node\nclass_name Shield\n', encoding="utf-8")

        rel_script = self.root / "src" / "unit.gd"
        rel_script.write_text(
            'extends "../base.gd"\n\n'
            'const W = preload("weapon.gd")\n'
            'const S = preload("res://src/shield.gd")\n',
            encoding="utf-8"
        )

        caller_script = self.root / "src" / "caller.gd"
        caller_script.write_text(
            'extends Node\n\n'
            'const U = preload("unit.gd")\n',
            encoding="utf-8"
        )

        # Move res://src/unit.gd to res://src/entities/unit.gd
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://src/unit.gd", "res://src/entities/unit.gd", update_references=True
        )
        self.assertEqual(prep["action"], "rename_file")
        self.assertFalse(prep.get("is_directory", False))

        # Check internal path changes in prep
        unit_item = next(f for f in prep["files"] if f["path"] == "res://src/unit.gd")
        unit_after = unit_item["after_bytes"].decode("utf-8")
        # extends "../base.gd" -> outside new_dir -> res://base.gd
        self.assertIn('extends "res://base.gd"', unit_after)
        # preload("weapon.gd") -> outside new_dir -> res://src/weapon.gd
        self.assertIn('preload("res://src/weapon.gd")', unit_after)
        # preload("res://src/shield.gd") unchanged
        self.assertIn('preload("res://src/shield.gd")', unit_after)

        # Apply
        res = file_refactor.apply_prepared_file_rename(str(self.root), prep)
        self.assertTrue(res["entry_id"])

        # Check filesystem
        self.assertFalse(rel_script.exists())
        new_unit = self.root / "src" / "entities" / "unit.gd"
        self.assertTrue(new_unit.exists())
        self.assertEqual(
            new_unit.read_text(encoding="utf-8").replace("\r\n", "\n"),
            unit_after.replace("\r\n", "\n")
        )
        self.assertIn('preload("res://src/entities/unit.gd")', caller_script.read_text(encoding="utf-8"))

        # Rollback
        ok, msg, _, _, _ = history_manager.rollback_last(str(self.root))
        self.assertTrue(ok, msg)
        self.assertTrue(rel_script.exists())
        self.assertFalse(new_unit.exists())
        self.assertIn('extends "../base.gd"', rel_script.read_text(encoding="utf-8"))
        self.assertIn('preload("weapon.gd")', rel_script.read_text(encoding="utf-8"))
        self.assertIn('preload("unit.gd")', caller_script.read_text(encoding="utf-8"))

    def test_relocate_directory(self):
        # Create a directory with multiple files and internal references
        combat_dir = self.root / "src" / "combat"
        combat_dir.mkdir(parents=True, exist_ok=True)

        sword_gd = combat_dir / "sword.gd"
        sword_gd.write_text(
            'extends Node\n\n'
            'const Shield = preload("shield.gd")\n'
            'const AbsShield = preload("res://src/combat/shield.gd")\n',
            encoding="utf-8"
        )
        shield_gd = combat_dir / "shield.gd"
        shield_gd.write_text('extends Node\nclass_name Shield\n', encoding="utf-8")

        arena_tscn = combat_dir / "arena.tscn"
        arena_tscn.write_text(
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://src/combat/sword.gd" id="1_s"]\n\n'
            '[node name="Arena" type="Node"]\n',
            encoding="utf-8"
        )

        external_gd = self.root / "src" / "game.gd"
        external_gd.write_text(
            'extends Node\n\n'
            'const S1 = preload("res://src/combat/sword.gd")\n'
            'const S2 = preload("combat/sword.gd")\n',
            encoding="utf-8"
        )

        (self.root / "project.godot").write_text(
            'config_version=5\n\n[autoload]\nCombat="*res://src/combat/sword.gd"\n',
            encoding="utf-8"
        )

        # Move directory res://src/combat to res://src/systems/battle
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://src/combat", "res://src/systems/battle", update_references=True
        )
        self.assertTrue(prep["is_directory"])
        self.assertEqual(len(prep["moved_files"]), 3)  # sword.gd, shield.gd, arena.tscn

        # Apply directory relocation
        res = file_refactor.apply_prepared_file_rename(str(self.root), prep)
        self.assertTrue(res["entry_id"])

        # Verify old dir is gone, new dir exists
        self.assertFalse(combat_dir.exists())
        new_dir = self.root / "src" / "systems" / "battle"
        self.assertTrue(new_dir.exists())
        self.assertTrue((new_dir / "sword.gd").exists())
        self.assertTrue((new_dir / "shield.gd").exists())
        self.assertTrue((new_dir / "arena.tscn").exists())

        # Verify internal references
        sword_content = (new_dir / "sword.gd").read_text(encoding="utf-8")
        self.assertIn('preload("shield.gd")', sword_content)
        self.assertIn('preload("res://src/systems/battle/shield.gd")', sword_content)

        arena_content = (new_dir / "arena.tscn").read_text(encoding="utf-8")
        self.assertIn('path="res://src/systems/battle/sword.gd"', arena_content)

        # Verify external references
        game_content = external_gd.read_text(encoding="utf-8")
        self.assertIn('preload("res://src/systems/battle/sword.gd")', game_content)
        self.assertNotIn('res://src/combat/sword.gd', game_content)

        proj_content = (self.root / "project.godot").read_text(encoding="utf-8")
        self.assertIn('Combat="*res://src/systems/battle/sword.gd"', proj_content)

        # Rollback
        ok, msg, _, _, _ = history_manager.rollback_last(str(self.root))
        self.assertTrue(ok, msg)

        # Verify restored
        self.assertTrue(combat_dir.exists())
        self.assertTrue((combat_dir / "sword.gd").exists())
        self.assertTrue((combat_dir / "shield.gd").exists())
        self.assertTrue((combat_dir / "arena.tscn").exists())
        self.assertFalse(new_dir.exists())

        self.assertIn('preload("res://src/combat/sword.gd")', external_gd.read_text(encoding="utf-8"))
        self.assertIn('Combat="*res://src/combat/sword.gd"', (self.root / "project.godot").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

