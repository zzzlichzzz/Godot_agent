# -*- coding: utf-8 -*-
"""Step-1 audit regression tests: directory self-nesting, companion files on
directory moves, case-only renames on Windows, and os.link fallbacks.

Every test here encodes the EXPECTED behaviour after the fix; tests that fail
on the pre-fix code reproduce the audited bugs (no Godot process needed).
"""
import errno
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import file_refactor
import project_tools


class _ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="move_dir_safety_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "project.godot").write_text("config_version=5\n", encoding="utf-8")

        self.chars = self.root / "chars"
        (self.chars / "enemies").mkdir(parents=True)

        self.hero = self.chars / "hero.gd"
        self.hero.write_text("extends Node\nclass_name Hero\n", encoding="utf-8")
        self.hero_uid = self.chars / "hero.gd.uid"
        self.hero_uid.write_text("uid://hero123\n", encoding="utf-8")

        self.goblin = self.chars / "enemies" / "goblin.gd"
        self.goblin.write_text("extends Node\n", encoding="utf-8")
        self.goblin_uid = self.chars / "enemies" / "goblin.gd.uid"
        self.goblin_uid.write_text("uid://goblin456\n", encoding="utf-8")

        self.tex = self.chars / "tex.png"
        self.tex.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        self.tex_import = self.chars / "tex.png.import"
        self.tex_import.write_text(
            "[remap]\n\nsource_file=\"res://chars/tex.png\"\ndest_files=[\"res://.godot/imported/tex.png-abc\"]\n",
            encoding="utf-8",
        )

        self.main_gd = self.root / "main.gd"
        self.main_gd.write_text(
            "extends Node\n"
            "const Hero = preload(\"res://chars/hero.gd\")\n"
            "var tex = load(\"res://chars/tex.png\")\n",
            encoding="utf-8",
        )

    def move_dir(self, old="res://chars", new="res://heroes"):
        prep = file_refactor.prepare_file_rename(str(self.root), old, new)
        return file_refactor.apply_prepared_file_rename(str(self.root), prep)


class DirectorySelfNesting(_ProjectFixture):
    """Audit 1.2: moving a folder into itself must be rejected, never rmtree'd."""

    def test_move_into_own_subdirectory_raises_and_preserves_everything(self):
        with self.assertRaises(file_refactor.FileRefactorError):
            self.move_dir("res://chars", "res://chars/heroes")
        self.assertEqual(self.hero.read_text(encoding="utf-8"), "extends Node\nclass_name Hero\n")
        self.assertEqual(self.hero_uid.read_text(encoding="utf-8"), "uid://hero123\n")
        self.assertTrue(self.goblin.exists())
        self.assertTrue(self.tex.exists())
        self.assertFalse((self.chars / "heroes").exists())

    def test_move_into_deeper_own_subdirectory_raises(self):
        for dest in ("res://chars/heroes/warriors", "res://chars/enemies"):
            with self.subTest(dest=dest):
                with self.assertRaises(file_refactor.FileRefactorError):
                    self.move_dir("res://chars", dest)
                self.assertTrue(self.hero.exists())
                self.assertTrue(self.goblin.exists())

    def test_move_into_itself_raises(self):
        with self.assertRaises(file_refactor.FileRefactorError):
            self.move_dir("res://chars", "res://chars")
        self.assertTrue(self.hero.exists())

    def test_move_to_sibling_still_works(self):
        res = self.move_dir("res://chars", "res://heroes")
        self.assertTrue(res.get("entry_id"))
        self.assertFalse(self.chars.exists())
        self.assertTrue((self.root / "heroes" / "hero.gd").exists())
        self.assertIn('preload("res://heroes/hero.gd")',
                      self.main_gd.read_text(encoding="utf-8"))

    def test_untracked_leftovers_are_not_deleted_with_old_dir(self):
        # Files skipped by the walk (e.g. inside a .godot subdir of the moved
        # folder) must survive: silent deletion is data loss.
        hidden = self.chars / ".godot"
        hidden.mkdir()
        cache = hidden / "cache.bin"
        cache.write_bytes(b"editor cache")
        self.move_dir("res://chars", "res://heroes")
        self.assertEqual(cache.read_bytes(), b"editor cache")


class DirectoryMoveCompanions(_ProjectFixture):
    """Audit 1.3 / 2.2 (prepare path): companion .uid/.import survive moves."""

    def test_uid_files_follow_their_assets(self):
        self.move_dir("res://chars", "res://heroes")
        heroes = self.root / "heroes"
        self.assertEqual((heroes / "hero.gd.uid").read_text(encoding="utf-8"), "uid://hero123\n")
        self.assertEqual((heroes / "enemies" / "goblin.gd.uid").read_text(encoding="utf-8"),
                         "uid://goblin456\n")
        self.assertFalse((self.chars / "hero.gd.uid").exists())

    def test_import_files_move_and_update_source_file(self):
        self.move_dir("res://chars", "res://heroes")
        moved = self.root / "heroes" / "tex.png.import"
        self.assertTrue(moved.exists())
        text = moved.read_text(encoding="utf-8")
        self.assertIn('source_file="res://heroes/tex.png"', text)
        self.assertNotIn("res://chars/tex.png", text)
        self.assertTrue((self.root / "heroes" / "tex.png").exists())


@unittest.skipUnless(os.name == "nt", "case-only rename matters on case-insensitive Windows FS")
class CaseOnlyRenameWindows(_ProjectFixture):
    """Audit 4.1: player.gd -> Player.gd must work instead of FileExistsError."""

    def test_move_project_file_case_only(self):
        project_tools.move_project_file(str(self.root), "res://chars/hero.gd", "res://chars/Hero.gd")
        names = os.listdir(self.chars)
        self.assertIn("Hero.gd", names)
        self.assertIn("Hero.gd.uid", names)
        self.assertNotIn("hero.gd", names)
        self.assertNotIn("hero.gd.uid", names)
        self.assertEqual((self.chars / "Hero.gd").read_text(encoding="utf-8"),
                         "extends Node\nclass_name Hero\n")

    def test_prepare_and_apply_case_only_rename_updates_references(self):
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://chars/hero.gd", "res://chars/Hero.gd"
        )
        res = file_refactor.apply_prepared_file_rename(str(self.root), prep)
        self.assertTrue(res.get("entry_id"))
        names = os.listdir(self.chars)
        self.assertIn("Hero.gd", names)
        self.assertNotIn("hero.gd", names)
        self.assertIn('preload("res://chars/Hero.gd")',
                      self.main_gd.read_text(encoding="utf-8"))

    def test_identical_path_still_rejected(self):
        with self.assertRaises((FileExistsError, file_refactor.FileRefactorError)):
            project_tools.move_project_file(str(self.root), "res://chars/hero.gd", "res://chars/hero.gd")
        self.assertTrue(self.hero.exists())

    def test_case_only_rename_rollback_restores_old_casing(self):
        prep = file_refactor.prepare_file_rename(
            str(self.root), "res://chars/hero.gd", "res://chars/Hero.gd"
        )
        res = file_refactor.apply_prepared_file_rename(str(self.root), prep)
        self.assertIn("Hero.gd", os.listdir(self.chars))

        import history_manager
        ok, message, _needs_force, _paths, _diff = history_manager.rollback_entry(
            str(self.root), res["entry_id"]
        )
        self.assertTrue(ok, message)
        names = os.listdir(self.chars)
        self.assertIn("hero.gd", names)
        self.assertIn("hero.gd.uid", names)
        self.assertNotIn("Hero.gd", names)
        self.assertEqual((self.chars / "hero.gd").read_text(encoding="utf-8"),
                         "extends Node\nclass_name Hero\n")
        self.assertIn('preload("res://chars/hero.gd")',
                      self.main_gd.read_text(encoding="utf-8"))


@unittest.skipUnless(os.name == "nt", "case-only directory rename needs a case-insensitive FS")
class DirectoryCaseOnlyRenameWindows(_ProjectFixture):
    """Case-only directory rename (res://chars -> res://Chars) must work.

    Pre-fix, realpath collapses both paths to the on-disk casing on Windows, so
    the self-nesting guard fired ('Нельзя переместить папку внутрь самой себя')
    and the destination-exists guard saw the source directory itself.
    """

    def test_prepare_case_only_dir_rename_does_not_raise(self):
        prep = file_refactor.prepare_file_rename(str(self.root), "res://chars", "res://Chars")
        self.assertTrue(prep.get("is_directory"))

    def test_apply_renames_directory_entry_and_preserves_everything(self):
        res = self.move_dir("res://chars", "res://Chars")
        self.assertTrue(res.get("entry_id"))
        names = os.listdir(self.root)
        self.assertIn("Chars", names)
        self.assertNotIn("chars", names)
        renamed = self.root / "Chars"
        self.assertEqual((renamed / "hero.gd").read_text(encoding="utf-8"),
                         "extends Node\nclass_name Hero\n")
        self.assertEqual((renamed / "hero.gd.uid").read_text(encoding="utf-8"), "uid://hero123\n")
        self.assertEqual((renamed / "enemies" / "goblin.gd").read_text(encoding="utf-8"),
                         "extends Node\n")
        self.assertEqual((renamed / "enemies" / "goblin.gd.uid").read_text(encoding="utf-8"),
                         "uid://goblin456\n")
        self.assertTrue((renamed / "tex.png").exists())
        self.assertTrue((renamed / "tex.png.import").exists())

    def test_case_only_dir_rename_updates_references_and_import(self):
        self.move_dir("res://chars", "res://Chars")
        main_text = self.main_gd.read_text(encoding="utf-8")
        self.assertIn('preload("res://Chars/hero.gd")', main_text)
        self.assertIn('load("res://Chars/tex.png")', main_text)
        self.assertNotIn("res://chars/", main_text)
        imp_text = (self.root / "Chars" / "tex.png.import").read_text(encoding="utf-8")
        self.assertIn('source_file="res://Chars/tex.png"', imp_text)
        self.assertNotIn("res://chars/tex.png", imp_text)

    def test_case_only_dir_rename_rollback_restores_casing(self):
        res = self.move_dir("res://chars", "res://Chars")
        self.assertIn("Chars", os.listdir(self.root))

        import history_manager
        ok, message, _needs_force, _paths, _diff = history_manager.rollback_entry(
            str(self.root), res["entry_id"]
        )
        self.assertTrue(ok, message)
        names = os.listdir(self.root)
        self.assertIn("chars", names)
        self.assertNotIn("Chars", names)
        self.assertEqual((self.chars / "hero.gd").read_text(encoding="utf-8"),
                         "extends Node\nclass_name Hero\n")
        self.assertIn('preload("res://chars/hero.gd")',
                      self.main_gd.read_text(encoding="utf-8"))

    def test_self_nesting_guard_still_works_with_different_case(self):
        # The case-only bypass must not reopen the self-nesting hole.
        with self.assertRaises(file_refactor.FileRefactorError):
            self.move_dir("res://chars", "res://CHARS/heroes")
        self.assertTrue(self.hero.exists())

    def test_existing_other_directory_conflict_still_raises(self):
        (self.root / "heroes").mkdir()
        with self.assertRaises(FileExistsError):
            self.move_dir("res://chars", "res://Heroes")
        self.assertTrue(self.hero.exists())


class HardlinkFallback(_ProjectFixture):
    """Audit 4.2: os.link is unavailable on FAT32/exFAT and across volumes."""

    def _deny_links(self, err):
        def deny(source, target):
            raise OSError(err, os.strerror(err) if err else "links unsupported")
        return deny

    def test_cross_device_move_falls_back_to_exclusive_copy(self):
        with patch.object(project_tools.os, "link",
                          side_effect=self._deny_links(errno.EXDEV)):
            project_tools.move_project_file(str(self.root), "res://chars/hero.gd",
                                            "res://moved/Hero.gd")
        dest = self.root / "moved" / "Hero.gd"
        self.assertEqual(dest.read_text(encoding="utf-8"), "extends Node\nclass_name Hero\n")
        self.assertEqual((self.root / "moved" / "Hero.gd.uid").read_text(encoding="utf-8"),
                         "uid://hero123\n")
        self.assertFalse(self.hero.exists())
        self.assertFalse(self.hero_uid.exists())

    def test_fat32_eperm_and_eacces_trigger_fallback(self):
        for err in (errno.EPERM, errno.EACCES):
            with self.subTest(err=err):
                with patch.object(project_tools.os, "link", side_effect=self._deny_links(err)):
                    project_tools.move_project_file(str(self.root), "res://chars/hero.gd",
                                                    "res://moved/Hero.gd")
                dest = self.root / "moved" / "Hero.gd"
                self.assertEqual(dest.read_text(encoding="utf-8"), "extends Node\nclass_name Hero\n")
                self.assertFalse(self.hero.exists())
                # restore fixture for the next iteration
                project_tools.move_project_file(str(self.root), "res://moved/Hero.gd",
                                                "res://chars/hero.gd")

    def test_fallback_still_never_clobbers_existing_destination(self):
        (self.root / "moved").mkdir()
        (self.root / "moved" / "Hero.gd").write_bytes(b"unrelated")
        with patch.object(project_tools.os, "link", side_effect=self._deny_links(errno.EXDEV)):
            with self.assertRaises(FileExistsError):
                project_tools.move_project_file(str(self.root), "res://chars/hero.gd",
                                                "res://moved/Hero.gd")
        self.assertEqual((self.root / "moved" / "Hero.gd").read_bytes(), b"unrelated")
        self.assertTrue(self.hero.exists())

    def test_fallback_locked_source_leaves_no_partial_copies(self):
        real_unlink = os.unlink

        def locked_source(path):
            if Path(path) == self.hero:
                raise PermissionError(errno.EACCES, "file in use (WinError 32)")
            return real_unlink(path)

        with patch.object(project_tools.os, "link", side_effect=self._deny_links(errno.EXDEV)), \
                patch.object(project_tools.os, "unlink", side_effect=locked_source):
            with self.assertRaises(PermissionError):
                project_tools.move_project_file(str(self.root), "res://chars/hero.gd",
                                                "res://moved/Hero.gd")
        self.assertEqual(self.hero.read_text(encoding="utf-8"), "extends Node\nclass_name Hero\n")
        self.assertFalse((self.root / "moved" / "Hero.gd").exists())
        self.assertFalse((self.root / "moved" / "Hero.gd.uid").exists())


if __name__ == "__main__":
    unittest.main()

