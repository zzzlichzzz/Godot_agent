# -*- coding: utf-8 -*-
"""Step-3 audit regression tests: parallel external move sync must not fail
with StaleFileRefactorError (audit 1.4), and the agent's move_file plan step
must update references like a safe rename (audit 2.5).
"""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import file_refactor
import history_manager


class ParallelExternalMoveSync(unittest.TestCase):
    """Audit 1.4: Godot fires files_moved per file; two files referenced by the
    same scene arrive as two parallel post_move_sync requests."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="move_race_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
        src = self.root / "src"
        src.mkdir()
        (src / "a.gd").write_text("extends Node\n", encoding="utf-8")
        (src / "b.gd").write_text("extends Node\n", encoding="utf-8")
        self.main = self.root / "main.gd"
        self.main.write_text(
            "extends Node\n"
            'const A = preload("res://src/a.gd")\n'
            'const B = preload("res://src/b.gd")\n',
            encoding="utf-8",
        )
        moved = self.root / "moved"
        moved.mkdir()
        (src / "a.gd").rename(moved / "a.gd")
        (src / "b.gd").rename(moved / "b.gd")

    def test_parallel_moves_update_same_file_without_stale_errors(self):
        real_find = file_refactor.find_file_references

        def slow_find(*args, **kwargs):
            # Widen the scan window so both requests read main.gd before
            # either applies its patch (pre-fix: guaranteed stale failure).
            time.sleep(0.3)
            return real_find(*args, **kwargs)

        def worker(old, new):
            return file_refactor.sync_references_after_external_move(
                str(self.root), old, new)

        with patch.object(file_refactor, "find_file_references", side_effect=slow_find):
            with ThreadPoolExecutor(max_workers=2) as pool:
                f1 = pool.submit(worker, "res://src/a.gd", "res://moved/a.gd")
                f2 = pool.submit(worker, "res://src/b.gd", "res://moved/b.gd")
                r1 = f1.result()
                r2 = f2.result()

        self.assertTrue(r1.get("ok"))
        self.assertTrue(r2.get("ok"))
        text = self.main.read_text(encoding="utf-8")
        self.assertIn('preload("res://moved/a.gd")', text)
        self.assertIn('preload("res://moved/b.gd")', text)
        self.assertNotIn("res://src/a.gd", text)
        self.assertNotIn("res://src/b.gd", text)

    def test_sequential_moves_still_work(self):
        r1 = file_refactor.sync_references_after_external_move(
            str(self.root), "res://src/a.gd", "res://moved/a.gd")
        r2 = file_refactor.sync_references_after_external_move(
            str(self.root), "res://src/b.gd", "res://moved/b.gd")
        self.assertTrue(r1.get("ok"))
        self.assertTrue(r2.get("ok"))
        text = self.main.read_text(encoding="utf-8")
        self.assertIn('preload("res://moved/a.gd")', text)
        self.assertIn('preload("res://moved/b.gd")', text)
class AgentMoveFileUpdatesReferences(unittest.TestCase):
    """Audit 2.5: the agent's move_file plan step used to leave every
    reference in the project dangling."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent_move_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
        src = self.root / "src"
        src.mkdir()
        (src / "player.gd").write_text("extends Node\nclass_name Player\n", encoding="utf-8")
        (src / "player.gd.uid").write_text("uid://player1\n", encoding="utf-8")
        self.main = self.root / "main.gd"
        self.main.write_text(
            "extends Node\nconst P = preload(\"res://src/player.gd\")\n",
            encoding="utf-8",
        )

    def _apply(self, action):
        import main
        with patch.dict(main.STATE, {"project_root": str(self.root), "addon_intent": False}), \
                patch.object(main, "_current_chat_info", return_value=("test-chat", "test")):
            return main._apply_write_step(action, str(self.root))

    def test_move_file_step_updates_references(self):
        result = self._apply({"action": "move_file",
                              "path": "res://src/player.gd",
                              "dest": "res://src/hero.gd"})
        self.assertTrue(result.get("ok"), result.get("message"))
        self.assertTrue(result.get("entry_id"))
        self.assertIn('preload("res://src/hero.gd")', self.main.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "src" / "player.gd").exists())
        self.assertTrue((self.root / "src" / "hero.gd").exists())
        self.assertEqual((self.root / "src" / "hero.gd.uid").read_text(encoding="utf-8"),
                         "uid://player1\n")

        # The journal entry must roll the whole thing back (file + references).
        ok, message = history_manager.rollback_entry(str(self.root), result["entry_id"])[:2]
        self.assertTrue(ok, message)
        self.assertTrue((self.root / "src" / "player.gd").exists())
        self.assertIn('preload("res://src/player.gd")', self.main.read_text(encoding="utf-8"))

    def test_move_file_step_reports_existing_destination(self):
        (self.root / "src" / "hero.gd").write_text("extends Node\n", encoding="utf-8")
        result = self._apply({"action": "move_file",
                              "path": "res://src/player.gd",
                              "dest": "res://src/hero.gd"})
        self.assertFalse(result.get("ok"))
        self.assertTrue((self.root / "src" / "player.gd").exists())


if __name__ == "__main__":
    unittest.main()
