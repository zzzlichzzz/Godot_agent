# -*- coding: utf-8 -*-
"""Step-2 audit regression tests: sync_references_after_external_move must
keep the project consistent after FileSystemDock moves and its rollback must
return the moved file/directory to the original location (audit 1.1, 2.1-2.4).
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import file_refactor
import history_manager


class ExternalMoveSync(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ext_move_sync_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "project.godot").write_text("config_version=5\n", encoding="utf-8")

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_bytes(self, rel, data):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def sync(self, old, new, is_directory=False):
        return file_refactor.sync_references_after_external_move(
            str(self.root), old, new, is_directory=is_directory)

    def rollback(self, entry_id):
        ok, message, _nf, _paths, _diff = history_manager.rollback_entry(
            str(self.root), entry_id)
        return ok, message

    # --- audit 1.1: rollback must move the file back ------------------------
    def test_rollback_restores_file_location(self):
        self.write("src/player.gd", "extends Node\nclass_name Player\n")
        self.write("src/player.gd.uid", "uid://player1\n")
        main = self.write("main.gd", 'extends Node\nconst P = preload("res://src/player.gd")\n')
        # External move, as FileSystemDock does it (file already on disk at dest).
        (self.root / "scripts").mkdir()
        (self.root / "src" / "player.gd").rename(self.root / "scripts" / "player.gd")
        (self.root / "src" / "player.gd.uid").rename(self.root / "scripts" / "player.gd.uid")

        res = self.sync("res://src/player.gd", "res://scripts/player.gd")
        self.assertTrue(res.get("entry_id"))
        self.assertIn('preload("res://scripts/player.gd")', main.read_text(encoding="utf-8"))

        ok, message = self.rollback(res["entry_id"])
        self.assertTrue(ok, message)
        self.assertTrue((self.root / "src" / "player.gd").exists())
        self.assertEqual((self.root / "src" / "player.gd.uid").read_text(encoding="utf-8"),
                         "uid://player1\n")
        self.assertFalse((self.root / "scripts" / "player.gd").exists())
        self.assertIn('preload("res://src/player.gd")', main.read_text(encoding="utf-8"))

    def test_rollback_available_even_without_references(self):
        self.write("src/lonely.gd", "extends Node\n")
        (self.root / "scripts").mkdir()
        (self.root / "src" / "lonely.gd").rename(self.root / "scripts" / "lonely.gd")

        res = self.sync("res://src/lonely.gd", "res://scripts/lonely.gd")
        self.assertTrue(res.get("entry_id"),
                        "rollback anchor must exist even with 0 updated references")

        ok, message = self.rollback(res["entry_id"])
        self.assertTrue(ok, message)
        self.assertTrue((self.root / "src" / "lonely.gd").exists())
        self.assertFalse((self.root / "scripts" / "lonely.gd").exists())

    def test_rollback_restores_import_companion(self):
        self.write_bytes("src/tex.png", b"\x89PNG\r\n\x1a\nfake")
        original_import = ("[remap]\n\nsource_file=\"res://src/tex.png\"\n"
                           "dest_files=[\"res://.godot/imported/tex.png-abc\"]\n")
        self.write("src/tex.png.import", original_import)
        (self.root / "assets").mkdir()
        (self.root / "src" / "tex.png").rename(self.root / "assets" / "tex.png")
        (self.root / "src" / "tex.png.import").rename(self.root / "assets" / "tex.png.import")

        res = self.sync("res://src/tex.png", "res://assets/tex.png")
        self.assertTrue(res.get("entry_id"))
        moved_import = self.root / "assets" / "tex.png.import"
        self.assertIn('source_file="res://assets/tex.png"',
                      moved_import.read_text(encoding="utf-8"))

        ok, message = self.rollback(res["entry_id"])
        self.assertTrue(ok, message)
        self.assertTrue((self.root / "src" / "tex.png").exists())
        self.assertEqual((self.root / "src" / "tex.png.import").read_text(encoding="utf-8"),
                         original_import)
        self.assertFalse((self.root / "assets" / "tex.png").exists())

    # --- audit 2.1: internal relative paths of the moved file ---------------
    def test_single_file_internal_relative_paths_fixed(self):
        self.write("base.gd", "extends Node\nclass_name Base\n")
        self.write("player.gd", 'extends "./base.gd"\n')
        (self.root / "sub").mkdir()
        (self.root / "player.gd").rename(self.root / "sub" / "player.gd")

        res = self.sync("res://player.gd", "res://sub/player.gd")
        self.assertTrue(res.get("entry_id"))
        text = (self.root / "sub" / "player.gd").read_text(encoding="utf-8")
        self.assertIn('extends "res://base.gd"', text)

    # --- audit 1.1/2.1/2.2/2.3: directory moves ------------------------------
    def test_directory_rollback_restores_tree(self):
        self.write("chars/hero.gd", "extends Node\nclass_name Hero\n")
        main = self.write("main.gd", 'extends Node\nconst H = preload("res://chars/hero.gd")\n')
        (self.root / "chars").rename(self.root / "loot")

        res = self.sync("res://chars", "res://loot", is_directory=True)
        self.assertTrue(res.get("entry_id"))
        self.assertIn('preload("res://loot/hero.gd")', main.read_text(encoding="utf-8"))

        ok, message = self.rollback(res["entry_id"])
        self.assertTrue(ok, message)
        self.assertTrue((self.root / "chars" / "hero.gd").exists())
        self.assertFalse((self.root / "loot").exists())
        self.assertIn('preload("res://chars/hero.gd")', main.read_text(encoding="utf-8"))

    def test_directory_internal_relative_paths_fixed(self):
        self.write("base.gd", "extends Node\nclass_name Base\n")
        self.write("chars/monster.gd", 'extends "../base.gd"\n')
        (self.root / "sub").mkdir()
        (self.root / "chars").rename(self.root / "sub" / "chars")

        res = self.sync("res://chars", "res://sub/chars", is_directory=True)
        self.assertTrue(res.get("entry_id"))
        text = (self.root / "sub" / "chars" / "monster.gd").read_text(encoding="utf-8")
        self.assertIn('extends "res://base.gd"', text)

    def test_directory_import_files_updated(self):
        self.write_bytes("chars/tex.png", b"\x89PNG\r\n\x1a\nfake")
        self.write("chars/tex.png.import",
                   "[remap]\n\nsource_file=\"res://chars/tex.png\"\n"
                   "dest_files=[\"res://.godot/imported/tex.png-abc\"]\n")
        (self.root / "chars").rename(self.root / "loot")

        res = self.sync("res://chars", "res://loot", is_directory=True)
        self.assertTrue(res.get("entry_id"))
        text = (self.root / "loot" / "tex.png.import").read_text(encoding="utf-8")
        self.assertIn('source_file="res://loot/tex.png"', text)
        self.assertNotIn("res://chars/tex.png", text)

    def test_directory_lint_guards_broken_replacement(self):
        # If applying the new prefix would break GDScript syntax, the file must
        # be skipped (with a warning), not written blindly (audit 2.3).
        self.write("chars/a.gd", "extends Node\n")
        victim = self.write("victim.gd",
                            'extends Node\nconst X = preload("res://chars/a.gd")\n')
        (self.root / "chars").rename(self.root / "loot")

        real_lint = file_refactor.gd_lint.lint_gdscript

        def fake_lint(text):
            if "res://loot/a.gd" in text:
                return ["simulated syntax error"]
            return real_lint(text)

        with patch.object(file_refactor.gd_lint, "lint_gdscript", side_effect=fake_lint):
            res = self.sync("res://chars", "res://loot", is_directory=True)
        self.assertTrue(res.get("ok"))
        self.assertIn('preload("res://chars/a.gd")', victim.read_text(encoding="utf-8"))


class DirectoryRelocationOffsets(unittest.TestCase):
    """Audit 2.4: several relative replacements in one file must not shift
    each other's character offsets."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rel_offsets_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "project.godot").write_text("config_version=5\n", encoding="utf-8")

    def test_multiple_relative_replacements_keep_offsets(self):
        chars = self.root / "chars"
        chars.mkdir()
        (chars / "a.gd").write_text("extends Node\n", encoding="utf-8")
        (chars / "bb.gd").write_text("extends Node\n", encoding="utf-8")
        view = self.root / "view.gd"
        view.write_text(
            "extends Node\n"
            'const A = preload("chars/a.gd")\n'
            'const B = preload("chars/bb.gd")\n',
            encoding="utf-8",
        )

        prep = file_refactor.prepare_file_rename(str(self.root), "res://chars", "res://x")
        file_refactor.apply_prepared_file_rename(str(self.root), prep)

        text = view.read_text(encoding="utf-8")
        self.assertIn('preload("res://x/a.gd")', text)
        self.assertIn('preload("res://x/bb.gd")', text)
        self.assertEqual(file_refactor.gd_lint.lint_gdscript(text), [])


if __name__ == "__main__":
    unittest.main()

