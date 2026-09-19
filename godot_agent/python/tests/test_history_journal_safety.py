"""Journal persistence, transaction serialization, and rollback identity safety."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import history_manager as history


class HistoryJournalSafety(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = str(Path(temporary.name, "project"))
        Path(self.root).mkdir()
        self.previous_storage = history._STORAGE_OVERRIDE
        self.addCleanup(setattr, history, "_STORAGE_OVERRIDE", self.previous_storage)
        history.set_storage_dir(temporary.name)
        self.hist = Path(history.get_storage_dir(self.root))
        self.journal = self.hist / "journal.json"
        self.target = Path(self.root, "Player.gd")
        self.target.write_bytes(b"before\n")

    def record(self, path="res://Player.gd", batch=False, **kwargs):
        if batch:
            return history.record_batch_change(self.root, "transaction", [path], **kwargs)
        return history.record_change(
            self.root, {"action": "patch_file", "path": path}, **kwargs)

    def snapshots(self):
        return {path.name: path.read_bytes() for path in (self.hist / "snapshots").iterdir()}

    def test_only_missing_journal_is_empty(self):
        self.assertEqual(history._load_journal(self.root), [])
        self.journal.mkdir()
        with self.assertRaises(OSError):
            history._load_journal(self.root)
        self.assertTrue(self.journal.is_dir())

    def test_invalid_journal_fails_closed_without_renaming_or_snapshot_changes(self):
        entry = self.record()
        snapshots = self.snapshots()
        operations = [
            lambda: history._load_journal(self.root),
            self.record,
            lambda: self.record(batch=True),
            lambda: history.commit_change(self.root, entry),
            lambda: history.abort_change(self.root, entry),
            lambda: history.forget_chat(self.root, "chat"),
            lambda: history.restore_reserved_change(self.root, entry),
            lambda: history.rollback_entry(self.root, entry, force=True),
            lambda: history.rollback_last(self.root, force=True),
            lambda: history.rollback_chain(self.root, "chain", force=True),
        ]
        for invalid in (b"{truncated", b"\xff", b"{}", b"null", b"[null]", b"[{}]"):
            self.journal.write_bytes(invalid)
            for operation in operations:
                with self.subTest(invalid=invalid, operation=operation):
                    with self.assertRaises((ValueError, UnicodeError)):
                        operation()
                    self.assertEqual(self.journal.read_bytes(), invalid)
                    self.assertEqual(self.snapshots(), snapshots)
                    self.assertFalse(Path(str(self.journal) + ".broken").exists())

    def test_unreadable_journal_preserves_original(self):
        self.record()
        original = self.journal.read_bytes()
        snapshots = self.snapshots()
        real_open = open

        def deny_journal(path, *args, **kwargs):
            if os.fspath(path) == str(self.journal):
                raise PermissionError("injected journal read denial")
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=deny_journal):
            for operation in (lambda: history._load_journal(self.root), self.record,
                              lambda: self.record(batch=True)):
                with self.assertRaises(PermissionError):
                    operation()
        self.assertEqual(self.journal.read_bytes(), original)
        self.assertEqual(self.snapshots(), snapshots)
        self.assertFalse(Path(str(self.journal) + ".broken").exists())

    def test_failed_fsync_and_replace_preserve_existing_or_missing_journal(self):
        for existing in (False, True):
            for failpoint in ("fsync", "replace"):
                for batch in (False, True):
                    with self.subTest(existing=existing, failpoint=failpoint, batch=batch):
                        if existing:
                            history._save_journal(self.root, [])
                        elif self.journal.exists():
                            self.journal.unlink()
                        original = self.journal.read_bytes() if existing else None
                        with patch.object(history.os, failpoint, side_effect=OSError("disk failure")):
                            with self.assertRaises(OSError):
                                self.record(batch=batch)
                        self.assertEqual(self.journal.read_bytes() if self.journal.exists() else None,
                                         original)
                        self.assertEqual(list(self.hist.glob(".journal-*.tmp")), [])
                        self.assertEqual(self.snapshots(), {})

    def test_save_uses_unique_temporary_and_syncs_before_replace(self):
        legacy_temp = Path(str(self.journal) + ".tmp")
        legacy_temp.write_bytes(b"not ours")
        events = []
        temporaries = []
        real_fsync, real_replace = os.fsync, os.replace

        def sync(fd):
            events.append("fsync")
            real_fsync(fd)

        def replace(source, destination):
            events.append("replace")
            temporaries.append(source)
            self.assertEqual(Path(source).parent, self.hist)
            self.assertEqual(Path(destination), self.journal)
            self.assertIsInstance(json.loads(Path(source).read_text(encoding="utf-8")), list)
            real_replace(source, destination)

        with patch.object(history.os, "fsync", side_effect=sync), \
                patch.object(history.os, "replace", side_effect=replace):
            entry = self.record()
            history.commit_change(self.root, entry)
        self.assertEqual(events, ["fsync", "replace", "fsync", "replace"])
        self.assertEqual(len(set(temporaries)), 2)
        self.assertTrue(all(not Path(path).exists() for path in temporaries))
        self.assertEqual(legacy_temp.read_bytes(), b"not ours")

    def test_concurrent_record_and_commit_no_lost_updates(self):
        count = 12
        start = threading.Barrier(count)
        real_load = history._load_journal

        def slow_load(root):
            journal = real_load(root)
            # Widen the stale-read window if the outer transaction lock is absent.
            time.sleep(0.01)
            return journal

        def worker(index):
            start.wait(timeout=10)
            # Different project roots share the same overridden journal.
            root = os.path.join(self.root, "root_%d" % index)
            Path(root).mkdir()
            entry = history.record_change(
                root, {"action": "create_file", "path": "res://new.gd"},
                chat_id="chat_%d" % index)
            history.commit_change(root, entry)
            history.forget_chat(root, "chat_%d" % index)
            return entry

        with patch.object(history, "_load_journal", side_effect=slow_load):
            with ThreadPoolExecutor(max_workers=count) as pool:
                entries = list(pool.map(worker, range(count)))
        journal = history._load_journal(self.root)
        self.assertEqual({entry["id"] for entry in journal}, set(entries))
        self.assertEqual(len(journal), count)
        self.assertTrue(all(entry["committed"] and "chat_id" not in entry for entry in journal))

    def test_cap_preserves_single_and_batch_reservations(self):
        pending = [self.record(), self.record(batch=True)]
        reserved_snapshots = self.snapshots()
        committed = []
        with patch.object(history, "MAX_ENTRIES", 2):
            for index in range(4):
                entry = self.record(batch=bool(index % 2))
                history.commit_change(self.root, entry)
                committed.append(entry)
        journal = history._load_journal(self.root)
        self.assertEqual([entry["id"] for entry in journal], pending + committed[-2:])
        for name, contents in reserved_snapshots.items():
            self.assertEqual(self.snapshots()[name], contents)
        self.assertEqual(len(self.snapshots()), 4)

    def test_failed_prune_save_preserves_every_snapshot(self):
        with patch.object(history, "MAX_ENTRIES", 1):
            old = self.record(batch=True)
            history.commit_change(self.root, old)
            pending = self.record(batch=True)
            new = self.record()
            original = self.journal.read_bytes()
            snapshots = self.snapshots()
            for failpoint in ("fsync", "replace"):
                with self.subTest(failpoint=failpoint):
                    with patch.object(history.os, failpoint, side_effect=OSError("prune failure")):
                        with self.assertRaises(OSError):
                            history.commit_change(self.root, new)
                    self.assertEqual(self.journal.read_bytes(), original)
                    self.assertEqual(self.snapshots(), snapshots)
            history.commit_change(self.root, new)
        journal = history._load_journal(self.root)
        self.assertEqual([entry["id"] for entry in journal], [pending, new])
        self.assertEqual(len(self.snapshots()), 2)

    def test_abort_save_failure_keeps_reservation_and_snapshots(self):
        entry = self.record(batch=True)
        original = self.journal.read_bytes()
        snapshots = self.snapshots()
        with patch.object(history.os, "replace", side_effect=OSError("abort failure")):
            with self.assertRaises(OSError):
                history.abort_change(self.root, entry)
        self.assertEqual(self.journal.read_bytes(), original)
        self.assertEqual(self.snapshots(), snapshots)

    def test_batch_duplicate_paths_refused_before_snapshot(self):
        aliases = ["res://Player.gd", "Player.gd", "res://./Player.gd"]
        if os.name == "nt":
            aliases.extend(["res://PLAYER.GD", "res://.\\player.gd"])
        for alias in aliases:
            with self.subTest(alias=alias):
                with self.assertRaisesRegex(ValueError, "duplicate physical paths"):
                    history.record_batch_change(
                        self.root, "transaction", ["res://Player.gd", alias])
                self.assertEqual(self.snapshots(), {})
                self.assertFalse(self.journal.exists())

    def assert_blocked(self, entry):
        original = self.journal.read_bytes()
        contents = {path.name: path.read_bytes() for path in Path(self.root).iterdir() if path.is_file()}
        self.assertEqual(len(history.entry_info(self.root, entry)["newer_same_file"]), 1)
        for force in (False, True):
            result = history.rollback_entry(self.root, entry, force=force)
            self.assertFalse(result[0])
            self.assertFalse(result[2])
        self.assertEqual(self.journal.read_bytes(), original)
        self.assertEqual({path.name: path.read_bytes() for path in Path(self.root).iterdir()
                          if path.is_file()}, contents)

    def test_equivalent_path_spellings_block_rollback(self):
        old = self.record()
        history.commit_change(self.root, old)
        later = self.record("res://./Player.gd", chat_id="other")
        self.target.write_bytes(b"later\n")
        history.commit_change(self.root, later)
        self.assert_blocked(old)
        self.assertGreater(history.last_write_ts_by_others(self.root, "Player.gd", "mine"), 0)

    def test_move_source_and_destination_both_block(self):
        old = self.record()
        history.commit_change(self.root, old)
        move = history.record_change(self.root, {
            "action": "move_file", "path": "res://Player.gd", "dest": "res://Moved.gd",
        }, chat_id="other")
        os.replace(self.target, Path(self.root, "Moved.gd"))
        history.commit_change(self.root, move)
        self.assert_blocked(old)
        for path in ("Player.gd", "Moved.gd"):
            self.assertGreater(history.last_write_ts_by_others(self.root, path, "mine"), 0)
        for path in ("Player.gd", "Moved.gd"):
            with self.subTest(path=path):
                later = history.record_change(self.root, {
                    "action": "create_file", "path": "res://" + path,
                })
                Path(self.root, path).write_bytes(b"later\n")
                history.commit_change(self.root, later)
                self.assert_blocked(move)
                self.assertTrue(history.rollback_entry(self.root, later)[0])

    @unittest.skipUnless(os.name == "nt", "Windows case-insensitive path identity")
    def test_windows_case_aliases_block_batch_and_move_rollback(self):
        old = self.record(batch=True)
        history.commit_change(self.root, old)
        later = self.record("res://.\\PLAYER.GD", chat_id="other")
        self.target.write_bytes(b"later\n")
        history.commit_change(self.root, later)
        self.assert_blocked(old)
        self.assertGreater(history.last_write_ts_by_others(self.root, "res://player.gd", "mine"), 0)
        self.assertTrue(history.rollback_entry(self.root, later)[0])
        move = history.record_change(self.root, {
            "action": "move_file", "path": "res://PLAYER.GD", "dest": "res://Moved.gd",
        }, chat_id="other")
        os.replace(self.target, Path(self.root, "Moved.gd"))
        history.commit_change(self.root, move)
        self.assert_blocked(old)
        for path in ("res://player.gd", "res://MOVED.GD"):
            self.assertGreater(history.last_write_ts_by_others(self.root, path, "mine"), 0)
        later = history.record_change(self.root, {
            "action": "create_file", "path": "res://player.gd",
        })
        self.target.write_bytes(b"new source\n")
        history.commit_change(self.root, later)
        self.assert_blocked(move)


if __name__ == "__main__":
    unittest.main()
