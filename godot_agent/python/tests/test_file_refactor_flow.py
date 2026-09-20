# -*- coding: utf-8 -*-
"""Integration test for file refactor Flask routes, chat action, confirmation, and rollback."""

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


class FileRefactorFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="refactor_flow_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        (self.root / "project.godot").write_text(
            'config_version=5\n\n[autoload]\nPlayer="*res://src/player.gd"\n',
            encoding="utf-8"
        )
        (self.root / "src").mkdir(parents=True)
        (self.root / "scenes").mkdir(parents=True)

        self.target = self.root / "src" / "player.gd"
        self.target.write_text('extends Node\nclass_name Player\n\nvar hp = 100\n', encoding="utf-8")
        (self.root / "src" / "player.gd.uid").write_text('uid://player123\n', encoding="utf-8")

        self.main_gd = self.root / "src" / "main.gd"
        self.main_gd.write_text(
            'extends Node\nconst P = preload("res://src/player.gd")\n', encoding="utf-8"
        )

        S.STATE["project_root"] = str(self.root)
        S.STATE["current_chat_id"] = "test_chat_refactor"
        S.STATE["pending_action"] = None
        S.STATE["pending_file_refactor"] = None

        self.client = main.app.test_client()

    def test_preview_and_apply_routes(self):
        # 1. Preview
        resp = self.client.post("/project/refactor/file/preview", json={
            "old_path": "res://src/player.gd",
            "new_path": "res://src/hero.gd",
            "update_references": True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["prepared"]["reference_count"], 2)  # main.gd and project.godot
        self.assertEqual(len(data["prepared"]["diffs"]), 3)  # move + 2 patches

        # 2. Apply
        resp2 = self.client.post("/project/refactor/file/apply", json={
            "old_path": "res://src/player.gd",
            "new_path": "res://src/hero.gd",
            "update_references": True
        })
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2["ok"])
        self.assertTrue(data2["entry_id"])

        # Check files
        self.assertFalse((self.root / "src" / "player.gd").exists())
        self.assertTrue((self.root / "src" / "hero.gd").exists())
        self.assertIn('preload("res://src/hero.gd")', self.main_gd.read_text(encoding="utf-8"))
        self.assertIn('Player="*res://src/hero.gd"', (self.root / "project.godot").read_text(encoding="utf-8"))

    def test_model_action_and_confirm(self):
        # Simulate model returning rename_file action
        action = {
            "action": "rename_file",
            "path": "res://src/player.gd",
            "dest": "res://src/hero.gd",
            "update_references": True
        }
        with main.app.test_request_context():
            resp = main._package_model_reply("Переименовываю игрока в героя", action, str(self.root))
            data = resp.get_json()

        self.assertIsNotNone(data["pending_action"])
        self.assertEqual(data["pending_action"]["action"], "rename_file")
        self.assertEqual(data["pending_action"]["reference_count"], 2)
        self.assertIn("diffs", data["pending_action_diffs"][0] if "diffs" in data else "pending_action_diffs")

        # Confirm action
        resp_conf = self.client.post("/chat/confirm_action", json={"approved": True})
        self.assertEqual(resp_conf.status_code, 200)
        conf_data = resp_conf.get_json()
        self.assertIn("успешно переименован", conf_data["answer"])

        self.assertTrue((self.root / "src" / "hero.gd").exists())
        self.assertIn('preload("res://src/hero.gd")', self.main_gd.read_text(encoding="utf-8"))

    def test_directory_relocation_flow(self):
        combat_dir = self.root / "src" / "combat"
        combat_dir.mkdir(parents=True, exist_ok=True)
        (combat_dir / "sword.gd").write_text('extends Node\nconst S = preload("shield.gd")\n', encoding="utf-8")
        (combat_dir / "shield.gd").write_text('extends Node\n', encoding="utf-8")

        # 1. Preview directory relocation
        resp = self.client.post("/project/refactor/file/preview", json={
            "old_path": "res://src/combat",
            "new_path": "res://src/battle",
            "update_references": True
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["prepared"]["is_directory"])
        self.assertEqual(len(data["prepared"]["moved_files"]), 2)

        # 2. Apply directory relocation
        resp2 = self.client.post("/project/refactor/file/apply", json={
            "old_path": "res://src/combat",
            "new_path": "res://src/battle",
            "update_references": True
        })
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2["ok"])

        # Check disk
        self.assertFalse(combat_dir.exists())
        self.assertTrue((self.root / "src" / "battle" / "sword.gd").exists())
        self.assertTrue((self.root / "src" / "battle" / "shield.gd").exists())

        # 3. Rollback via client
        resp_rb = self.client.post("/chat/rollback", json={})
        self.assertEqual(resp_rb.status_code, 200)
        rb_data = resp_rb.get_json()
        self.assertTrue(rb_data["success"])

        self.assertTrue(combat_dir.exists())
        self.assertTrue((combat_dir / "sword.gd").exists())
        self.assertFalse((self.root / "src" / "battle").exists())

    def test_post_move_sync_flow(self):
        # 1. Simulate external file rename on disk (e.g. by Godot FileSystem dock)
        hero_target = self.root / "src" / "hero.gd"
        self.target.rename(hero_target)

        # 2. Call /project/refactor/file/post_move_sync via Flask client
        resp = self.client.post("/project/refactor/file/post_move_sync", json={
            "old_path": "res://src/player.gd",
            "new_path": "res://src/hero.gd",
            "is_directory": False,
            "project_root": str(self.root)
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("reference_count"), 2)
        self.assertIn("res://src/main.gd", data.get("changed_paths", []))
        self.assertIn("res://project.godot", data.get("changed_paths", []))

        # Check references in files on disk
        self.assertIn('preload("res://src/hero.gd")', self.main_gd.read_text(encoding="utf-8"))
        self.assertIn('Player="*res://src/hero.gd"', (self.root / "project.godot").read_text(encoding="utf-8"))

        # 3. Test rollback
        resp_rb = self.client.post("/chat/rollback", json={})
        self.assertEqual(resp_rb.status_code, 200)
        rb_data = resp_rb.get_json()
        self.assertTrue(rb_data["success"])
        self.assertIn('preload("res://src/player.gd")', self.main_gd.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


