# -*- coding: utf-8 -*-
"""Тесты карты архитектуры (arch_map.py): зоны, имена, вердикты, аудит.

Проверяемый контракт:
  * зоны сегментные: `*.gd` не ловит вложенные файлы, `**` ловит всё;
  * вердикт нового файла честный: дубль имени ядра — отказ, зона потребителя —
    предупреждение, зона deny — отказ, зона вне карты — предупреждение,
    отсутствие карты — предупреждение (не молчаливое «ок»);
  * check_names:false (тесты, n8n, per-site парсеры) отключает сверку имён;
  * поставленная карта аддона валидна и покрывает ключевые каталоги дерева.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import arch_map  # noqa: E402

ADDON = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

MINI_MAP = {
    "schema": 1,
    "core_dir": "python/godot_tools",
    "name_stoplist": ["main", "run"],
    "zones": [
        {"glob": "python/godot_tools/**", "role": "core", "new_files": "allow"},
        {"glob": "python/tests/**", "role": "tests", "new_files": "allow",
         "check_names": False},
        {"glob": "python/browser/**", "role": "consumer", "new_files": "warn",
         "hint": "вызовы ядра"},
        {"glob": "agent_api_cache/**", "role": "generated", "new_files": "deny",
         "hint": "генерируемое"},
        {"glob": "*.gd", "role": "godot-side", "new_files": "warn",
         "check_names": False},
        {"glob": "**", "role": "unknown", "new_files": "warn"},
    ],
}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arch_map_")
        self.addCleanup(self.temp.cleanup)
        self.addon = str(Path(self.temp.name, "addon"))
        Path(self.addon, "docs").mkdir(parents=True)
        self.write_map(MINI_MAP)

    def write_map(self, data):
        Path(self.addon, "docs", "architecture_map.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def write(self, rel, text):
        path = Path(self.addon, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class ZoneMatchingTests(Fixture):
    def test_first_match_wins_and_segments_do_not_cross(self):
        data = arch_map.load_map(self.addon)
        self.assertIsNotNone(data)
        cases = {
            "python/godot_tools/new.py": "core",
            "python/browser/x.py": "consumer",
            "python/tests/test_new.py": "tests",
            "agent_api_cache/classes.json": "generated",
            "panel.gd": "godot-side",
            "sub/panel.gd": "unknown",
            "weird/thing.py": "unknown",
        }
        for rel, role in cases.items():
            with self.subTest(path=rel):
                zone = arch_map.zone_for(data, rel)
                self.assertIsNotNone(zone, rel)
                self.assertEqual(zone.get("role"), role, rel)

    def test_missing_map_is_none(self):
        empty = tempfile.TemporaryDirectory(prefix="arch_nomap_")
        self.addCleanup(empty.cleanup)
        self.assertIsNone(arch_map.load_map(empty.name))

    def test_broken_map_is_none(self):
        Path(self.addon, "docs", "architecture_map.json").write_text(
            "{ не json", encoding="utf-8")
        self.assertIsNone(arch_map.load_map(self.addon))


class PublicNamesTests(unittest.TestCase):
    def test_top_level_only_and_private_skipped(self):
        text = ("def alpha():\n"
                "    def nested():\n"
                "        pass\n"
                "    return nested\n\n"
                "async def beta():\n"
                "    return 1\n\n"
                "class Gamma:\n"
                "    def method(self):\n"
                "        return 2\n\n"
                "def _private():\n"
                "    pass\n")
        self.assertEqual(arch_map.public_names(text),
                         [("alpha", "def"), ("beta", "def"), ("Gamma", "class")])

    def test_broken_python_is_none(self):
        self.assertIsNone(arch_map.public_names("def broken(:\n"))


class CheckNewFileTests(Fixture):
    def setUp(self):
        super().setUp()
        self.write("python/godot_tools/core_mod.py",
                   "def reticulate_splines():\n    return 1\n")

    def test_core_name_in_consumer_zone_is_error(self):
        errors, _warnings = arch_map.check_new_file(
            self.addon, "python/browser/helper.py",
            "def reticulate_splines():\n    return 2\n")
        self.assertTrue(errors)
        self.assertIn("reticulate_splines", errors[0])
        self.assertIn("ядре", errors[0])
        self.assertIn("core_mod.py", errors[0])

    def test_unique_consumer_name_warns_but_allows(self):
        errors, warnings = arch_map.check_new_file(
            self.addon, "python/browser/helper.py",
            "def sweep_scene_cache():\n    return 1\n")
        self.assertEqual(errors, [])
        joined = " ".join(warnings)
        self.assertIn("ядре", joined)
        self.assertIn("python/browser/helper.py", joined)

    def test_stoplist_names_do_not_collide(self):
        errors, _warnings = arch_map.check_new_file(
            self.addon, "python/browser/helper.py", "def main():\n    pass\n")
        self.assertEqual(errors, [])

    def test_core_new_file_passes_quietly(self):
        errors, warnings = arch_map.check_new_file(
            self.addon, "python/godot_tools/new_mod.py",
            "def brand_new_fn():\n    pass\n")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_core_duplicate_inside_core_is_error(self):
        errors, _warnings = arch_map.check_new_file(
            self.addon, "python/godot_tools/another.py",
            "def reticulate_splines():\n    return 3\n")
        self.assertTrue(errors)
        self.assertIn("core_mod.py", errors[0])

    def test_deny_zone_is_error_even_for_json(self):
        errors, _warnings = arch_map.check_new_file(
            self.addon, "agent_api_cache/classes.json", "{}")
        self.assertTrue(errors)
        self.assertIn("generated", errors[0])

    def test_tests_zone_skips_name_checks(self):
        errors, warnings = arch_map.check_new_file(
            self.addon, "python/tests/test_dup.py",
            "def reticulate_splines():\n    return 4\n")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_unknown_zone_warns(self):
        errors, warnings = arch_map.check_new_file(
            self.addon, "weird/thing.py", "def zz_unique():\n    pass\n")
        self.assertEqual(errors, [])
        self.assertIn("unknown", " ".join(warnings))

    def test_missing_map_warns_not_silent(self):
        fresh = tempfile.TemporaryDirectory(prefix="arch_nomap2_")
        self.addCleanup(fresh.cleanup)
        errors, warnings = arch_map.check_new_file(
            fresh.name, "python/browser/helper.py", "def x():\n    pass\n")
        self.assertEqual(errors, [])
        self.assertIn("не найдена", " ".join(warnings))

    def test_non_python_in_warn_zone_gets_zone_note(self):
        errors, warnings = arch_map.check_new_file(
            self.addon, "python/browser/notes.txt", "hello")
        self.assertEqual(errors, [])
        self.assertIn("python/browser/**", " ".join(warnings))

    def test_batch_collects_all_files(self):
        errors, _warnings, checked = arch_map.check_new_files(
            self.addon,
            [("python/browser/a.py", "def unique_a():\n    pass\n"),
             ("python/browser/b.py", "def reticulate_splines():\n    pass\n")])
        self.assertEqual(checked,
                         ["python/browser/a.py", "python/browser/b.py"])
        self.assertTrue(any("reticulate_splines" in item for item in errors))


class AuditTests(Fixture):
    def setUp(self):
        super().setUp()
        self.write("python/godot_tools/core_mod.py",
                   "def shared_fn():\n    pass\n\ndef unique_core():\n    pass\n")
        self.write("python/browser/a.py",
                   "def shared_fn():\n    pass\n\ndef only_a():\n    pass\n")
        self.write("python/browser/b.py", "def only_a():\n    pass\n")
        self.write("python/tests/test_x.py", "def shared_fn():\n    pass\n")
        self.write("weird/file.py", "def zzz_unknown():\n    pass\n")

    def test_audit_reports_core_and_consumer_duplicates(self):
        report = arch_map.audit(self.addon)
        core_names = {item["name"] for item in report["core_duplicates"]}
        self.assertIn("shared_fn", core_names)
        self.assertNotIn("unique_core", core_names)
        consumer_names = {item["name"] for item in report["consumer_duplicates"]}
        self.assertIn("only_a", consumer_names)

    def test_audit_skips_name_checks_disabled_zones(self):
        report = arch_map.audit(self.addon)
        for item in report["core_duplicates"]:
            for rel in item["outside"]:
                self.assertFalse(rel.startswith("python/tests/"), rel)

    def test_audit_lists_unknown_zone_files(self):
        report = arch_map.audit(self.addon)
        self.assertIn("weird/file.py", report["unknown_files"])


class ShippedMapTests(unittest.TestCase):
    def test_shipped_map_is_valid_and_covers_tree(self):
        data = arch_map.load_map(ADDON)
        self.assertIsNotNone(data, "docs/architecture_map.json не читается")
        self.assertGreaterEqual(len(data.get("zones") or []), 15)
        expected = {
            "python/godot_tools/new_mod.py": "core",
            "python/browser/x.py": "consumer",
            "python/server/x.py": "consumer",
            "python/tools/x.py": "consumer",
            "python/api/x.py": "consumer",
            "python/parsers/x.py": "consumer",
            "python/tests/test_new.py": "tests",
            "docs/ARCHITECTURE.md": "docs",
            "n8n/scripts/new_script.py": "workflow",
            "agent_api_cache/classes.json": "generated",
            "minilich_brain/dataset.jsonl": "generated",
            "python/dist/bundle/x.py": "generated",
            "panel_extra.gd": "godot-side",
            "elsewhere/thing.py": "unknown",
        }
        for rel, role in expected.items():
            with self.subTest(path=rel):
                zone = arch_map.zone_for(data, rel)
                self.assertIsNotNone(zone, rel)
                self.assertEqual(zone.get("role"), role, rel)

    def test_shipped_core_dir_exists(self):
        data = arch_map.load_map(ADDON)
        core = arch_map.core_dir_of(data).rstrip("/")
        self.assertTrue(os.path.isdir(os.path.join(ADDON, core)), core)


if __name__ == "__main__":
    unittest.main()
