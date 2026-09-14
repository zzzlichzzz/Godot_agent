"""Fault injection for disk writes and editor transaction recovery."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import history_manager as history
import project_tools


class WriteRecoverySafety(unittest.TestCase):
    def test_atomic_write_failures_preserve_existing_and_absent_targets(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "player.gd")
            original = b"extends Node\r\nvar health = 10\r\n"
            for operation in ("create", "patch"):
                for failpoint in ("fsync", "replace"):
                    target.write_bytes(original)
                    with patch.object(project_tools.os, failpoint, side_effect=OSError("disk failure")):
                        with self.assertRaises(OSError):
                            if operation == "create":
                                project_tools.create_project_file(root, "res://player.gd", "new content")
                            else:
                                project_tools.patch_project_file(root, "res://player.gd", "health = 10", "health = 20")
                    self.assertEqual(target.read_bytes(), original)
                    self.assertEqual(list(Path(root).glob(".agent-write-*")), [])
            with patch.object(project_tools.os, "replace", side_effect=OSError("replace failure")):
                with self.assertRaises(OSError):
                    project_tools.create_project_file(root, "res://new.gd", "extends Node\n")
            self.assertFalse(Path(root, "new.gd").exists())

    def test_successful_atomic_write_preserves_public_return_and_lf(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(project_tools.create_project_file(root, "res://node.gd", "extends Node\r\n"))
            self.assertTrue(project_tools.create_project_file(root, "res://node.gd", "extends Node\r\nvar a = 1\r\n"))
            project_tools.patch_project_file(root, "res://node.gd", "a = 1", "a = 2")
            self.assertEqual(Path(root, "node.gd").read_bytes(), b"extends Node\nvar a = 2\n")

    def test_recovery_requires_exact_report_and_keeps_conflicts(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as store:
            history.set_storage_dir(store)
            target = Path(root, "main.tscn")
            original = b"original\r\n"
            target.write_bytes(original)
            entry = history.record_batch_change(root, "edit_scene", ["res://main.tscn"])
            target.write_bytes(b"external\r\n")
            for reported in (None, hashlib.sha256(b"external\n").hexdigest()):
                ok, _, _ = history.restore_reserved_change(root, entry, current_hash=reported)
                self.assertFalse(ok)
                self.assertEqual(target.read_bytes(), b"external\r\n")
                self.assertTrue(any(item["id"] == entry for item in history._load_journal(root)))
            ok, _, _ = history.restore_reserved_change(
                root, entry, current_hash=hashlib.sha256(target.read_bytes()).hexdigest())
            self.assertTrue(ok)
            self.assertEqual(target.read_bytes(), original)

    def test_missing_target_recovery_and_abort_snapshot_cleanup(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as store:
            history.set_storage_dir(store)
            target = Path(root, "node.gd")
            target.write_bytes(b"original\n")
            reservation = history.record_batch_change(root, "edit_scene", ["res://node.gd"])
            target.unlink()
            ok, _, _ = history.restore_reserved_change(root, reservation)
            self.assertTrue(ok)
            self.assertEqual(target.read_bytes(), b"original\n")
            entry = history.record_change(root, {"action": "patch_file", "path": "res://node.gd"})
            record = next(item for item in history._load_journal(root) if item["id"] == entry)
            snapshot = Path(history._history_dir(root), record["snapshot"])
            self.assertTrue(snapshot.exists())
            history.abort_change(root, entry)
            self.assertFalse(snapshot.exists())


if __name__ == "__main__":
    unittest.main()
