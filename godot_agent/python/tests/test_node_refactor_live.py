# -*- coding: utf-8 -*-
"""Live engine verification of Safe Node Rename using real Godot 4 executable."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import node_refactor
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


class TestNodeRefactorLive(unittest.TestCase):
    def setUp(self):
        self.godot_bin = find_godot_executable()
        if not self.godot_bin or not os.path.isfile(self.godot_bin):
            self.skipTest("Godot executable not found for live testing")

        self.test_dir = tempfile.mkdtemp(prefix="godot_node_refactor_live_")

        # 1. project.godot
        project_godot_content = (
            '; Engine configuration file.\n'
            'config_version=5\n\n'
            '[application]\n'
            'config/name="LiveNodeRefactorTest"\n'
            'config/features=PackedStringArray("4.6")\n'
            'run/main_scene="res://main.tscn"\n'
        )
        with open(os.path.join(self.test_dir, "project.godot"), "w", encoding="utf-8") as f:
            f.write(project_godot_content)

        # 2. res://player.gd
        self.player_gd_content = """class_name LivePlayer
extends CharacterBody2D

@onready var gun = $Gun
@onready var muzzle = $"Gun/Muzzle"
@onready var unique_gun = %Gun

func _ready() -> void:
\tvar g = get_node("Gun")
\tvar m = get_node("Gun/Muzzle")
\tvar c = find_child("Gun")
\tprint("LivePlayer ready: ", gun != null, muzzle != null, unique_gun != null, g != null, m != null, c != null)

func _on_gun_ready() -> void:
\tprint("Gun ready signal received!")
"""
        with open(os.path.join(self.test_dir, "player.gd"), "w", encoding="utf-8") as f:
            f.write(self.player_gd_content)

        # 3. res://main.tscn
        self.main_tscn_content = """[gd_scene load_steps=4 format=3]

[ext_resource type="Script" path="res://player.gd" id="1_player"]

[sub_resource type="Animation" id="Animation_shoot"]
resource_name = "shoot"
length = 0.5
tracks/0/type = "value"
tracks/0/imported = false
tracks/0/enabled = true
tracks/0/path = NodePath("Gun/Muzzle:position")
tracks/0/interp = 1
tracks/0/loop_wrap = true
tracks/0/keys = {
"times": PackedFloat32Array(0),
"transitions": PackedFloat32Array(1),
"update": 0,
"values": [Vector2(10, 0)]
}
tracks/1/type = "value"
tracks/1/imported = false
tracks/1/enabled = true
tracks/1/path = NodePath("Gun:rotation")
tracks/1/interp = 1
tracks/1/loop_wrap = true
tracks/1/keys = {
"times": PackedFloat32Array(0),
"transitions": PackedFloat32Array(1),
"update": 0,
"values": [0.0]
}

[sub_resource type="AnimationLibrary" id="AnimationLibrary_main"]
_data = {
"shoot": SubResource("Animation_shoot")
}

[node name="Player" type="CharacterBody2D"]
script = ExtResource("1_player")

[node name="Gun" type="Node2D" parent="."]
unique_name_in_owner = true

[node name="Muzzle" type="Marker2D" parent="Gun"]

[node name="AnimationPlayer" type="AnimationPlayer" parent="."]
libraries = {
"": SubResource("AnimationLibrary_main")
}

[connection signal="ready" from="Gun" to="." method="_on_gun_ready"]
"""
        with open(os.path.join(self.test_dir, "main.tscn"), "w", encoding="utf-8") as f:
            f.write(self.main_tscn_content)

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

    def test_live_node_rename_and_engine_validation(self):
        # Step 1: Initial import by real Godot
        res1 = self._run_godot_headless()
        self.assertEqual(res1.returncode, 0, "Initial Godot import failed: %s\n%s" % (res1.stdout, res1.stderr))

        # Step 2: Prepare node rename: Gun -> Rifle
        prep = node_refactor.prepare_node_rename(
            self.test_dir, "res://main.tscn", "Gun", "Rifle"
        )
        self.assertEqual(prep["new_name"], "Rifle")
        self.assertEqual(len(prep["files"]), 2)  # main.tscn and player.gd

        # Step 3: Apply node rename
        result = node_refactor.apply_prepared_node_rename(
            self.test_dir, prep, chat_id="live_node_test", chat_title="Live Node Test"
        )
        self.assertTrue(result["entry_id"])

        # Step 4: Verify on disk
        with open(os.path.join(self.test_dir, "main.tscn"), "r", encoding="utf-8") as f:
            tscn_text = f.read()

        self.assertIn('[node name="Rifle" type="Node2D" parent="."]', tscn_text)
        self.assertIn('parent="Rifle"', tscn_text)
        self.assertIn('from="Rifle"', tscn_text)
        self.assertIn('NodePath("Rifle/Muzzle:position")', tscn_text)
        self.assertIn('NodePath("Rifle:rotation")', tscn_text)
        self.assertNotIn('[node name="Gun"', tscn_text)

        with open(os.path.join(self.test_dir, "player.gd"), "r", encoding="utf-8") as f:
            gd_text = f.read()

        self.assertIn('@onready var gun = $Rifle', gd_text)
        self.assertIn('@onready var muzzle = $"Rifle/Muzzle"', gd_text)
        self.assertIn('@onready var unique_gun = %Rifle', gd_text)
        self.assertIn('get_node("Rifle")', gd_text)
        self.assertIn('get_node("Rifle/Muzzle")', gd_text)
        self.assertIn('find_child("Rifle")', gd_text)
        self.assertNotIn('$Gun', gd_text)
        self.assertNotIn('%Gun', gd_text)

        # Step 5: Validate with real Godot in headless editor mode!
        res2 = self._run_godot_headless()
        self.assertEqual(res2.returncode, 0, "Godot failed on renamed node scene: %s\n%s" % (res2.stdout, res2.stderr))
        output2 = (res2.stdout + res2.stderr).lower()
        self.assertNotIn("cannot load source code", output2)
        self.assertNotIn("parser error", output2)
        self.assertNotIn("node not found", output2)

        # Step 6: Test rollback with history_manager
        rb_res = history_manager.rollback_last(self.test_dir)
        self.assertTrue(rb_res[0], "Rollback failed: %s" % (rb_res,))

        # Step 7: Verify files are restored
        with open(os.path.join(self.test_dir, "main.tscn"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), self.main_tscn_content)

        with open(os.path.join(self.test_dir, "player.gd"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), self.player_gd_content)

        # Step 8: Validate restored project with real Godot
        res3 = self._run_godot_headless()
        self.assertEqual(res3.returncode, 0, "Godot failed on rolled-back project: %s\n%s" % (res3.stdout, res3.stderr))

        print("PASS: Live engine verification of node rename and rollback with Godot passed!")

    def test_live_node_reparent_and_deletion_validation(self):
        # 1. Add Arm node to main.tscn
        arm_node = '[node name="Arm" type="Node2D" parent="."]\n\n'
        with open(os.path.join(self.test_dir, "main.tscn"), "r", encoding="utf-8") as f:
            cur_tscn = f.read()
        with open(os.path.join(self.test_dir, "main.tscn"), "w", encoding="utf-8") as f:
            f.write(cur_tscn.replace('[node name="Gun"', arm_node + '[node name="Gun"'))

        # Verify initial import with Godot
        res1 = self._run_godot_headless()
        self.assertEqual(res1.returncode, 0, "Godot failed initial import: %s\n%s" % (res1.stdout, res1.stderr))

        # 2. Prepare reparent: Gun -> Arm
        prep_rep = node_refactor.prepare_node_reparent(
            self.test_dir, "res://main.tscn", "Gun", "Arm", update_scripts=True
        )
        self.assertEqual(prep_rep["new_path"], "Arm/Gun")

        # Apply reparent
        res_rep = node_refactor.apply_prepared_node_reparent(
            self.test_dir, prep_rep, chat_id="live_reparent", chat_title="Live Reparent"
        )
        self.assertTrue(res_rep["entry_id"])

        # Validate with real Godot in headless editor mode
        res_godot_rep = self._run_godot_headless()
        self.assertEqual(res_godot_rep.returncode, 0, "Godot failed on reparented scene: %s\n%s" % (
            res_godot_rep.stdout, res_godot_rep.stderr))
        output_rep = (res_godot_rep.stdout + res_godot_rep.stderr).lower()
        self.assertNotIn("parser error", output_rep)
        self.assertNotIn("cannot load source code", output_rep)

        # Rollback reparent
        rb_rep = history_manager.rollback_last(self.test_dir)
        self.assertTrue(rb_rep[0], "Rollback reparent failed: %s" % (rb_rep,))

        # 3. Prepare deletion: delete Gun and its children
        prep_del = node_refactor.prepare_node_deletion(
            self.test_dir, "res://main.tscn", "Gun", cleanup_code=True
        )
        self.assertEqual(prep_del["action"], "delete_node")

        # Apply deletion
        res_del = node_refactor.apply_prepared_node_deletion(
            self.test_dir, prep_del, chat_id="live_delete", chat_title="Live Delete"
        )
        self.assertTrue(res_del["entry_id"])

        # Validate with real Godot in headless editor mode
        res_godot_del = self._run_godot_headless()
        self.assertEqual(res_godot_del.returncode, 0, "Godot failed on scene after node deletion: %s\n%s" % (
            res_godot_del.stdout, res_godot_del.stderr))
        output_del = (res_godot_del.stdout + res_godot_del.stderr).lower()
        self.assertNotIn("parser error", output_del)
        self.assertNotIn("cannot load source code", output_del)

        # Rollback deletion
        rb_del = history_manager.rollback_last(self.test_dir)
        self.assertTrue(rb_del[0], "Rollback deletion failed: %s" % (rb_del,))

        # Final validate with real Godot
        res_final = self._run_godot_headless()
        self.assertEqual(res_final.returncode, 0, "Godot failed after final rollback: %s\n%s" % (
            res_final.stdout, res_final.stderr))

        print("PASS: Live engine verification of node reparent, deletion, and rollback with Godot passed!")



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", help="Path to Godot executable")
    args, unknown = parser.parse_known_args()
    if args.godot:
        os.environ["GODOT_EXECUTABLE"] = args.godot
    unittest.main(argv=[sys.argv[0]] + unknown)
