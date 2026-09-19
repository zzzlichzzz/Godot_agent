"""Real temporary-project moves with injected filesystem failures; no Godot process."""
import errno
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import project_tools


class MoveSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="move_safety_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "project.godot").write_bytes(b"config_version=5\n")
        self.source = self.root / "Player.gd"
        self.uid = self.root / "Player.gd.uid"
        self.dest = self.root / "moved" / "Hero.gd"
        self.dest_uid = self.root / "moved" / "Hero.gd.uid"
        self.main_bytes = b"extends Node\r\n# original\r\n"
        self.uid_bytes = b"uid://original\n"
        self.source.write_bytes(self.main_bytes)
        self.uid.write_bytes(self.uid_bytes)

    def move(self, dest="res://moved/Hero.gd"):
        return project_tools.move_project_file(str(self.root), "res://Player.gd", dest)

    def assert_original_pair(self):
        self.assertEqual(self.source.read_bytes(), self.main_bytes)
        self.assertEqual(self.uid.read_bytes(), self.uid_bytes)

    def test_successful_pair_move_preserves_bytes_and_return(self):
        self.assertIsNone(self.move())
        self.assertFalse(self.source.exists())
        self.assertFalse(self.uid.exists())
        self.assertEqual(self.dest.read_bytes(), self.main_bytes)
        self.assertEqual(self.dest_uid.read_bytes(), self.uid_bytes)

    def test_move_without_uid(self):
        self.uid.unlink()
        self.assertIsNone(self.move())
        self.assertFalse(self.source.exists())
        self.assertEqual(self.dest.read_bytes(), self.main_bytes)
        self.assertFalse(self.dest_uid.exists())

    def test_second_uid_link_failure_restores_original_pair(self):
        link = os.link
        failure = OSError("injected UID move failure")

        def fail_uid(source, target):
            if Path(source) == self.uid:
                self.assertFalse(self.source.exists())
                self.assertEqual(self.dest.read_bytes(), self.main_bytes)
                raise failure
            return link(source, target)

        with patch.object(project_tools.os, "link", side_effect=fail_uid):
            with self.assertRaises(OSError) as caught:
                self.move()
        self.assertIs(caught.exception, failure)
        self.assert_original_pair()
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.dest_uid.exists())

    def test_source_unlink_failure_restores_pair_and_removes_only_own_links(self):
        unlink = os.unlink
        for failing_source in (self.source, self.uid):
            with self.subTest(source=failing_source):
                def fail_unlink(path):
                    if Path(path) == failing_source:
                        raise OSError("injected unlink failure")
                    return unlink(path)

                with patch.object(project_tools.os, "unlink", side_effect=fail_unlink):
                    with self.assertRaisesRegex(OSError, "injected unlink failure"):
                        self.move()
                self.assert_original_pair()
                self.assertFalse(self.dest.exists())
                self.assertFalse(self.dest_uid.exists())

    def test_existing_destination_or_uid_is_never_overwritten(self):
        self.dest.parent.mkdir()
        for target in (self.dest, self.dest_uid):
            with self.subTest(target=target):
                target.write_bytes(b"unrelated")
                with patch.object(project_tools.os, "link") as link:
                    with self.assertRaises(FileExistsError):
                        self.move()
                    link.assert_not_called()
                self.assert_original_pair()
                self.assertEqual(target.read_bytes(), b"unrelated")
                other = self.dest_uid if target == self.dest else self.dest
                self.assertFalse(other.exists())
                target.unlink()

    def test_destination_uid_collision_without_source_uid_is_rejected(self):
        self.uid.unlink()
        self.dest.parent.mkdir()
        self.dest_uid.write_bytes(b"unrelated")
        with self.assertRaises(FileExistsError):
            self.move()
        self.assertEqual(self.source.read_bytes(), self.main_bytes)
        self.assertEqual(self.dest_uid.read_bytes(), b"unrelated")
        self.assertFalse(self.dest.exists())

    def test_destination_created_after_preflight_is_not_overwritten_or_deleted(self):
        link = os.link
        for collision in (self.dest, self.dest_uid):
            with self.subTest(collision=collision):
                def race(source, target):
                    if Path(target) == collision:
                        collision.write_bytes(b"concurrent writer")
                    return link(source, target)

                with patch.object(project_tools.os, "link", side_effect=race):
                    with self.assertRaises(FileExistsError):
                        self.move()
                self.assert_original_pair()
                self.assertEqual(collision.read_bytes(), b"concurrent writer")
                other = self.dest_uid if collision == self.dest else self.dest
                self.assertFalse(other.exists())
                collision.unlink()

    def test_recovery_failure_preserves_evidence_and_reports_both_errors(self):
        link = os.link

        def fail_uid_and_restore(source, target):
            if Path(source) == self.uid:
                raise OSError("UID transfer failed")
            if Path(target) == self.source:
                raise OSError("restore denied")
            return link(source, target)

        with patch.object(project_tools.os, "link", side_effect=fail_uid_and_restore):
            with self.assertRaisesRegex(RuntimeError, "Move recovery failed.*restore denied.*UID transfer failed") as caught:
                self.move()
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertIn(str(self.dest).replace("\\", "\\\\"), str(caught.exception))
        self.assertFalse(self.source.exists())
        self.assertEqual(self.dest.read_bytes(), self.main_bytes)
        self.assertEqual(self.uid.read_bytes(), self.uid_bytes)
        self.assertFalse(self.dest_uid.exists())

    def test_recovery_does_not_overwrite_recreated_source(self):
        link = os.link

        def recreate_source(source, target):
            if Path(source) == self.uid:
                self.source.write_bytes(b"concurrent source")
                raise OSError("UID transfer failed")
            return link(source, target)

        with patch.object(project_tools.os, "link", side_effect=recreate_source):
            with self.assertRaisesRegex(RuntimeError, "Move recovery failed"):
                self.move()
        self.assertEqual(self.source.read_bytes(), b"concurrent source")
        self.assertEqual(self.dest.read_bytes(), self.main_bytes)
        self.assertEqual(self.uid.read_bytes(), self.uid_bytes)
        self.assertFalse(self.dest_uid.exists())

    def test_server_keeps_reservation_when_move_recovery_failed(self):
        import main
        import history_manager as history
        link = os.link

        def fail_uid_and_restore(source, target):
            if Path(source) == self.uid or Path(target) == self.source:
                raise OSError("injected transfer/restore failure")
            return link(source, target)

        with patch.dict(main.STATE, {"project_root": str(self.root), "addon_intent": False}), \
                patch.object(history, "_STORAGE_OVERRIDE", str(self.root / "history")), \
                patch.object(main, "_current_chat_info", return_value=("test-chat", "test")), \
                patch.object(project_tools.os, "link", side_effect=fail_uid_and_restore):
            result = main._apply_write_step({"action": "move_file", "path": "res://Player.gd",
                                            "dest": "res://moved/Hero.gd"}, str(self.root))
            self.assertFalse(result["ok"])
            self.assertTrue(result["recovery_required"])
            journal = history._load_journal(str(self.root))
            self.assertEqual(len(journal), 1)
            self.assertEqual(journal[0]["id"], result["recovery_entry_id"])
            self.assertFalse(journal[0].get("committed"))
        self.assertEqual(self.dest.read_bytes(), self.main_bytes)
        self.assertEqual(self.uid.read_bytes(), self.uid_bytes)

    def test_recovery_does_not_delete_replaced_target(self):
        link = os.link

        def replace_target(source, target):
            if Path(source) == self.uid:
                replacement = self.root / "replacement"
                replacement.write_bytes(b"unrelated replacement")
                os.replace(replacement, self.dest)
                raise OSError("UID transfer failed")
            return link(source, target)

        with patch.object(project_tools.os, "link", side_effect=replace_target):
            with self.assertRaisesRegex(RuntimeError, "Move recovery failed.*target changed"):
                self.move()
        self.assertEqual(self.dest.read_bytes(), b"unrelated replacement")
        self.assertEqual(self.uid.read_bytes(), self.uid_bytes)
        self.assertFalse(self.dest_uid.exists())

    def test_cross_device_failure_has_no_overwriting_fallback(self):
        link = os.link
        for failpoint in (self.source, self.uid):
            with self.subTest(failpoint=failpoint):
                def cross_device(source, target):
                    if Path(source) == failpoint:
                        raise OSError(errno.EXDEV, "different mount")
                    return link(source, target)

                with patch.object(project_tools.os, "link", side_effect=cross_device):
                    with self.assertRaises(OSError) as caught:
                        self.move()
                self.assertEqual(caught.exception.errno, errno.EXDEV)
                self.assert_original_pair()
                self.assertFalse(self.dest.exists())
                self.assertFalse(self.dest_uid.exists())

    def test_same_file_and_overlapping_sidecar_paths_are_rejected(self):
        for dest in ("res://Player.gd", "res://./Player.gd", "res://Player.gd.uid"):
            with self.subTest(dest=dest):
                with self.assertRaises(FileExistsError):
                    self.move(dest)
                self.assert_original_pair()

    @unittest.skipUnless(os.name == "nt", "Windows normcase identities")
    def test_windows_case_alias_is_rejected(self):
        with self.assertRaises(FileExistsError):
            self.move("res://PLAYER.GD")
        self.assert_original_pair()

    def test_hardlink_alias_is_rejected(self):
        self.dest.parent.mkdir()
        os.link(self.source, self.dest)
        with self.assertRaises(FileExistsError):
            self.move()
        self.assert_original_pair()
        self.assertTrue(os.path.samefile(self.source, self.dest))

    def test_unsafe_destination_is_rejected_before_moving(self):
        for dest in ("res://../escaped.gd", "res://.agent_history/hidden.gd"):
            with self.subTest(dest=dest):
                with self.assertRaises(ValueError):
                    self.move(dest)
                self.assert_original_pair()

    def test_dangling_destination_symlinks_are_not_followed(self):
        self.dest.parent.mkdir()
        for target in (self.dest, self.dest_uid):
            with self.subTest(target=target):
                missing = self.root / "missing"
                try:
                    target.symlink_to(missing)
                except OSError:
                    self.skipTest("symlinks not available")
                with self.assertRaises(FileExistsError):
                    self.move()
                self.assert_original_pair()
                self.assertTrue(target.is_symlink())
                self.assertFalse(missing.exists())
                target.unlink()

    def test_uid_symlink_cannot_escape_safe_path_helper(self):
        with tempfile.TemporaryDirectory(prefix="move_outside_") as outside:
            external = Path(outside, "external.uid")
            external.write_bytes(b"unrelated external UID")
            self.uid.unlink()
            try:
                self.uid.symlink_to(external)
            except OSError:
                self.skipTest("symlinks not available")
            with self.assertRaises(ValueError):
                self.move()
            self.assertEqual(self.source.read_bytes(), self.main_bytes)
            self.assertTrue(self.uid.is_symlink())
            self.assertEqual(external.read_bytes(), b"unrelated external UID")
            self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
