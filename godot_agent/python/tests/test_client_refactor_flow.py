# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import main
from godot_tools import history_manager, node_refactor, file_refactor


class TestClientRefactorFlow(unittest.TestCase):
    """Simulates the Godot editor plugin client (agent_panel.gd) interacting
    with the Flask backend for all refactoring actions:
    - Safe File / Directory Relocation
    - Safe Node Rename
    - Safe Node Reparent
    - Safe Node Deletion (with warning inspection)
    - Chat Confirmation flow
    - 1-Click Rollback
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agent_client_refactor_")
        self.root = Path(self.test_dir)
        main.STATE["project_root"] = str(self.root)
        main.STATE["addon_intent"] = False
        self.client = main.app.test_client()

        # Create Godot project structure
        (self.root / "project.godot").write_text('[application]\nconfig/name="ClientRefactorTest"\n', encoding="utf-8")
        (self.root / "scenes").mkdir(parents=True, exist_ok=True)
        (self.root / "scripts").mkdir(parents=True, exist_ok=True)

        self.scene_path = self.root / "scenes" / "player.tscn"
        self.script_path = self.root / "scripts" / "player.gd"

        self.script_content = (
            'class_name TestPlayer\n'
            'extends CharacterBody2D\n\n'
            '@onready var gun = $Gun\n'
            '@onready var muzzle = $"Gun/Muzzle"\n'
            '@onready var unique_gun = %Gun\n\n'
            'func _ready():\n'
            '\tvar g = get_node("Gun")\n'
            '\tvar m = get_node_or_null("Gun/Muzzle")\n'
            '\tvar f = find_child("Gun")\n'
        )
        self.script_path.write_text(self.script_content, encoding="utf-8")

        self.scene_content = (
            '[gd_scene load_steps=2 format=3]\n\n'
            '[ext_resource type="Script" path="res://scripts/player.gd" id="1_scr"]\n\n'
            '[node name="Player" type="CharacterBody2D"]\n'
            'script = ExtResource("1_scr")\n\n'
            '[node name="Gun" type="Node2D" parent="."]\n'
            'unique_name_in_owner = true\n\n'
            '[node name="Muzzle" type="Marker2D" parent="Gun"]\n\n'
            '[connection signal="ready" from="Gun" to="." method="_on_gun_ready"]\n'
        )
        self.scene_path.write_text(self.scene_content, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_client_file_relocation_and_rollback(self):
        # 1. Preview file move
        resp = self.client.post("/project/refactor/file/preview", json={
            "old_path": "res://scripts/player.gd",
            "new_path": "res://scripts/actors/player.gd",
            "update_references": True,
            "project_root": str(self.root)
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["prepared"]["new_path"], "res://scripts/actors/player.gd")

        # 2. Apply file move
        resp2 = self.client.post("/project/refactor/file/apply", json={
            "old_path": "res://scripts/player.gd",
            "new_path": "res://scripts/actors/player.gd",
            "update_references": True,
            "project_root": str(self.root)
        })
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2["ok"])

        # Check on disk
        self.assertFalse(self.script_path.exists())
        new_script_path = self.root / "scripts" / "actors" / "player.gd"
        self.assertTrue(new_script_path.exists())

        # Check scene reference updated
        tscn_text = self.scene_path.read_text(encoding="utf-8")
        self.assertIn('path="res://scripts/actors/player.gd"', tscn_text)

        # 3. Rollback
        resp_rb = self.client.post("/chat/rollback", json={})
        self.assertEqual(resp_rb.status_code, 200)
        self.assertTrue(resp_rb.get_json()["success"])

        self.assertTrue(self.script_path.exists())
        self.assertFalse(new_script_path.exists())
        self.assertIn('path="res://scripts/player.gd"', self.scene_path.read_text(encoding="utf-8"))

    def test_client_node_rename_and_rollback(self):
        # 1. Preview
        resp = self.client.post("/scene/refactor/node/preview", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "new_name": "Rifle",
            "project_root": str(self.root)
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["prepared"]["new_name"], "Rifle")

        # 2. Apply
        resp2 = self.client.post("/scene/refactor/node/apply", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "new_name": "Rifle",
            "project_root": str(self.root)
        })
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2["ok"])

        # Verify on disk
        tscn_text = self.scene_path.read_text(encoding="utf-8")
        self.assertIn('[node name="Rifle" type="Node2D" parent="."]', tscn_text)
        self.assertIn('parent="Rifle"', tscn_text)
        self.assertIn('from="Rifle"', tscn_text)

        gd_text = self.script_path.read_text(encoding="utf-8")
        self.assertIn('$Rifle', gd_text)
        self.assertIn('$"Rifle/Muzzle"', gd_text)
        self.assertIn('%Rifle', gd_text)
        self.assertIn('get_node("Rifle")', gd_text)

        # 3. Rollback
        resp_rb = self.client.post("/chat/rollback", json={})
        self.assertEqual(resp_rb.status_code, 200)
        self.assertTrue(resp_rb.get_json()["success"])

        self.assertIn('[node name="Gun" type="Node2D" parent="."]', self.scene_path.read_text(encoding="utf-8"))
        self.assertIn('$Gun', self.script_path.read_text(encoding="utf-8"))

    def test_client_node_reparent_and_rollback(self):
        # Add Arm node to scene
        cur_tscn = self.scene_path.read_text(encoding="utf-8")
        arm_node = '[node name="Arm" type="Node2D" parent="."]\n\n'
        self.scene_path.write_text(cur_tscn.replace('[node name="Gun"', arm_node + '[node name="Gun"'), encoding="utf-8")

        # 1. Preview
        resp = self.client.post("/scene/refactor/node/reparent/preview", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "new_parent": "Arm",
            "project_root": str(self.root)
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["prepared"]["new_path"], "Arm/Gun")

        # 2. Apply
        resp2 = self.client.post("/scene/refactor/node/reparent/apply", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "new_parent": "Arm",
            "project_root": str(self.root)
        })
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2["ok"])

        # Verify on disk
        tscn_text = self.scene_path.read_text(encoding="utf-8")
        self.assertIn('[node name="Gun" type="Node2D" parent="Arm"]', tscn_text)
        self.assertIn('parent="Arm/Gun"', tscn_text)
        self.assertIn('from="Arm/Gun"', tscn_text)

        gd_text = self.script_path.read_text(encoding="utf-8")
        self.assertIn('$Arm/Gun', gd_text)
        self.assertIn('$"Arm/Gun/Muzzle"', gd_text)

        # 3. Rollback
        resp_rb = self.client.post("/chat/rollback", json={})
        self.assertEqual(resp_rb.status_code, 200)
        self.assertTrue(resp_rb.get_json()["success"])

        self.assertIn('[node name="Gun" type="Node2D" parent="."]', self.scene_path.read_text(encoding="utf-8"))
        self.assertIn('$Gun', self.script_path.read_text(encoding="utf-8"))

    def test_client_node_deletion_and_rollback(self):
        # 1. Preview
        resp = self.client.post("/scene/refactor/node/delete/preview", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "cleanup_code": True,
            "project_root": str(self.root)
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("Gun", data["prepared"]["deleted_nodes"])
        self.assertIn("Gun/Muzzle", data["prepared"]["deleted_nodes"])
        # Warnings should record script references
        warnings = data["prepared"]["warnings"]
        self.assertGreater(len(warnings), 0)
        self.assertTrue(any("gun = $Gun" in w["code"] for w in warnings))

        # 2. Apply
        resp2 = self.client.post("/scene/refactor/node/delete/apply", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "cleanup_code": True,
            "project_root": str(self.root)
        })
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2["ok"])
        self.assertGreater(len(data2["warnings"]), 0)

        # Verify on disk: scene has node removed, script is UNTOUCHED
        tscn_text = self.scene_path.read_text(encoding="utf-8")
        self.assertNotIn('[node name="Gun"', tscn_text)
        self.assertNotIn('[node name="Muzzle"', tscn_text)
        self.assertNotIn('from="Gun"', tscn_text)

        gd_text = self.script_path.read_text(encoding="utf-8")
        self.assertEqual(gd_text, self.script_content)

        # 3. Rollback
        resp_rb = self.client.post("/chat/rollback", json={})
        self.assertEqual(resp_rb.status_code, 200)
        self.assertTrue(resp_rb.get_json()["success"])

        self.assertIn('[node name="Gun" type="Node2D" parent="."]', self.scene_path.read_text(encoding="utf-8"))
        self.assertIn('[node name="Muzzle" type="Marker2D" parent="Gun"]', self.scene_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
