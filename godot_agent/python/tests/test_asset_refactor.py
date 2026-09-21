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

    def test_sync_references_after_external_move_updates_code_and_supports_rollback(self):
        """When Godot's FileSystemDock renames an enemy scene on disk, sync_references_after_external_move updates references in scripts and supports rollback."""
        enemies_dir = self.root / "scenes" / "enemies"
        enemies_dir.mkdir(parents=True, exist_ok=True)
        goblin_scene = enemies_dir / "goblin.tscn"
        goblin_scene.write_text('[gd_scene format=3]\n[node name="Goblin" type="CharacterBody2D"]\n', encoding="utf-8")

        data_reg = self.root / "scripts" / "data_registry.gd"
        data_reg.write_text(
            'extends RefCounted\n\n'
            'const ENEMIES = {\n'
            '    "goblin": {\n'
            '        "name": "Гоблин",\n'
            '        "scene": "res://scenes/enemies/goblin.tscn"\n'
            '    }\n'
            '}\n',
            encoding="utf-8"
        )

        # Simulate Godot's external rename on disk
        rat_scene = enemies_dir / "rat.tscn"
        goblin_scene.rename(rat_scene)
        self.assertTrue(rat_scene.exists())
        self.assertFalse(goblin_scene.exists())

        # Call post-move sync
        res = file_refactor.sync_references_after_external_move(
            str(self.root),
            "res://scenes/enemies/goblin.tscn",
            "res://scenes/enemies/rat.tscn"
        )
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("reference_count"), 1)
        self.assertIn("res://scripts/data_registry.gd", res.get("changed_paths", []))

        # Verify data_registry.gd updated with rat.tscn
        reg_text = data_reg.read_text(encoding="utf-8")
        self.assertIn('"scene": "res://scenes/enemies/rat.tscn"', reg_text)
        self.assertNotIn('goblin.tscn', reg_text)

        # Test rollback
        ok, msg, needs_force, paths, diff = history_manager.rollback_last(str(self.root))
        self.assertTrue(ok, msg)

        # References in code restored to goblin.tscn
        restored_reg_text = data_reg.read_text(encoding="utf-8")
        self.assertIn('"scene": "res://scenes/enemies/goblin.tscn"', restored_reg_text)

    def test_sync_references_after_external_directory_move(self):
        """When a directory is moved externally, sync_references_after_external_move updates references across files."""
        items_dir = self.root / "items"
        items_dir.mkdir(parents=True, exist_ok=True)
        sword_gd = items_dir / "sword.gd"
        sword_gd.write_text('extends Node2D\n', encoding="utf-8")
        sword_scene = items_dir / "sword.tscn"
        sword_scene.write_text(
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource type="Script" path="res://items/sword.gd" id="1_abc"]\n'
            '[node name="Sword" type="Node2D"]\n',
            encoding="utf-8"
        )

        spawner_gd = self.root / "scripts" / "spawner.gd"
        spawner_gd.write_text(
            'extends Node\n'
            'const ITEMS_STORAGE = "res://items"\n'
            'const ITEMS_PATH = "res://items/"\n'
            'var item = preload("res://items/sword.tscn")\n',
            encoding="utf-8"
        )

        # Move directory externally on disk
        loot_dir = self.root / "loot"
        items_dir.rename(loot_dir)

        res = file_refactor.sync_references_after_external_move(
            str(self.root),
            "res://items",
            "res://loot",
            is_directory=True
        )
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("reference_count"), 4)
        self.assertIn("res://scripts/spawner.gd", res.get("changed_paths", []))
        self.assertIn("res://loot/sword.tscn", res.get("changed_paths", []))

        spawner_text = spawner_gd.read_text(encoding="utf-8")
        self.assertIn('const ITEMS_STORAGE = "res://loot"', spawner_text)
        self.assertIn('const ITEMS_PATH = "res://loot/"', spawner_text)
        self.assertIn('preload("res://loot/sword.tscn")', spawner_text)

        loot_sword_tscn = (loot_dir / "sword.tscn").read_text(encoding="utf-8")
        self.assertIn('path="res://loot/sword.gd"', loot_sword_tscn)

    def test_sync_references_after_external_script_rename(self):
        """When an enemy script is renamed externally, references in scenes are updated."""
        scripts_dir = self.root / "scripts" / "enemies"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        goblin_gd = scripts_dir / "goblin.gd"
        goblin_gd.write_text('extends CharacterBody2D\n', encoding="utf-8")

        scenes_dir = self.root / "scenes" / "enemies"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        enemy_tscn = scenes_dir / "enemy.tscn"
        enemy_tscn.write_text(
            '[gd_scene format=3]\n'
            '[ext_resource type="Script" path="res://scripts/enemies/goblin.gd" id="1_abc"]\n',
            encoding="utf-8"
        )

        rat_gd = scripts_dir / "rat.gd"
        goblin_gd.rename(rat_gd)

        res = file_refactor.sync_references_after_external_move(
            str(self.root),
            "res://scripts/enemies/goblin.gd",
            "res://scripts/enemies/rat.gd"
        )
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("reference_count"), 1)
        self.assertIn("res://scenes/enemies/enemy.tscn", res.get("changed_paths", []))

        updated_tscn = enemy_tscn.read_text(encoding="utf-8")
        self.assertIn('path="res://scripts/enemies/rat.gd"', updated_tscn)

    def test_sync_references_zero_references_returns_clean_result(self):
        """Renaming a file with no project references returns ok=True and empty changed_paths."""
        misc_dir = self.root / "misc"
        misc_dir.mkdir(parents=True, exist_ok=True)
        old_file = misc_dir / "temp1.txt"
        new_file = misc_dir / "temp2.txt"
        old_file.write_text('hello\n', encoding="utf-8")
        old_file.rename(new_file)

        res = file_refactor.sync_references_after_external_move(
            str(self.root),
            "res://misc/temp1.txt",
            "res://misc/temp2.txt"
        )
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("reference_count"), 0)
        self.assertEqual(res.get("changed_paths"), [])

    def test_synthetic_folder_as_storage_repository_with_similar_names_and_rollback(self):
        """Synthetic test: Directory relocation where folder is used as a repository/storage
        with dynamic paths, DirAccess, multiple files, sibling folders with similar prefixes,
        and full history rollback.
        """
        enemies_dir = self.root / "enemies"
        enemies_dir.mkdir(parents=True, exist_ok=True)

        # 1. Goblin scene & script inside enemies
        (enemies_dir / "goblin.gd").write_text(
            'extends CharacterBody2D\n'
            'const ORC_PREFAB = preload("res://enemies/orc.tscn")\n'
            'func get_type():\n'
            '    return "goblin"\n',
            encoding="utf-8"
        )
        (enemies_dir / "goblin.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource type="Script" path="res://enemies/goblin.gd" id="1_gob"]\n'
            '[node name="Goblin" type="CharacterBody2D"]\n'
            'script = ExtResource("1_gob")\n',
            encoding="utf-8"
        )

        # 2. Orc scene & script inside enemies
        (enemies_dir / "orc.gd").write_text(
            'extends CharacterBody2D\n'
            'func get_type():\n'
            '    return "orc"\n',
            encoding="utf-8"
        )
        (enemies_dir / "orc.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource type="Script" path="res://enemies/orc.gd" id="1_orc"]\n'
            '[node name="Orc" type="CharacterBody2D"]\n'
            'script = ExtResource("1_orc")\n',
            encoding="utf-8"
        )

        # 3. Sibling folder with similar prefix: res://enemies_bosses (MUST NOT BE TOUCHED!)
        bosses_dir = self.root / "enemies_bosses"
        bosses_dir.mkdir(parents=True, exist_ok=True)
        (bosses_dir / "dragon.gd").write_text('extends CharacterBody2D\n', encoding="utf-8")
        (bosses_dir / "dragon.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource type="Script" path="res://enemies_bosses/dragon.gd" id="1_drag"]\n'
            '[node name="Dragon" type="CharacterBody2D"]\n'
            'script = ExtResource("1_drag")\n',
            encoding="utf-8"
        )

        # 4. Spawner GDScript acting as repository consumer
        spawner_gd = self.root / "scripts" / "spawner.gd"
        spawner_orig_text = (
            'extends Node\n\n'
            'const ENEMIES_DIR = "res://enemies"\n'
            'const ENEMIES_PATH = "res://enemies/"\n'
            'const BOSS_SCENE = preload("res://enemies_bosses/dragon.tscn")\n\n'
            'func spawn_random(enemy_name: String):\n'
            '    var dir = DirAccess.open("res://enemies")\n'
            '    var scene = load("res://enemies/" + enemy_name + ".tscn")\n'
            '    return scene.instantiate()\n'
        )
        spawner_gd.write_text(spawner_orig_text, encoding="utf-8")

        # 5. Prepare and execute relocation: res://enemies -> res://entities/enemies
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://enemies", "res://entities/enemies", update_references=True
        )
        self.assertTrue(prep.get("is_directory"))
        res = file_refactor.apply_prepared_file_rename(str(self.root), prep)
        self.assertTrue(res.get("file_count") > 0)

        # --- VERIFY RELOCATION ---
        # Old folder removed, new folder exists with all assets
        self.assertFalse((self.root / "enemies").exists())
        self.assertTrue((self.root / "entities" / "enemies" / "goblin.tscn").exists())
        self.assertTrue((self.root / "entities" / "enemies" / "goblin.gd").exists())
        self.assertTrue((self.root / "entities" / "enemies" / "orc.tscn").exists())
        self.assertTrue((self.root / "entities" / "enemies" / "orc.gd").exists())

        # Internal references inside moved scenes and scripts
        new_goblin_tscn = (self.root / "entities" / "enemies" / "goblin.tscn").read_text(encoding="utf-8")
        self.assertIn('path="res://entities/enemies/goblin.gd"', new_goblin_tscn)

        new_goblin_gd = (self.root / "entities" / "enemies" / "goblin.gd").read_text(encoding="utf-8")
        self.assertIn('preload("res://entities/enemies/orc.tscn")', new_goblin_gd)

        # External script (storage paths + preload)
        new_spawner_text = spawner_gd.read_text(encoding="utf-8")
        self.assertIn('const ENEMIES_DIR = "res://entities/enemies"', new_spawner_text)
        self.assertIn('const ENEMIES_PATH = "res://entities/enemies/"', new_spawner_text)
        self.assertIn('DirAccess.open("res://entities/enemies")', new_spawner_text)
        self.assertIn('load("res://entities/enemies/" + enemy_name + ".tscn")', new_spawner_text)
        # Sibling res://enemies_bosses MUST NOT be modified!
        self.assertIn('preload("res://enemies_bosses/dragon.tscn")', new_spawner_text)

        # Sibling folder files MUST NOT be modified!
        boss_dragon_tscn = (bosses_dir / "dragon.tscn").read_text(encoding="utf-8")
        self.assertIn('path="res://enemies_bosses/dragon.gd"', boss_dragon_tscn)

        # --- ROLLBACK VERIFICATION ---
        ok, msg, _, _, _ = history_manager.rollback_last(str(self.root))
        self.assertTrue(ok, msg)

        # Old folder restored, new folder removed
        self.assertTrue((self.root / "enemies" / "goblin.tscn").exists())
        self.assertTrue((self.root / "enemies" / "goblin.gd").exists())
        self.assertTrue((self.root / "enemies" / "orc.tscn").exists())
        self.assertTrue((self.root / "enemies" / "orc.gd").exists())
        self.assertFalse((self.root / "entities" / "enemies").exists())

        # Restored contents match exact original
        self.assertEqual(spawner_gd.read_text(encoding="utf-8"), spawner_orig_text)
        restored_goblin_tscn = (self.root / "enemies" / "goblin.tscn").read_text(encoding="utf-8")
        self.assertIn('path="res://enemies/goblin.gd"', restored_goblin_tscn)

    def test_synthetic_external_folder_move_storage_sync_and_rollback(self):
        """Synthetic test: Simulating Godot editor drag-and-drop moving a folder containing
        assets and dynamic storage folder references, followed by reference synchronization and rollback.
        """
        import shutil

        enemies_dir = self.root / "enemies"
        enemies_dir.mkdir(parents=True, exist_ok=True)

        (enemies_dir / "slime.gd").write_text('extends CharacterBody2D\n', encoding="utf-8")
        (enemies_dir / "slime.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource type="Script" path="res://enemies/slime.gd" id="1_sli"]\n'
            '[node name="Slime" type="CharacterBody2D"]\n',
            encoding="utf-8"
        )

        # Sibling folder to guard against prefix matching bugs
        bosses_dir = self.root / "enemies_elite"
        bosses_dir.mkdir(parents=True, exist_ok=True)
        (bosses_dir / "golem.tscn").write_text('[gd_scene format=3]\n', encoding="utf-8")

        game_mgr = self.root / "scripts" / "game_mgr.gd"
        game_mgr_orig = (
            'extends Node\n\n'
            'const REPO = "res://enemies"\n'
            'const REPO_SLASH = "res://enemies/"\n'
            'const ELITE = preload("res://enemies_elite/golem.tscn")\n\n'
            'func load_monster(m_name: String):\n'
            '    var d = DirAccess.open("res://enemies")\n'
            '    return load("res://enemies/" + m_name + ".tscn")\n'
        )
        game_mgr.write_text(game_mgr_orig, encoding="utf-8")

        # Simulate Godot editor drag & drop: folder moved on disk from res://enemies to res://actors/monsters
        dest_dir = self.root / "actors" / "monsters"
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(enemies_dir), str(dest_dir))

        # Safe rename handler runs sync_references_after_external_move
        res = file_refactor.sync_references_after_external_move(
            str(self.root),
            "res://enemies",
            "res://actors/monsters",
            is_directory=True
        )
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("reference_count"), 5)  # REPO, REPO_SLASH, DirAccess, load, slime.tscn script path
        self.assertIn("res://scripts/game_mgr.gd", res.get("changed_paths", []))
        self.assertIn("res://actors/monsters/slime.tscn", res.get("changed_paths", []))

        # Check updated script
        updated_mgr = game_mgr.read_text(encoding="utf-8")
        self.assertIn('const REPO = "res://actors/monsters"', updated_mgr)
        self.assertIn('const REPO_SLASH = "res://actors/monsters/"', updated_mgr)
        self.assertIn('DirAccess.open("res://actors/monsters")', updated_mgr)
        self.assertIn('return load("res://actors/monsters/" + m_name + ".tscn")', updated_mgr)
        # Sibling elite golem must remain untouched
        self.assertIn('const ELITE = preload("res://enemies_elite/golem.tscn")', updated_mgr)

        # Check internal scene inside moved directory
        updated_slime_tscn = (dest_dir / "slime.tscn").read_text(encoding="utf-8")
        self.assertIn('path="res://actors/monsters/slime.gd"', updated_slime_tscn)

        # Rollback synchronized code references AND the moved tree itself (audit 1.1)
        ok, msg, _, _, _ = history_manager.rollback_last(str(self.root))
        self.assertTrue(ok, msg)

        # game_mgr.gd restored to res://enemies
        self.assertEqual(game_mgr.read_text(encoding="utf-8"), game_mgr_orig)
        # slime.tscn moved back with the tree and restored to res://enemies
        self.assertFalse(dest_dir.exists())
        restored_slime = (self.root / "enemies" / "slime.tscn").read_text(encoding="utf-8")
        self.assertIn('path="res://enemies/slime.gd"', restored_slime)


if __name__ == "__main__":
    unittest.main()


