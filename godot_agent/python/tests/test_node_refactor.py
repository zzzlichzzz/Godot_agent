# -*- coding: utf-8 -*-
"""Unit tests for node_refactor: scene node rename, animation tracks, connections, and GDScript updates."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import history_manager
import node_refactor


class NodeRefactorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="node_refactor_test_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        # Create basic scene with hierarchy, animation, connections, and attached script
        self.player_tscn = self.root / "player.tscn"
        self.player_tscn.write_text(
            '[gd_scene load_steps=3 format=3]\n\n'
            '[ext_resource type="Script" path="res://player.gd" id="1_player"]\n'
            '[ext_resource type="Script" path="res://gun.gd" id="2_gun"]\n\n'
            '[sub_resource type="Animation" id="Animation_1"]\n'
            'resource_name = "shoot"\n'
            'tracks/0/type = "value"\n'
            'tracks/0/path = NodePath("Gun/Muzzle:position")\n'
            'tracks/1/type = "value"\n'
            'tracks/1/path = NodePath("Gun:rotation")\n\n'
            '[node name="Player" type="CharacterBody2D"]\n'
            'script = ExtResource("1_player")\n\n'
            '[node name="Gun" type="Node2D" parent="."]\n'
            'script = ExtResource("2_gun")\n'
            'unique_name_in_owner = true\n\n'
            '[node name="Muzzle" type="Marker2D" parent="Gun"]\n\n'
            '[node name="Spark" type="Node2D" parent="Gun/Muzzle"]\n\n'
            '[connection signal="fired" from="Gun" to="." method="_on_gun_fired"]\n'
            '[connection signal="sparked" from="Gun/Muzzle" to="Gun" method="_on_sparked"]\n',
            encoding="utf-8"
        )

        self.player_gd = self.root / "player.gd"
        self.player_gd.write_text(
            'extends CharacterBody2D\n\n'
            '@onready var gun: Node2D = $Gun\n'
            '@onready var muzzle = $"Gun/Muzzle"\n'
            '@onready var unique_gun = %Gun\n\n'
            'func _ready() -> void:\n'
            '    var g = get_node("Gun")\n'
            '    var m = get_node_or_null("Gun/Muzzle")\n'
            '    var u = get_node("%Gun")\n'
            '    var f = find_child("Gun")\n'
            '    if has_node("Gun"):\n'
            '        print("Has gun")\n\n'
            'func _on_gun_fired() -> void:\n'
            '    pass\n',
            encoding="utf-8"
        )

        self.gun_gd = self.root / "gun.gd"
        self.gun_gd.write_text(
            'extends Node2D\n\n'
            'signal fired\n\n'
            '@onready var muzzle = $Muzzle\n\n'
            'func shoot() -> void:\n'
            '    fired.emit()\n\n'
            'func _on_sparked() -> void:\n'
            '    pass\n',
            encoding="utf-8"
        )

    def test_parse_tscn_structure(self):
        tscn_text = self.player_tscn.read_text(encoding="utf-8")
        ext_res, nodes, conns, tracks = node_refactor.parse_tscn_structure(tscn_text)

        self.assertEqual(len(ext_res), 2)
        self.assertEqual(len(nodes), 4)  # Player, Gun, Muzzle, Spark
        self.assertEqual(nodes[0]["name"], "Player")
        self.assertEqual(nodes[0]["path"], ".")
        self.assertEqual(nodes[1]["name"], "Gun")
        self.assertEqual(nodes[1]["path"], "Gun")
        self.assertTrue(nodes[1]["unique_name"])
        self.assertEqual(nodes[2]["name"], "Muzzle")
        self.assertEqual(nodes[2]["path"], "Gun/Muzzle")
        self.assertEqual(nodes[3]["name"], "Spark")
        self.assertEqual(nodes[3]["path"], "Gun/Muzzle/Spark")

        self.assertEqual(len(conns), 2)
        self.assertEqual(conns[0]["from"], "Gun")
        self.assertEqual(conns[1]["from"], "Gun/Muzzle")
        self.assertEqual(conns[1]["to"], "Gun")

        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0]["path"], "Gun/Muzzle:position")
        self.assertEqual(tracks[1]["path"], "Gun:rotation")

    def test_prepare_and_apply_node_rename(self):
        # Rename Gun -> Weapon
        prep = node_refactor.prepare_node_rename(
            str(self.root), "res://player.tscn", "Gun", "Weapon", update_scripts=True
        )
        self.assertEqual(prep["action"], "rename_node")
        self.assertEqual(prep["old_name"], "Gun")
        self.assertEqual(prep["new_name"], "Weapon")
        # .tscn and player.gd should be modified (gun.gd only accesses its own children $Muzzle, so stays unchanged)
        paths = prep["affected_paths"]
        self.assertIn("res://player.tscn", paths)
        self.assertIn("res://player.gd", paths)

        # Apply
        res = node_refactor.apply_prepared_node_rename(str(self.root), prep)
        self.assertTrue(res["entry_id"])

        # Check .tscn content
        new_tscn = self.player_tscn.read_text(encoding="utf-8")
        self.assertIn('[node name="Weapon" type="Node2D" parent="."]', new_tscn)
        self.assertIn('[node name="Muzzle" type="Marker2D" parent="Weapon"]', new_tscn)
        self.assertIn('[node name="Spark" type="Node2D" parent="Weapon/Muzzle"]', new_tscn)
        self.assertIn('from="Weapon"', new_tscn)
        self.assertIn('from="Weapon/Muzzle"', new_tscn)
        self.assertIn('to="Weapon"', new_tscn)
        self.assertIn('tracks/0/path = NodePath("Weapon/Muzzle:position")', new_tscn)
        self.assertIn('tracks/1/path = NodePath("Weapon:rotation")', new_tscn)

        # Check player.gd content
        new_gd = self.player_gd.read_text(encoding="utf-8")
        self.assertIn('@onready var gun: Node2D = $Weapon', new_gd)
        self.assertIn('@onready var muzzle = $"Weapon/Muzzle"', new_gd)
        self.assertIn('@onready var unique_gun = %Weapon', new_gd)
        self.assertIn('get_node("Weapon")', new_gd)
        self.assertIn('get_node_or_null("Weapon/Muzzle")', new_gd)
        self.assertIn('get_node("%Weapon")', new_gd)
        self.assertIn('find_child("Weapon")', new_gd)
        self.assertIn('has_node("Weapon")', new_gd)

        # gun.gd shouldn't be broken
        gun_text = self.gun_gd.read_text(encoding="utf-8")
        self.assertIn('$Muzzle', gun_text)

        # Test Rollback
        rb_res = history_manager.rollback_last(str(self.root))
        self.assertTrue(rb_res[0], "Rollback failed: %s" % (rb_res,))

        # Verify restoration
        rb_tscn = self.player_tscn.read_text(encoding="utf-8")
        self.assertIn('[node name="Gun" type="Node2D" parent="."]', rb_tscn)
        self.assertIn('[node name="Muzzle" type="Marker2D" parent="Gun"]', rb_tscn)
        self.assertIn('tracks/0/path = NodePath("Gun/Muzzle:position")', rb_tscn)

        rb_gd = self.player_gd.read_text(encoding="utf-8")
        self.assertIn('$Gun', rb_gd)
        self.assertIn('%Gun', rb_gd)
        self.assertIn('get_node("Gun")', rb_gd)

    def test_prepare_and_apply_node_reparent(self):
        # Add Arm node to scene
        cur_tscn = self.player_tscn.read_text(encoding="utf-8")
        arm_node = '[node name="Arm" type="Node2D" parent="."]\n\n'
        new_tscn = cur_tscn.replace('[node name="Gun"', arm_node + '[node name="Gun"')
        self.player_tscn.write_text(new_tscn, encoding="utf-8")

        # Reparent Gun to Arm
        prep = node_refactor.prepare_node_reparent(
            str(self.root), "res://player.tscn", "Gun", "Arm", update_scripts=True
        )
        self.assertEqual(prep["action"], "reparent_node")
        self.assertEqual(prep["old_path"], "Gun")
        self.assertEqual(prep["new_path"], "Arm/Gun")
        self.assertEqual(prep["new_parent"], "Arm")

        # Apply
        res = node_refactor.apply_prepared_node_reparent(str(self.root), prep)
        self.assertTrue(res["entry_id"])

        # Check .tscn
        mod_tscn = self.player_tscn.read_text(encoding="utf-8")
        self.assertIn('[node name="Gun" type="Node2D" parent="Arm"]', mod_tscn)
        self.assertIn('[node name="Muzzle" type="Marker2D" parent="Arm/Gun"]', mod_tscn)
        self.assertIn('[node name="Spark" type="Node2D" parent="Arm/Gun/Muzzle"]', mod_tscn)
        self.assertIn('from="Arm/Gun"', mod_tscn)
        self.assertIn('from="Arm/Gun/Muzzle"', mod_tscn)
        self.assertIn('to="Arm/Gun"', mod_tscn)
        self.assertIn('tracks/0/path = NodePath("Arm/Gun/Muzzle:position")', mod_tscn)
        self.assertIn('tracks/1/path = NodePath("Arm/Gun:rotation")', mod_tscn)

        # Check player.gd (dollar paths updated, %Gun unique unchanged)
        mod_gd = self.player_gd.read_text(encoding="utf-8")
        self.assertIn('$Arm/Gun', mod_gd)
        self.assertIn('$"Arm/Gun/Muzzle"', mod_gd)
        self.assertIn('get_node("Arm/Gun")', mod_gd)
        self.assertIn('get_node_or_null("Arm/Gun/Muzzle")', mod_gd)
        self.assertIn('%Gun', mod_gd)

        # Check gun.gd (internal relative $Muzzle unchanged)
        gun_text = self.gun_gd.read_text(encoding="utf-8")
        self.assertIn('$Muzzle', gun_text)

        # Rollback
        rb_res = history_manager.rollback_last(str(self.root))
        self.assertTrue(rb_res[0], "Rollback failed: %s" % (rb_res,))

        rb_tscn = self.player_tscn.read_text(encoding="utf-8")
        self.assertIn('[node name="Gun" type="Node2D" parent="."]', rb_tscn)
        self.assertIn('[node name="Muzzle" type="Marker2D" parent="Gun"]', rb_tscn)

        rb_gd = self.player_gd.read_text(encoding="utf-8")
        self.assertIn('$Gun', rb_gd)
        self.assertIn('$"Gun/Muzzle"', rb_gd)

    def test_reparent_node_upward_quotes_dollar_syntax(self):
        # Create an arm.gd attached to Arm that refers to Gun as $Gun when Gun is under Arm
        cur_tscn = self.player_tscn.read_text(encoding="utf-8")
        arm_script = self.root / "arm.gd"
        arm_script.write_text('extends Node2D\n@onready var my_gun = $Gun\n', encoding="utf-8")
        
        # Add ext_resource for arm.gd and attach to Arm
        ext_arm = '[ext_resource type="Script" path="res://arm.gd" id="3_arm"]\n'
        arm_node = '[node name="Arm" type="Node2D" parent="."]\nscript = ExtResource("3_arm")\n\n'
        new_tscn = cur_tscn.replace('[ext_resource', ext_arm + '[ext_resource')
        new_tscn = new_tscn.replace('[node name="Gun" type="Node2D" parent="."]',
                                    arm_node + '[node name="Gun" type="Node2D" parent="Arm"]')
        self.player_tscn.write_text(new_tscn, encoding="utf-8")

        # Reparent Gun from Arm back to root '.'
        prep = node_refactor.prepare_node_reparent(
            str(self.root), "res://player.tscn", "Arm/Gun", ".", update_scripts=True
        )
        self.assertEqual(prep["action"], "reparent_node")
        self.assertEqual(prep["new_path"], "Gun")

        res = node_refactor.apply_prepared_node_reparent(str(self.root), prep)
        self.assertTrue(res["entry_id"])

        # Check arm.gd: unquoted $Gun must be converted to quoted $"../Gun" (NOT invalid $../Gun)
        mod_arm = arm_script.read_text(encoding="utf-8")
        self.assertIn('@onready var my_gun = $"../Gun"', mod_arm)
        self.assertNotIn('$../Gun', mod_arm)

        # Rollback
        rb_res = history_manager.rollback_last(str(self.root))
        self.assertTrue(rb_res[0])
        self.assertIn('@onready var my_gun = $Gun', arm_script.read_text(encoding="utf-8"))

    def test_prepare_and_apply_node_deletion(self):
        # Delete Gun (and descendants Muzzle, Spark)
        prep = node_refactor.prepare_node_deletion(
            str(self.root), "res://player.tscn", "Gun", cleanup_code=True
        )
        self.assertEqual(prep["action"], "delete_node")
        self.assertIn("Gun", prep["deleted_nodes"])
        self.assertIn("Gun/Muzzle", prep["deleted_nodes"])
        self.assertIn("Gun/Muzzle/Spark", prep["deleted_nodes"])

        # Warnings should record references in player.gd without modifying it
        self.assertGreater(len(prep["warnings"]), 0)
        warn_codes = [w["code"] for w in prep["warnings"]]
        self.assertTrue(any("@onready var gun: Node2D = $Gun" in c for c in warn_codes))
        self.assertTrue(any('@onready var muzzle = $"Gun/Muzzle"' in c for c in warn_codes))
        self.assertTrue(any("@onready var unique_gun = %Gun" in c for c in warn_codes))
        self.assertEqual(len(prep["files"]), 1)  # only player.tscn

        # Apply
        res = node_refactor.apply_prepared_node_deletion(str(self.root), prep)
        self.assertTrue(res["entry_id"])

        # Check .tscn (nodes, connections, tracks removed)
        mod_tscn = self.player_tscn.read_text(encoding="utf-8")
        self.assertNotIn('[node name="Gun"', mod_tscn)
        self.assertNotIn('[node name="Muzzle"', mod_tscn)
        self.assertNotIn('[node name="Spark"', mod_tscn)
        self.assertNotIn('from="Gun"', mod_tscn)
        self.assertNotIn('from="Gun/Muzzle"', mod_tscn)
        self.assertNotIn('NodePath("Gun', mod_tscn)

        # Check player.gd (NOT modified, untouched)
        mod_gd = self.player_gd.read_text(encoding="utf-8")
        self.assertIn('@onready var gun: Node2D = $Gun', mod_gd)
        self.assertIn('@onready var muzzle = $"Gun/Muzzle"', mod_gd)
        self.assertIn('@onready var unique_gun = %Gun', mod_gd)
        self.assertIn('var g = get_node("Gun")', mod_gd)
        self.assertNotIn('# [REMOVED_NODE]', mod_gd)

        # Rollback
        rb_res = history_manager.rollback_last(str(self.root))
        self.assertTrue(rb_res[0], "Rollback failed: %s" % (rb_res,))

        rb_tscn = self.player_tscn.read_text(encoding="utf-8")
        self.assertIn('[node name="Gun" type="Node2D" parent="."]', rb_tscn)
        self.assertIn('[node name="Muzzle" type="Marker2D" parent="Gun"]', rb_tscn)
        self.assertIn('tracks/0/path = NodePath("Gun/Muzzle:position")', rb_tscn)

        rb_gd = self.player_gd.read_text(encoding="utf-8")
        self.assertIn('@onready var gun: Node2D = $Gun', rb_gd)
        self.assertNotIn('# [REMOVED_NODE]', rb_gd)


if __name__ == "__main__":
    unittest.main()

