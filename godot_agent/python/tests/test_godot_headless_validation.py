# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

import _bootstrap  # noqa: E402,F401
import godot_headless_validation as validation  # noqa: E402


FAKE_GODOT = r'''# -*- coding: utf-8 -*-
import json, os, sys, time
root = sys.argv[sys.argv.index("--path") + 1]
service = os.path.join(root, ".godot_agent_validation")
with open(os.path.join(service, "manifest.json"), "r", encoding="utf-8") as handle:
    manifest = json.load(handle)
diagnostics = []
for target in manifest.get("targets", []):
    path = os.path.join(root, target[6:].replace("/", os.sep))
    if not os.path.isfile(path):
        diagnostics.append({"severity": "error", "category": "load", "path": target,
                            "message": "Resource does not exist"})
        continue
    with open(path, "rb") as handle:
        content = handle.read()
    if b"SLEEP_VALIDATION" in content:
        time.sleep(5)
    if b"ENGINE_ERROR" in content:
        diagnostics.append({"severity": "error", "category": "parse", "path": target,
                            "message": "Synthetic engine parse failure"})
with open(os.path.join(service, "result.json"), "w", encoding="utf-8") as handle:
    json.dump({"diagnostics": diagnostics}, handle)
sys.exit(1 if diagnostics else 0)
'''


class HeadlessValidationTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="godot-headless-project-")
        self.temp = tempfile.mkdtemp(prefix="godot-headless-runs-")
        with open(os.path.join(self.root, "project.godot"), "w", encoding="utf-8") as handle:
            handle.write("[application]\nconfig/name=\"Validation\"\n")
        self.script = os.path.join(self.root, "player.gd")
        with open(self.script, "w", encoding="utf-8") as handle:
            handle.write("extends Node\nfunc ready():\n\tpass\n")
        self.fake = os.path.join(self.temp, "fake_godot.py")
        with open(self.fake, "w", encoding="utf-8") as handle:
            handle.write(FAKE_GODOT)
        self.harness = os.path.abspath(os.path.join(PYTHON_DIR, os.pardir,
                                                     "agent_headless_validator.gd"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.temp, ignore_errors=True)

    def validate(self, action, **kwargs):
        batch = validation.batch_from_action(self.root, action)
        receipt = validation.validate_batch(
            self.root, batch, mode="required", command_prefix=[sys.executable, self.fake],
            harness_path=self.harness, temp_root=self.temp, **kwargs)
        return batch, receipt

    def test_overlay_passes_without_mutating_project_and_receipt_verifies(self):
        with open(self.script, "rb") as handle:
            before = handle.read()
        action = {"action": "patch_file", "path": "res://player.gd",
                  "search": "\tpass", "replace": "\tprint(\"ok\")"}
        batch, receipt = self.validate(action)
        self.assertEqual("passed", receipt["report"]["status"])
        self.assertFalse(receipt["report"]["blocking"])
        with open(self.script, "rb") as handle:
            self.assertEqual(before, handle.read())
        self.assertTrue(validation.verify_receipt(self.root, batch, receipt))
        leftovers = [name for name in os.listdir(self.temp)
                     if name.startswith("godot_agent_validation_")]
        self.assertEqual([], leftovers)

    def test_new_engine_error_blocks_but_preexisting_error_is_subtracted(self):
        action = {"action": "patch_file", "path": "res://player.gd",
                  "search": "\tpass", "replace": "\tENGINE_ERROR"}
        _batch, receipt = self.validate(action)
        self.assertEqual("failed", receipt["report"]["status"])
        self.assertTrue(receipt["report"]["blocking"])
        self.assertEqual(1, len(receipt["report"]["new_diagnostics"]))

        with open(self.script, "w", encoding="utf-8") as handle:
            handle.write("extends Node\n# ENGINE_ERROR\nfunc ready():\n\tpass\n")
        action = {"action": "patch_file", "path": "res://player.gd",
                  "search": "\tpass", "replace": "\tprint(\"still broken\")"}
        _batch, receipt = self.validate(action)
        self.assertEqual("passed", receipt["report"]["status"])
        self.assertFalse(receipt["report"]["new_diagnostics"])
        self.assertEqual(1, len(receipt["report"]["pre_existing_diagnostics"]))

    def test_timeout_and_unavailable_required_are_blocking(self):
        action = {"action": "patch_file", "path": "res://player.gd",
                  "search": "\tpass", "replace": "\tSLEEP_VALIDATION"}
        _batch, receipt = self.validate(action, timeout=0.1)
        self.assertTrue(receipt["report"]["blocking"])
        self.assertIn(receipt["report"]["status"], ("failed", "inconclusive"))
        batch = validation.batch_from_action(self.root, action)
        receipt = validation.validate_batch(self.root, batch, mode="required", executable="")
        self.assertEqual("unavailable", receipt["report"]["status"])
        self.assertTrue(receipt["report"]["blocking"])

    def test_receipt_detects_stale_source_and_move_carries_uid(self):
        action = {"action": "patch_file", "path": "res://player.gd",
                  "search": "\tpass", "replace": "\tprint(1)"}
        batch, receipt = self.validate(action)
        with open(self.script, "a", encoding="utf-8") as handle:
            handle.write("# external\n")
        with self.assertRaises(validation.StaleValidationError):
            validation.verify_receipt(self.root, batch, receipt)

        with open(self.script, "w", encoding="utf-8") as handle:
            handle.write("extends Node\n")
        with open(self.script + ".uid", "w", encoding="ascii") as handle:
            handle.write("uid://test")
        batch, receipt = self.validate({"action": "move_file", "path": "res://player.gd",
                                        "dest": "res://renamed.gd"})
        self.assertEqual("passed", receipt["report"]["status"])
        self.assertTrue(validation.verify_receipt(self.root, batch, receipt))
        self.assertTrue(os.path.isfile(self.script))
        self.assertTrue(os.path.isfile(self.script + ".uid"))

    def test_changed_script_adds_resource_referencers_to_targets(self):
        scene = os.path.join(self.root, "main.tscn")
        with open(scene, "w", encoding="utf-8") as handle:
            handle.write('[gd_scene load_steps=2 format=3]\n\n[ext_resource path="res://player.gd" type="Script" id="1"]\n')
        batch = validation.batch_from_action(self.root, {
            "action": "patch_file", "path": "res://player.gd",
            "search": "\tpass", "replace": "\tprint(1)",
        })
        self.assertIn("res://main.tscn", batch["targets"])

    def test_explicit_checks_block_preexisting_errors_without_writes(self):
        with open(self.script, "w", encoding="utf-8") as handle:
            handle.write("extends Node\n# ENGINE_ERROR\n")
        batch = validation.make_batch("transaction", [], ["res://player.gd"], {},
                                      required_targets=["res://player.gd"])
        receipt = validation.validate_batch(
            self.root, batch, mode="auto", command_prefix=[sys.executable, self.fake],
            harness_path=self.harness, temp_root=self.temp)
        self.assertTrue(receipt["report"]["blocking"])
        self.assertTrue(receipt["report"]["check_diagnostics"])
        self.assertFalse(receipt["report"]["new_diagnostics"])
        with patch.object(validation, "discover_executable", return_value=None):
            unavailable = validation.validate_batch(self.root, batch, mode="off")
        self.assertEqual(unavailable["report"]["status"], "unavailable")
        self.assertTrue(unavailable["report"]["blocking"])

    def test_referencer_change_invalidates_validation_receipt(self):
        scene = os.path.join(self.root, "main.tscn")
        with open(scene, "w", encoding="utf-8") as handle:
            handle.write('[gd_scene format=3]\n# res://player.gd\n')
        batch, receipt = self.validate({"action": "patch_file", "path": "res://player.gd",
                                       "search": "pass", "replace": "print(1)"})
        self.assertIn("res://main.tscn", receipt["source_hashes"])
        with open(scene, "a", encoding="utf-8") as handle:
            handle.write("# externally changed\n")
        with self.assertRaises(validation.StaleValidationError):
            validation.verify_receipt(self.root, batch, receipt)

    def test_stale_source_during_copy_and_missing_harness_fail_closed(self):
        action = {"action": "patch_file", "path": "res://player.gd", "search": "pass", "replace": "print(1)"}
        batch = validation.batch_from_action(self.root, action)
        with open(self.script, "a", encoding="utf-8") as handle:
            handle.write("# outside edit\n")
        with self.assertRaises(validation.StaleValidationError):
            validation.validate_batch(self.root, batch, command_prefix=[sys.executable, self.fake],
                                      harness_path=self.harness, temp_root=self.temp)
        with open(self.fake, "w", encoding="utf-8") as handle:
            handle.write("# exits zero but returns no validation result\n")
        _, receipt = self.validate(action)
        self.assertTrue(receipt["report"]["blocking"])
        self.assertEqual(receipt["report"]["status"], "inconclusive")


if __name__ == "__main__":
    unittest.main()
