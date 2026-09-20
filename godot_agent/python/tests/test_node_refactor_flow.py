# -*- coding: utf-8 -*-
"""Integration test for node refactor Flask routes, chat action, confirmation, and rollback."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import main
import server_state as S
import history_manager


class NodeRefactorFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="node_refactor_flow_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        (self.root / "project.godot").write_text('config_version=5\n', encoding="utf-8")
        (self.root / "scenes").mkdir(parents=True)
        (self.root / "scripts").mkdir(parents=True)

        self.scene_path = self.root / "scenes" / "player.tscn"
        self.scene_content = """[gd_scene load_steps=3 format=3]

[ext_resource type="Script" path="res://scripts/player.gd" id="1_abc"]

[node name="Player" type="CharacterBody2D"]
script = ExtResource("1_abc")

[node name="Gun" type="Node2D" parent="."]

[node name="Muzzle" type="Marker2D" parent="Gun"]

[connection signal="ready" from="Gun" to="." method="_on_gun_ready"]
"""
        self.scene_path.write_text(self.scene_content, encoding="utf-8")

        self.script_path = self.root / "scripts" / "player.gd"
        self.script_content = """extends CharacterBody2D

@onready var gun = $Gun
@onready var muzzle = $"Gun/Muzzle"

func _on_gun_ready():
\tprint("gun ready")
"""
        self.script_path.write_text(self.script_content, encoding="utf-8")

        S.STATE["project_root"] = str(self.root)
        S.STATE["current_chat_id"] = "test_chat_node_refactor"
        S.STATE["pending_action"] = None
        S.STATE["pending_node_refactor"] = None

        self.client = main.app.test_client()

    def test_preview_and_apply_routes(self):
        # 1. Preview
        resp = self.client.post("/scene/refactor/node/preview", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "new_name": "Weapon"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["prepared"]["new_name"], "Weapon")
        self.assertEqual(len(data["prepared"]["diffs"]), 2)  # .tscn and .gd

        # 2. Apply
        resp2 = self.client.post("/scene/refactor/node/apply", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "new_name": "Weapon"
        })
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2["ok"])
        self.assertTrue(data2["entry_id"])

        # Check scene and script content
        new_scene = self.scene_path.read_text(encoding="utf-8")
        self.assertIn('[node name="Weapon" type="Node2D" parent="."]', new_scene)
        self.assertIn('parent="Weapon"', new_scene)
        self.assertIn('from="Weapon"', new_scene)

        new_script = self.script_path.read_text(encoding="utf-8")
        self.assertIn('$Weapon', new_script)
        self.assertIn('$"Weapon/Muzzle"', new_script)

        # Rollback check
        ok, msg, paths, changed_path, changed_block = history_manager.rollback_last(str(self.root))
        self.assertTrue(ok)
        self.assertEqual(self.scene_path.read_text(encoding="utf-8"), self.scene_content)
        self.assertEqual(self.script_path.read_text(encoding="utf-8"), self.script_content)

    def test_model_action_and_confirm(self):
        # Simulate model returning rename_node action
        action = {
            "action": "rename_node",
            "scene": "res://scenes/player.tscn",
            "node": "Gun",
            "new_name": "Weapon"
        }
        with main.app.test_request_context():
            resp = main._package_model_reply("Переименовываю Gun в Weapon", action, str(self.root))
            data = resp.get_json()

        self.assertIsNotNone(data["pending_action"])
        self.assertEqual(data["pending_action"]["action"], "rename_node")
        self.assertEqual(data["pending_action"]["new_name"], "Weapon")
        self.assertEqual(len(data["pending_action_diffs"]), 2)

        # Confirm action
        resp_conf = self.client.post("/chat/confirm_action", json={"approved": True})
        self.assertEqual(resp_conf.status_code, 200)
        conf_data = resp_conf.get_json()
        self.assertIn("успешно переименован", conf_data["answer"])

        # Verify on disk
        new_scene = self.scene_path.read_text(encoding="utf-8")
        self.assertIn('[node name="Weapon" type="Node2D" parent="."]', new_scene)
        new_script = self.script_path.read_text(encoding="utf-8")
        self.assertIn('$Weapon', new_script)

    def test_reparent_flow(self):
        # Add Arm node to scene
        cur_tscn = self.scene_path.read_text(encoding="utf-8")
        arm_node = '[node name="Arm" type="Node2D" parent="."]\n\n'
        self.scene_path.write_text(cur_tscn.replace('[node name="Gun"', arm_node + '[node name="Gun"'), encoding="utf-8")

        # 1. Preview reparent
        resp = self.client.post("/scene/refactor/node/reparent/preview", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "new_parent": "Arm"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["prepared"]["new_path"], "Arm/Gun")

        # 2. Model action & confirm
        action = {
            "action": "reparent_node",
            "scene": "res://scenes/player.tscn",
            "node": "Gun",
            "new_parent": "Arm"
        }
        with main.app.test_request_context():
            resp_pkg = main._package_model_reply("Перемещаю Gun в Arm", action, str(self.root))
            pkg_data = resp_pkg.get_json()

        self.assertIsNotNone(pkg_data["pending_action"])
        self.assertEqual(pkg_data["pending_action"]["action"], "reparent_node")

        # Confirm
        resp_conf = self.client.post("/chat/confirm_action", json={"approved": True})
        self.assertEqual(resp_conf.status_code, 200)
        conf_data = resp_conf.get_json()
        self.assertIn("успешно перемещён", conf_data["answer"])

        # Verify on disk
        mod_scene = self.scene_path.read_text(encoding="utf-8")
        self.assertIn('[node name="Gun" type="Node2D" parent="Arm"]', mod_scene)
        mod_script = self.script_path.read_text(encoding="utf-8")
        self.assertIn('$Arm/Gun', mod_script)

        # Rollback via /chat/rollback
        resp_rb = self.client.post("/chat/rollback", json={})
        self.assertEqual(resp_rb.status_code, 200)
        rb_data = resp_rb.get_json()
        self.assertTrue(rb_data["success"])

        rb_scene = self.scene_path.read_text(encoding="utf-8")
        self.assertIn('[node name="Gun" type="Node2D" parent="."]', rb_scene)

    def test_delete_flow(self):
        # 1. Preview delete
        resp = self.client.post("/scene/refactor/node/delete/preview", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "cleanup_code": True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("Gun", data["prepared"]["deleted_nodes"])
        self.assertGreater(len(data["prepared"]["warnings"]), 0)

        # 2. Apply delete
        resp2 = self.client.post("/scene/refactor/node/delete/apply", json={
            "scene": "res://scenes/player.tscn",
            "node_path": "Gun",
            "cleanup_code": True
        })
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2["ok"])
        self.assertGreater(len(data2["warnings"]), 0)

        # Verify on disk: scene modified, script untouched
        mod_scene = self.scene_path.read_text(encoding="utf-8")
        self.assertNotIn('[node name="Gun"', mod_scene)
        mod_script = self.script_path.read_text(encoding="utf-8")
        self.assertIn('@onready var gun = $Gun', mod_script)
        self.assertNotIn('# [REMOVED_NODE]', mod_script)

        # Rollback via /chat/rollback
        resp_rb = self.client.post("/chat/rollback", json={})
        self.assertEqual(resp_rb.status_code, 200)
        rb_data = resp_rb.get_json()
        self.assertTrue(rb_data["success"])

        rb_scene = self.scene_path.read_text(encoding="utf-8")
        self.assertIn('[node name="Gun" type="Node2D" parent="."]', rb_scene)
        rb_script = self.script_path.read_text(encoding="utf-8")
        self.assertIn('@onready var gun = $Gun', rb_script)
        self.assertNotIn('# [REMOVED_NODE]', rb_script)


if __name__ == "__main__":
    unittest.main()

