# -*- coding: utf-8 -*-
"""Интеграционный тест Flask-роутов «пилы» .gd: scan -> plan -> apply.

Контракт, который здесь закрепляется:
  * scan и plan НИЧЕГО не пишут на диск (plan только кладёт prepared в STATE);
  * apply пишет модули и донора одной транзакцией журнала (entry_id);
  * пила .gd работает только с .gd-файлами собственного аддона агента,
    и только при наличии прав (allow_self_edit + addon_dir);
  * apply без подготовленного плана — 409, а не молчаливая запись.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import main  # noqa: E402
import server_state as S  # noqa: E402

DONOR = ("extends Node\n"
         "\n"
         "\n"
         "func split_gd_probe_alpha() -> int:\n"
         "\treturn 1\n"
         "\n"
         "\n"
         "func split_gd_probe_beta() -> int:\n"
         "\treturn 2\n"
         "\n"
         "\n"
         "func split_gd_probe_gamma() -> int:\n"
         "\treturn 3\n")

DONOR_RES = "res://addons/Godot_agent/godot_agent/split_gd_probe.gd"
MODULE_RES = "res://addons/Godot_agent/godot_agent/split_gd_probe_part1.gd"


class SplitGdFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="split_gd_flow_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "project.godot").write_text(
            'config_version=5\n\n[application]\nconfig/name="SplitGdFlow"\n',
            encoding="utf-8")
        self.addon = self.root / "addons" / "Godot_agent" / "godot_agent"
        self.addon.mkdir(parents=True)
        self.donor = self.addon / "split_gd_probe.gd"
        self.donor.write_text(DONOR, encoding="utf-8")
        self.module = self.addon / "split_gd_probe_part1.gd"

        self._saved = {key: S.STATE.get(key) for key in (
            "project_root", "addon_dir", "allow_addons", "allow_self_edit",
            "pending_split_gd", "pending_action", "godot_executable",
            "current_chat_id")}
        S.STATE.update({"project_root": str(self.root),
                        "addon_dir": str(self.addon),
                        "allow_addons": False, "allow_self_edit": True,
                        "pending_split_gd": None, "pending_action": None,
                        "godot_executable": "",
                        "current_chat_id": "test_split_gd_flow"})
        self.addCleanup(self._restore)
        self.client = main.app.test_client()

    def _restore(self):
        S.STATE.update(self._saved)

    def plan(self):
        return self.client.post("/project/split_gd/plan", json={
            "file": DONOR_RES,
            "groups": [{"module": "split_gd_probe_part1",
                        "funcs": ["split_gd_probe_alpha",
                                  "split_gd_probe_beta"]}]})

    def test_scan_is_read_only(self):
        resp = self.client.post("/project/split_gd/scan",
                                json={"file": DONOR_RES})
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["scan"]["donor"], "split_gd_probe.gd")
        self.assertEqual(data["scan"]["funcs"], 3)
        self.assertEqual(self.donor.read_text(encoding="utf-8"), DONOR)

    def test_scan_refuses_foreign_and_non_gd(self):
        resp = self.client.post("/project/split_gd/scan",
                                json={"file": "res://src/player.gd"})
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post("/project/split_gd/scan", json={
            "file": "res://addons/Godot_agent/godot_agent/agent_panel.py"})
        self.assertEqual(resp.status_code, 400)

    def test_plan_is_read_only_and_stores_pending(self):
        resp = self.plan()
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        plan = resp.get_json()["plan"]
        self.assertEqual(plan["donor"], DONOR_RES)
        self.assertEqual([module["rel"] for module in plan["modules"]],
                         ["split_gd_probe_part1.gd"])
        self.assertEqual(plan["moved"], 2)
        self.assertIsInstance(S.STATE.get("pending_split_gd"), dict)
        self.assertEqual(self.donor.read_text(encoding="utf-8"), DONOR)
        self.assertFalse(self.module.exists())

    def test_apply_requires_plan(self):
        resp = self.client.post("/project/split_gd/apply", json={})
        self.assertEqual(resp.status_code, 409)

    def test_apply_writes_modules_and_donor(self):
        self.assertEqual(self.plan().status_code, 200)
        resp = self.client.post("/project/split_gd/apply", json={})
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["entry_id"])
        self.assertIn(DONOR_RES, data["changed_paths"])
        self.assertIn(MODULE_RES, data["changed_paths"])
        self.assertTrue(self.module.exists())
        module_text = self.module.read_text(encoding="utf-8")
        self.assertIn("static func split_gd_probe_alpha", module_text)
        self.assertIn("static func split_gd_probe_beta", module_text)
        donor_text = self.donor.read_text(encoding="utf-8")
        self.assertIn("func split_gd_probe_gamma", donor_text)
        self.assertIn("split_gd_probe_part1.gd", donor_text)
        self.assertNotIn("return 1", donor_text)
        self.assertIsNone(S.STATE.get("pending_split_gd"))


if __name__ == "__main__":
    unittest.main()
