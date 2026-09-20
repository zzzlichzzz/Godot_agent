# -*- coding: utf-8 -*-
"""Live engine verification of Safe File Rename using real Godot 4 executable."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import file_refactor
import history_manager


def find_godot_executable():
    env_path = os.environ.get("GODOT_EXECUTABLE")
    if env_path and os.path.isfile(env_path):
        return env_path
    candidates = [
        r"D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe",
        r"D:\vajno\Godot\Godot v4.6\Godot_v4.6-stable_win64_console.exe",
        r"D:\vajno\Godot\Godot v4.5.1\Godot_v4.5.1-stable_win64_console.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return shutil.which("godot")


class TestFileRefactorLive(unittest.TestCase):
    def setUp(self):
        self.godot_bin = find_godot_executable()
        if not self.godot_bin or not os.path.isfile(self.godot_bin):
            self.skipTest("Godot executable not found for live testing")

        self.test_dir = tempfile.mkdtemp(prefix="godot_refactor_live_")

        # 1. project.godot
        project_godot_content = (
            '; Engine configuration file.\n'
            'config_version=5\n\n'
            '[application]\n'
            'config/name="LiveRefactorTest"\n'
            'config/features=PackedStringArray("4.6")\n\n'
            '[autoload]\n'
            'PlayerService="*res://player.gd"\n'
        )
        with open(os.path.join(self.test_dir, "project.godot"), "w", encoding="utf-8") as f:
            f.write(project_godot_content)

        # 2. res://player.gd
        player_gd_content = (
            'class_name LivePlayer\n'
            'extends Node\n\n'
            'signal health_changed(new_hp: int)\n\n'
            'var hp: int = 100\n\n'
            'func take_damage(amount: int) -> void:\n'
            '    hp -= amount\n'
            '    health_changed.emit(hp)\n'
        )
        with open(os.path.join(self.test_dir, "player.gd"), "w", encoding="utf-8") as f:
            f.write(player_gd_content)

        # 3. res://weapon.gd (references player.gd via absolute and relative preload)
        weapon_gd_content = (
            'extends Node\n\n'
            'const PlayerAbs = preload("res://player.gd")\n'
            'const PlayerRel = preload("player.gd")\n\n'
            'func attack(target: Node) -> void:\n'
            '    if target is PlayerAbs:\n'
            '        target.take_damage(10)\n'
        )
        with open(os.path.join(self.test_dir, "weapon.gd"), "w", encoding="utf-8") as f:
            f.write(weapon_gd_content)

        # 4. res://main.tscn (scene referencing player.gd)
        main_tscn_content = (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://player.gd" id="1_player"]\n\n'
            '[node name="Main" type="Node"]\n'
            'script = ExtResource("1_player")\n'
        )
        with open(os.path.join(self.test_dir, "main.tscn"), "w", encoding="utf-8") as f:
            f.write(main_tscn_content)

        # 5. res://data.tres (resource referencing player.gd)
        data_tres_content = (
            '[gd_resource type="Resource" load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://player.gd" id="1_player"]\n\n'
            '[resource]\n'
            'script = ExtResource("1_player")\n'
        )
        with open(os.path.join(self.test_dir, "data.tres"), "w", encoding="utf-8") as f:
            f.write(data_tres_content)

    def tearDown(self):
        if os.path.isdir(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _run_godot_headless(self):
        cmd = [self.godot_bin, "--headless", "--editor", "--quit", "--path", self.test_dir]
        result = subprocess.run(
            cmd, cwd=self.test_dir, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60
        )
        return result

    def test_live_rename_and_engine_validation(self):
        # Step 1: Initial import by real Godot
        res1 = self._run_godot_headless()
        self.assertEqual(res1.returncode, 0, "Initial Godot import failed: %s\n%s" % (res1.stdout, res1.stderr))

        # Step 2: Prepare rename from res://player.gd -> res://entities/hero.gd
        old_path = "res://player.gd"
        new_path = "res://entities/hero.gd"
        prep = file_refactor.prepare_file_rename(self.test_dir, old_path, new_path, update_references=True)
        self.assertEqual(prep["reference_count"], 5)  # weapon (2: abs, rel), main.tscn (1), data.tres (1), project.godot (1)

        # Step 3: Apply rename
        result = file_refactor.apply_prepared_file_rename(self.test_dir, prep, chat_id="live_test", chat_title="Live Test")
        self.assertTrue(result["entry_id"])

        # Step 4: Verify on disk
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "player.gd")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "entities", "hero.gd")))

        with open(os.path.join(self.test_dir, "weapon.gd"), "r", encoding="utf-8") as f:
            w_text = f.read()
        self.assertIn('preload("res://entities/hero.gd")', w_text)
        self.assertNotIn('preload("player.gd")', w_text)

        with open(os.path.join(self.test_dir, "main.tscn"), "r", encoding="utf-8") as f:
            t_text = f.read()
        self.assertIn('path="res://entities/hero.gd"', t_text)
        self.assertNotIn('path="res://player.gd"', t_text)

        with open(os.path.join(self.test_dir, "data.tres"), "r", encoding="utf-8") as f:
            d_text = f.read()
        self.assertIn('path="res://entities/hero.gd"', d_text)
        self.assertNotIn('path="res://player.gd"', d_text)

        with open(os.path.join(self.test_dir, "project.godot"), "r", encoding="utf-8") as f:
            p_text = f.read()
        self.assertIn('*res://entities/hero.gd', p_text)
        self.assertNotIn('*res://player.gd', p_text)

        # Step 5: Validate with real Godot in headless editor mode!
        res2 = self._run_godot_headless()
        self.assertEqual(res2.returncode, 0, "Godot failed on renamed project: %s\n%s" % (res2.stdout, res2.stderr))
        # Ensure no ERROR or missing resource logs
        output = (res2.stdout + res2.stderr).lower()
        self.assertNotIn("cannot load source code", output)
        self.assertNotIn("parser error", output)

        # Step 6: Test rollback with history_manager
        rb_res = history_manager.rollback_last(self.test_dir)
        self.assertTrue(rb_res[0], "Rollback failed: %s" % (rb_res,))

        # Step 7: Verify files are restored
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "player.gd")))
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "entities", "hero.gd")))

        with open(os.path.join(self.test_dir, "weapon.gd"), "r", encoding="utf-8") as f:
            w_restored = f.read()
        self.assertIn('preload("res://player.gd")', w_restored)

        with open(os.path.join(self.test_dir, "main.tscn"), "r", encoding="utf-8") as f:
            t_restored = f.read()
        self.assertIn('path="res://player.gd"', t_restored)

        # Step 8: Validate restored project with real Godot!
        res3 = self._run_godot_headless()
        self.assertEqual(res3.returncode, 0, "Godot failed on rolled-back project: %s\n%s" % (res3.stdout, res3.stderr))

        print("PASS: Live engine verification of file rename and rollback with Godot 4.6.3 passed!")

    def test_live_directory_and_relocation_engine_validation(self):
        # 1. Setup a directory with internal scripts and scenes
        combat_path = os.path.join(self.test_dir, "combat")
        os.makedirs(combat_path, exist_ok=True)

        sword_content = (
            'class_name LiveSword\n'
            'extends Node\n\n'
            'const Shield = preload("shield.gd")\n'
            'const AbsShield = preload("res://combat/shield.gd")\n\n'
            'func strike() -> void:\n'
            '    pass\n'
        )
        with open(os.path.join(combat_path, "sword.gd"), "w", encoding="utf-8") as f:
            f.write(sword_content)

        shield_content = (
            'class_name LiveShield\n'
            'extends Node\n'
        )
        with open(os.path.join(combat_path, "shield.gd"), "w", encoding="utf-8") as f:
            f.write(shield_content)

        arena_content = (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://combat/sword.gd" id="1_sword"]\n\n'
            '[node name="Arena" type="Node"]\n'
            'script = ExtResource("1_sword")\n'
        )
        with open(os.path.join(combat_path, "arena.tscn"), "w", encoding="utf-8") as f:
            f.write(arena_content)

        # External reference in weapon.gd
        with open(os.path.join(self.test_dir, "weapon.gd"), "a", encoding="utf-8") as f:
            f.write('\nconst ArenaSword = preload("res://combat/sword.gd")\n')

        # 2. Verify initial Godot headless import
        res1 = self._run_godot_headless()
        self.assertEqual(res1.returncode, 0, "Initial Godot import failed: %s\n%s" % (res1.stdout, res1.stderr))

        # 3. Prepare directory relocation
        old_dir = "res://combat"
        new_dir = "res://systems/battle"
        prep = file_refactor.prepare_file_rename(self.test_dir, old_dir, new_dir, update_references=True)
        self.assertTrue(prep.get("is_directory"))
        self.assertEqual(len(prep["moved_files"]), 3)

        # 4. Apply directory relocation
        result = file_refactor.apply_prepared_file_rename(
            self.test_dir, prep, chat_id="live_test_dir", chat_title="Live Test Dir"
        )
        self.assertTrue(result["entry_id"])

        # Check disk
        self.assertFalse(os.path.exists(combat_path))
        battle_path = os.path.join(self.test_dir, "systems", "battle")
        self.assertTrue(os.path.exists(os.path.join(battle_path, "sword.gd")))
        self.assertTrue(os.path.exists(os.path.join(battle_path, "shield.gd")))
        self.assertTrue(os.path.exists(os.path.join(battle_path, "arena.tscn")))

        with open(os.path.join(self.test_dir, "weapon.gd"), "r", encoding="utf-8") as f:
            w_text = f.read()
        self.assertIn('preload("res://systems/battle/sword.gd")', w_text)
        self.assertNotIn('res://combat/sword.gd', w_text)

        # 5. Validate with real Godot 4.6.3 headless
        res2 = self._run_godot_headless()
        self.assertEqual(res2.returncode, 0, "Godot failed on directory-relocated project: %s\n%s" % (res2.stdout, res2.stderr))
        output2 = (res2.stdout + res2.stderr).lower()
        self.assertNotIn("cannot load source code", output2)
        self.assertNotIn("parser error", output2)

        # 6. Rollback
        rb_res = history_manager.rollback_last(self.test_dir)
        self.assertTrue(rb_res[0], "Directory rollback failed: %s" % (rb_res,))

        # Verify disk restored
        self.assertTrue(os.path.exists(combat_path))
        self.assertTrue(os.path.exists(os.path.join(combat_path, "sword.gd")))
        self.assertTrue(os.path.exists(os.path.join(combat_path, "shield.gd")))
        self.assertTrue(os.path.exists(os.path.join(combat_path, "arena.tscn")))
        self.assertFalse(os.path.exists(battle_path))

        with open(os.path.join(self.test_dir, "weapon.gd"), "r", encoding="utf-8") as f:
            w_restored = f.read()
        self.assertIn('preload("res://combat/sword.gd")', w_restored)

        # 7. Validate restored project with real Godot 4.6.3 headless
        res3 = self._run_godot_headless()
        self.assertEqual(res3.returncode, 0, "Godot failed on rolled-back directory project: %s\n%s" % (res3.stdout, res3.stderr))

        print("PASS: Live engine verification of directory relocation and rollback with Godot 4.6.3 passed!")



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", help="Path to Godot executable")
    args, unknown = parser.parse_known_args()
    if args.godot:
        os.environ["GODOT_EXECUTABLE"] = args.godot
    unittest.main(argv=[sys.argv[0]] + unknown)
