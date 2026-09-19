"""Exercise the production baseline/candidate validator with an explicit real Godot."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _bootstrap  # noqa: E402,F401
import godot_headless_validation as validation  # noqa: E402


class LiveValidatorTests(unittest.TestCase):
    executable = None

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="validator-live-")
        self.addCleanup(self.temp.cleanup)
        self.owner = Path(self.temp.name)
        self.root = self.owner / "project with spaces \u0442\u0435\u0441\u0442"
        self.root.mkdir()
        (self.root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Validator sandbox"\n', encoding="utf-8")
        self.script = self.root / "player.gd"
        self.script.write_text("extends Node\nfunc ready():\n\tpass\n", encoding="utf-8")

    def validate(self, batch):
        before = {str(p.relative_to(self.root)): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        receipt = validation.validate_batch(str(self.root), batch, executable=self.executable,
                                            mode="required", temp_root=str(self.owner))
        after = {str(p.relative_to(self.root)): p.read_bytes()
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after, "Validation must not write to the source project")
        self.assertEqual([], list(self.owner.glob("godot_agent_validation_*")))
        return receipt

    def patch_batch(self, replacement):
        return validation.batch_from_action(str(self.root), {
            "action": "patch_file", "path": "res://player.gd",
            "search": "\tpass", "replace": replacement})

    def test_valid_candidate_and_stale_receipt(self):
        batch = self.patch_batch('\tprint("ok")')
        receipt = self.validate(batch)
        self.assertEqual("passed", receipt["report"]["status"], receipt)
        self.assertTrue(validation.verify_receipt(str(self.root), batch, receipt))
        self.script.write_text("extends Node\n# external edit\n", encoding="utf-8")
        with self.assertRaises(validation.StaleValidationError):
            validation.verify_receipt(str(self.root), batch, receipt)

    def test_new_parse_error_blocks(self):
        receipt = self.validate(self.patch_batch("\tvar broken = )"))
        self.assertEqual("passed", receipt["report"]["baseline_status"], receipt)
        self.assertTrue(receipt["report"]["blocking"], receipt)
        self.assertTrue(receipt["report"]["new_diagnostics"], receipt)

    def test_baseline_error_subtracted_but_explicit_check_blocks(self):
        self.script.write_text("extends Node\nfunc ready():\n\tvar broken = )\n# marker\n", encoding="utf-8")
        batch = validation.batch_from_action(str(self.root), {
            "action": "patch_file", "path": "res://player.gd",
            "search": "# marker", "replace": "# unrelated edit"})
        receipt = self.validate(batch)
        self.assertEqual("passed", receipt["report"]["status"], receipt)
        self.assertTrue(receipt["report"]["pre_existing_diagnostics"], receipt)
        check = validation.make_batch("transaction", [], ["res://player.gd"], {},
                                      required_targets=["res://player.gd"])
        receipt = self.validate(check)
        self.assertTrue(receipt["report"]["blocking"], receipt)
        self.assertTrue(receipt["report"]["check_diagnostics"], receipt)

    def test_move_breaking_scene_reference_blocks(self):
        (self.root / "main.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource type="Script" path="res://player.gd" id="1"]\n'
            '[node name="Main" type="Node"]\nscript = ExtResource("1")\n', encoding="utf-8")
        batch = validation.batch_from_action(str(self.root), {
            "action": "move_file", "path": "res://player.gd", "dest": "res://renamed.gd"})
        self.assertIn("res://main.tscn", batch["targets"])
        receipt = self.validate(batch)
        self.assertIn("res://main.tscn", receipt["source_hashes"])
        self.assertTrue(receipt["report"]["blocking"], receipt)

    def test_missing_explicit_resource_blocks(self):
        batch = validation.make_batch("transaction", [], ["res://missing.tres"], {},
                                      required_targets=["res://missing.tres"])
        receipt = self.validate(batch)
        self.assertTrue(receipt["report"]["blocking"], receipt)
        self.assertTrue(receipt["report"]["check_diagnostics"], receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True)
    args, remaining = parser.parse_known_args()
    LiveValidatorTests.executable = str(Path(args.godot).resolve(strict=True))
    unittest.main(argv=[sys.argv[0]] + remaining)
