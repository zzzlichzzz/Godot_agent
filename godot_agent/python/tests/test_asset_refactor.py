# -*- coding: utf-8 -*-
"""Unit tests for asset and companion .import file refactoring:
- Automatic detection and movement of companion .import files
- Updating source_file inside .import while preserving Godot 4 UID
- Cascade reference updates in .tscn, .tres, .gd, and project.godot
- Directory relocation with multiple assets and .import files
- Safe atomic rollback via history_manager
"""

import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import file_refactor
import history_manager


SAMPLE_IMPORT_TEMPLATE = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="{uid}"
path="res://.godot/imported/{filename}-{cache_hash}.ctex"
metadata={{
"vram_texture": false
}}

[deps]

source_file="{source_file}"
dest_files=["res://.godot/imported/{filename}-{cache_hash}.ctex"]

[params]

compress/mode=0
compress/high_quality=false
"""


class AssetRefactorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="asset_refactor_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        # Create basic Godot project structure
        (self.root / "project.godot").write_text(
            'config_version=5\n\n'
            '[application]\n'
            'config/name="AssetRefactorTest"\n'
            'config/icon="res://icon.svg"\n',
            encoding="utf-8"
        )
        (self.root / "textures").mkdir(parents=True)
        (self.root / "scenes").mkdir(parents=True)
        (self.root / "scripts").mkdir(parents=True)

        # Asset 1: icon.svg with icon.svg.import
        self.icon_svg = self.root / "icon.svg"
        self.icon_svg.write_text("<svg>icon</svg>", encoding="utf-8")
        self.icon_import = self.root / "icon.svg.import"
        self.icon_import.write_text(
            SAMPLE_IMPORT_TEMPLATE.format(
                uid="uid://icon_uid_001",
                filename="icon.svg",
                cache_hash="111111",
                source_file="res://icon.svg"
            ),
            encoding="utf-8"
        )

        # Asset 2: textures/player.png with textures/player.png.import
        self.player_png = self.root / "textures" / "player.png"
        self.player_png.write_bytes(b"\x89PNG\r\n\x1a\nfake_png_data")
        self.player_import = self.root / "textures" / "player.png.import"
        self.player_import.write_text(
            SAMPLE_IMPORT_TEMPLATE.format(
                uid="uid://player_uid_002",
                filename="player.png",
                cache_hash="222222",
                source_file="res://textures/player.png"
            ),
            encoding="utf-8"
        )

        # Scene referencing player.png by UID and path
        self.main_tscn = self.root / "scenes" / "main.tscn"
        self.main_tscn.write_text(
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Texture2D" uid="uid://player_uid_002" path="res://textures/player.png" id="1_tex"]\n\n'
            '[node name="Main" type="Node2D"]\n'
            '[node name="Sprite2D" type="Sprite2D" parent="."]\n'
            'texture = ExtResource("1_tex")\n',
            encoding="utf-8"
        )

        # Script referencing both icon.svg and player.png
        self.game_gd = self.root / "scripts" / "game.gd"
        self.game_gd.write_text(
            'extends Node\n\n'
            'const ICON = preload("res://icon.svg")\n'
            'var player_tex = load("res://textures/player.png")\n',
            encoding="utf-8"
        )

    def test_single_asset_rename_updates_import_and_references(self):
        """Renaming an asset renames its .import, updates source_file, preserves UID and updates references."""
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://textures/player.png", "res://textures/hero.png", update_references=True
        )
        self.assertEqual(prep["action"], "rename_file")
        self.assertEqual(prep["old_path"], "res://textures/player.png")
        self.assertEqual(prep["new_path"], "res://textures/hero.png")

        # Check prepared files: should have player.png (move), player.png.import (move), scenes/main.tscn (patch), scripts/game.gd (patch)
        files_by_path = {f["path"]: f for f in prep["files"]}
        self.assertIn("res://textures/player.png", files_by_path)
        self.assertIn("res://textures/player.png.import", files_by_path)
        self.assertIn("res://scenes/main.tscn", files_by_path)
        self.assertIn("res://scripts/game.gd", files_by_path)

        # Check import file diff and bytes
        imp_file = files_by_path["res://textures/player.png.import"]
        self.assertEqual(imp_file["action"], "move_file")
        self.assertEqual(imp_file["dest"], "res://textures/hero.png.import")
        imp_after = imp_file["after_bytes"].decode("utf-8")
        self.assertIn('source_file="res://textures/hero.png"', imp_after)
        self.assertIn('uid="uid://player_uid_002"', imp_after)

        # Apply transaction
        res = file_refactor.apply_prepared_file_rename(str(self.root), prep)
        self.assertTrue(res["entry_id"])

        # Verify on filesystem
        self.assertFalse(self.player_png.exists())
        self.assertFalse(self.player_import.exists())

        new_png = self.root / "textures" / "hero.png"
        new_import = self.root / "textures" / "hero.png.import"
        self.assertTrue(new_png.exists())
        self.assertTrue(new_import.exists())

        # Verify new import content
        new_import_text = new_import.read_text(encoding="utf-8")
        self.assertIn('source_file="res://textures/hero.png"', new_import_text)
        self.assertIn('uid="uid://player_uid_002"', new_import_text)

        # Verify scene reference updated
        scene_text = self.main_tscn.read_text(encoding="utf-8")
        self.assertIn('path="res://textures/hero.png"', scene_text)
        self.assertIn('uid="uid://player_uid_002"', scene_text)

        # Verify script reference updated
        script_text = self.game_gd.read_text(encoding="utf-8")
        self.assertIn('load("res://textures/hero.png")', script_text)

    def test_asset_relocation_to_new_folder(self):
        """Moving an asset to a new subfolder moves its .import, creates directory, and updates project.godot."""
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://icon.svg", "res://art/logo.svg", update_references=True
        )
        res = file_refactor.apply_prepared_file_rename(str(self.root), prep)
        self.assertTrue(res["entry_id"])

        # Check old files removed
        self.assertFalse(self.icon_svg.exists())
        self.assertFalse(self.icon_import.exists())

        # Check new files created
        new_svg = self.root / "art" / "logo.svg"
        new_import = self.root / "art" / "logo.svg.import"
        self.assertTrue(new_svg.exists())
        self.assertTrue(new_import.exists())

        new_import_text = new_import.read_text(encoding="utf-8")
        self.assertIn('source_file="res://art/logo.svg"', new_import_text)
        self.assertIn('uid="uid://icon_uid_001"', new_import_text)

        # Check project.godot updated
        proj_text = (self.root / "project.godot").read_text(encoding="utf-8")
        self.assertIn('config/icon="res://art/logo.svg"', proj_text)

        # Check script updated
        script_text = self.game_gd.read_text(encoding="utf-8")
        self.assertIn('preload("res://art/logo.svg")', script_text)

    def test_directory_relocation_with_multiple_assets_and_imports(self):
        """Relocating a directory moves all assets and all companion .import files without loss."""
        # Add another asset to textures/
        enemy_png = self.root / "textures" / "enemy.png"
        enemy_png.write_bytes(b"\x89PNG\r\n\x1a\nenemy_data")
        enemy_import = self.root / "textures" / "enemy.png.import"
        enemy_import.write_text(
            SAMPLE_IMPORT_TEMPLATE.format(
                uid="uid://enemy_uid_003",
                filename="enemy.png",
                cache_hash="333333",
                source_file="res://textures/enemy.png"
            ),
            encoding="utf-8"
        )

        # Relocate res://textures -> res://art/sprites
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://textures", "res://art/sprites", update_references=True
        )
        self.assertTrue(prep["is_directory"])

        # In moved_files (assets): player.png, enemy.png
        self.assertEqual(len(prep["moved_files"]), 2)
        # In files_to_modify: 2 assets + 2 imports + 2 patched files (scene + script)
        paths_to_modify = [f["path"] for f in prep["files"]]
        self.assertIn("res://textures/player.png", paths_to_modify)
        self.assertIn("res://textures/player.png.import", paths_to_modify)
        self.assertIn("res://textures/enemy.png", paths_to_modify)
        self.assertIn("res://textures/enemy.png.import", paths_to_modify)

        res = file_refactor.apply_prepared_file_rename(str(self.root), prep)
        self.assertTrue(res["entry_id"])

        # Verify old dir is gone
        self.assertFalse((self.root / "textures").exists())

        # Verify new dir contains all files
        new_sprites = self.root / "art" / "sprites"
        self.assertTrue(new_sprites.exists())
        self.assertTrue((new_sprites / "player.png").exists())
        self.assertTrue((new_sprites / "player.png.import").exists())
        self.assertTrue((new_sprites / "enemy.png").exists())
        self.assertTrue((new_sprites / "enemy.png.import").exists())

        # Verify import content updated
        p_imp = (new_sprites / "player.png.import").read_text(encoding="utf-8")
        self.assertIn('source_file="res://art/sprites/player.png"', p_imp)
        self.assertIn('uid="uid://player_uid_002"', p_imp)

        e_imp = (new_sprites / "enemy.png.import").read_text(encoding="utf-8")
        self.assertIn('source_file="res://art/sprites/enemy.png"', e_imp)
        self.assertIn('uid="uid://enemy_uid_003"', e_imp)

        # Verify scene reference updated
        scene_text = self.main_tscn.read_text(encoding="utf-8")
        self.assertIn('path="res://art/sprites/player.png"', scene_text)

    def test_asset_rename_and_rollback(self):
        """Rollback restores the asset, its .import file with original source_file, and references."""
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://textures/player.png", "res://textures/hero.png", update_references=True
        )
        file_refactor.apply_prepared_file_rename(str(self.root), prep)

        # Verify rename happened
        self.assertTrue((self.root / "textures" / "hero.png").exists())
        self.assertTrue((self.root / "textures" / "hero.png.import").exists())
        self.assertFalse((self.root / "textures" / "player.png").exists())
        self.assertFalse((self.root / "textures" / "player.png.import").exists())

        # Rollback
        ok, msg, needs_force, paths, diff = history_manager.rollback_last(str(self.root))
        self.assertTrue(ok, msg)

        # Verify filesystem after rollback
        self.assertTrue((self.root / "textures" / "player.png").exists())
        self.assertTrue((self.root / "textures" / "player.png.import").exists())
        self.assertFalse((self.root / "textures" / "hero.png").exists())
        self.assertFalse((self.root / "textures" / "hero.png.import").exists())

        # Verify original import content restored
        restored_import = (self.root / "textures" / "player.png.import").read_text(encoding="utf-8")
        self.assertIn('source_file="res://textures/player.png"', restored_import)
        self.assertIn('uid="uid://player_uid_002"', restored_import)

        # Verify references restored
        self.assertIn('path="res://textures/player.png"', self.main_tscn.read_text(encoding="utf-8"))
        self.assertIn('load("res://textures/player.png")', self.game_gd.read_text(encoding="utf-8"))

    def test_direct_import_or_uid_rename_rejected(self):
        """Directly renaming .import or .uid files is rejected with a helpful error message."""
        with self.assertRaises(file_refactor.FileRefactorError) as ctx:
            file_refactor.prepare_file_rename(
                str(self.root), "res://icon.svg.import", "res://icon2.svg.import"
            )
        self.assertIn("Не следует переименовывать файл .import напрямую", str(ctx.exception))

        # Create dummy .uid
        (self.root / "dummy.gd").write_text("extends Node\n", encoding="utf-8")
        (self.root / "dummy.gd.uid").write_text("uid://dummy123\n", encoding="utf-8")

        with self.assertRaises(file_refactor.FileRefactorError) as ctx:
            file_refactor.prepare_file_rename(
                str(self.root), "res://dummy.gd.uid", "res://dummy2.gd.uid"
            )
        self.assertIn("Не следует переименовывать файл .uid напрямую", str(ctx.exception))

    def test_destination_import_collision_rejected(self):
        """If destination .import already exists, FileExistsError is raised before modifying anything."""
        # Create orphaned hero.png.import at destination
        (self.root / "textures" / "hero.png.import").write_text("stale", encoding="utf-8")

        with self.assertRaises(FileExistsError) as ctx:
            file_refactor.prepare_file_rename(
                str(self.root), "res://textures/player.png", "res://textures/hero.png"
            )
        self.assertIn("Целевой файл .import уже существует", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
