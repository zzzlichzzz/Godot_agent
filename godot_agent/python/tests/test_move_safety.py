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

    def _make_case_only_pair(self):
        """Add a nested file pair whose parent directory needs new casing."""
        source_dir = self.root / "chars"
        source = source_dir / "hero.gd"
        uid = source_dir / "hero.gd.uid"
        source_dir.mkdir()
        source.write_bytes(self.main_bytes)
        uid.write_bytes(self.uid_bytes)
        renamed_dir = self.root / "Chars"
        return source_dir, source, uid, renamed_dir

    def _move_case_only_pair(self):
        return project_tools.move_project_file(
            str(self.root), "res://chars/hero.gd", "res://Chars/hero.gd")

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

    def test_cross_device_failure_falls_back_to_exclusive_copy(self):
        # EXDEV means "no hardlinks across volumes": the move must still
        # succeed via the fail-if-exists copy fallback (audit 4.2).
        def cross_device(source, target):
            raise OSError(errno.EXDEV, "different mount")

        with patch.object(project_tools.os, "link", side_effect=cross_device):
            self.assertIsNone(self.move())
        self.assertFalse(self.source.exists())
        self.assertFalse(self.uid.exists())
        self.assertEqual(self.dest.read_bytes(), self.main_bytes)
        self.assertEqual(self.dest_uid.read_bytes(), self.uid_bytes)

    def test_same_file_and_overlapping_sidecar_paths_are_rejected(self):
        for dest in ("res://Player.gd", "res://./Player.gd", "res://Player.gd.uid"):
            with self.subTest(dest=dest):
                with self.assertRaises(FileExistsError):
                    self.move(dest)
                self.assert_original_pair()

    @unittest.skipUnless(os.name == "nt", "Windows normcase identities")
    def test_windows_case_alias_performs_case_only_rename(self):
        # player.gd -> Player.gd is a legitimate rename, not an alias
        # collision (audit 4.1).
        self.assertIsNone(self.move("res://PLAYER.GD"))
        names = os.listdir(self.root)
        self.assertIn("PLAYER.GD", names)
        self.assertNotIn("Player.gd", names)
        self.assertEqual((self.root / "PLAYER.GD").read_bytes(), self.main_bytes)
        self.assertEqual((self.root / "PLAYER.GD.uid").read_bytes(), self.uid_bytes)

    @unittest.skipUnless(os.name == "nt", "case-only filesystem aliases require Windows")
    def test_case_only_file_failure_rolls_back_parent_directory_casing(self):
        source_dir, source, uid, renamed_dir = self._make_case_only_pair()
        failure = OSError("injected case-only file failure")

        with patch.object(project_tools, "_move_case_only", side_effect=failure):
            with self.assertRaises(OSError) as caught:
                self._move_case_only_pair()

        self.assertIs(caught.exception, failure)
        names = os.listdir(self.root)
        self.assertIn("chars", names)
        self.assertNotIn("Chars", names)
        self.assertEqual(source.read_bytes(), self.main_bytes)
        self.assertEqual(uid.read_bytes(), self.uid_bytes)

    @unittest.skipUnless(os.name == "nt", "case-only filesystem aliases require Windows")
    def test_failed_parent_casing_rollback_reports_paths_and_retains_recovery_state(self):
        source_dir, source, uid, renamed_dir = self._make_case_only_pair()
        real_rename = os.rename
        file_failure = OSError("injected case-only leaf failure")
        rollback_failure = OSError("injected parent casing rollback failure")
        attempts = {"parents": 0, "files": 0, "rollbacks": 0}

        def injected_rename(old_path, new_path):
            old_name = os.path.basename(old_path)
            new_name = os.path.basename(new_path)
            if old_name == "chars" and new_name == "Chars":
                attempts["parents"] += 1
                return real_rename(old_path, new_path)
            if old_name.lower() == "hero.gd" and new_name.lower() == "hero.gd":
                attempts["files"] += 1
                raise file_failure
            if old_name == "Chars" and new_name == "chars":
                attempts["rollbacks"] += 1
                raise rollback_failure
            return real_rename(old_path, new_path)

        import main
        import history_manager as history

        with patch.dict(main.STATE, {"project_root": str(self.root), "addon_intent": False}), \
                patch.object(history, "_STORAGE_OVERRIDE", str(self.root / "history")), \
                patch.object(main, "_current_chat_info", return_value=("test-chat", "test")), \
                patch.object(project_tools.os, "rename", side_effect=injected_rename):
            result = main._apply_write_step(
                {"action": "move_file", "path": "res://chars/hero.gd",
                 "dest": "res://Chars/hero.gd"},
                str(self.root))
            journal = history._load_journal(str(self.root))
            history_root = history._history_dir(str(self.root))

        self.assertFalse(result["ok"])
        self.assertTrue(result["recovery_required"])
        self.assertEqual(attempts, {"parents": 1, "files": 1, "rollbacks": 1})
        message = result["message"]
        self.assertIn(str(renamed_dir).replace("\\", "\\\\"), message)
        self.assertIn(str(source_dir).replace("\\", "\\\\"), message)
        self.assertIn("case-only leaf failure", message)
        self.assertIn("parent casing rollback failure", message)
        self.assertTrue(renamed_dir.is_dir())
        self.assertEqual((renamed_dir / "hero.gd").read_bytes(), self.main_bytes)
        self.assertEqual((renamed_dir / "hero.gd.uid").read_bytes(), self.uid_bytes)
        root_names = os.listdir(self.root)
        self.assertIn("Chars", root_names)
        self.assertNotIn("chars", root_names)

        self.assertEqual(len(journal), 1)
        self.assertFalse(journal[0].get("committed"))
        self.assertTrue(result["recovery_entry_id"])
        self.assertTrue(journal[0]["files"])
        for item in journal[0]["files"]:
            if item.get("snapshot"):
                self.assertTrue(os.path.isfile(os.path.join(history_root, item["snapshot"])))

    @unittest.skipUnless(os.name == "nt", "case-only filesystem aliases require Windows")
    def test_successful_nested_case_only_rename_moves_file_and_uid(self):
        _source_dir, _source, _uid, renamed_dir = self._make_case_only_pair()

        self.assertIsNone(self._move_case_only_pair())

        names = os.listdir(self.root)
        self.assertIn("Chars", names)
        self.assertNotIn("chars", names)
        self.assertEqual((renamed_dir / "hero.gd").read_bytes(), self.main_bytes)
        self.assertEqual((renamed_dir / "hero.gd.uid").read_bytes(), self.uid_bytes)

    def test_case_only_file_rollback_failure_preserves_files_and_reports_paths(self):
        source = self.source
        dest = self.root / "PLAYER.GD"
        uid = self.uid
        real_rename = os.rename
        transfer_failure = OSError("injected case-only UID failure")
        recovery_failure = OSError("injected case-only file recovery failure")

        def injected_rename(old_path, new_path):
            old_name = os.path.basename(old_path)
            new_name = os.path.basename(new_path)
            if old_name == "Player.gd.uid":
                raise transfer_failure
            if old_name == "PLAYER.GD" and new_name == "Player.gd":
                raise recovery_failure
            return real_rename(old_path, new_path)

        with patch.object(project_tools.os, "rename", side_effect=injected_rename):
            with self.assertRaises(project_tools.MoveRecoveryError) as caught:
                project_tools._move_case_only(str(source), str(dest))

        message = str(caught.exception)
        self.assertIn(str(dest).replace("\\", "\\\\"), message)
        self.assertIn(str(source).replace("\\", "\\\\"), message)
        self.assertIn("case-only file recovery failure", message)
        self.assertIn("case-only UID failure", message)
        self.assertEqual(dest.read_bytes(), self.main_bytes)
        self.assertEqual(uid.read_bytes(), self.uid_bytes)
        root_names = os.listdir(self.root)
        self.assertIn("PLAYER.GD", root_names)
        self.assertIn("Player.gd.uid", root_names)
        self.assertNotIn("PLAYER.GD.uid", root_names)

    def test_repeated_rollback_of_finished_transaction_is_idempotent(self):
        nested = self.root / "chars" / "enemies"
        nested.mkdir(parents=True)
        (nested / "hero.gd").write_bytes(self.main_bytes)
        transaction = project_tools.begin_case_only_dir_casing(
            str(self.root), "chars/enemies/hero.gd", "Chars/Enemies/hero.gd")
        real_rename = os.rename
        calls = []

        def counting_rename(old_path, new_path):
            calls.append((os.path.basename(old_path), os.path.basename(new_path)))
            return real_rename(old_path, new_path)

        with patch.object(project_tools.os, "rename", side_effect=counting_rename):
            transaction.rollback()
            transaction.rollback()

        self.assertEqual(transaction.state, "rolled_back")
        self.assertEqual(calls, [("Enemies", "enemies"), ("Chars", "chars")])
        self.assertIn("chars", os.listdir(self.root))
        self.assertNotIn("Chars", os.listdir(self.root))
        self.assertIn("enemies", os.listdir(self.root / "chars"))
        self.assertNotIn("Enemies", os.listdir(self.root / "chars"))

    def test_rollback_after_commit_is_safe_noop(self):
        self._make_case_only_pair()
        transaction = project_tools.begin_case_only_dir_casing(
            str(self.root), "chars/hero.gd", "Chars/hero.gd")
        transaction.commit()
        with patch.object(project_tools.os, "rename", side_effect=AssertionError("must not rename")):
            transaction.rollback()
        self.assertEqual(transaction.state, "committed")
        self.assertIn("Chars", os.listdir(self.root))

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
