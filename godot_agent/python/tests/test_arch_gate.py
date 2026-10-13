# -*- coding: utf-8 -*-
"""Тесты архитектурного гейта в мосте (agent_bridge, режим agent-dev).

Контракт:
  * новый .py агента с именем функции ядра — отказ (rc=2, «дубль из ядра»);
  * новый .py в зоне потребителя с уникальным именем — разрешён, но получает
    строки «arch:» в preview и в apply (их читает стадия-архитектор n8n);
  * зона deny (генерируемые каталоги) — отказ;
  * зона вне карты — предупреждение, не отказ;
  * зоны с check_names:false (тесты) не сверяют имена;
  * файлы пользовательских проектов и режим project карту не касаются.
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
import agent_bridge  # noqa: E402


def run_bridge(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = agent_bridge.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


MAP = {
    "schema": 1,
    "core_dir": "python/godot_tools",
    "name_stoplist": ["main"],
    "zones": [
        {"glob": "python/godot_tools/**", "role": "core", "new_files": "allow"},
        {"glob": "python/tests/**", "role": "tests", "new_files": "allow",
         "check_names": False},
        {"glob": "python/browser/**", "role": "consumer", "new_files": "warn",
         "hint": "вызовы ядра"},
        {"glob": "agent_api_cache/**", "role": "generated", "new_files": "deny"},
        {"glob": "**", "role": "unknown", "new_files": "warn"},
    ],
}

AGENT = "res://addons/Godot_agent/godot_agent"


class ArchGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arch_gate_")
        self.addCleanup(self.temp.cleanup)
        self.root = str(Path(self.temp.name))
        self.store = str(Path(self.temp.name, "store"))
        self.agent = Path(self.root, "addons", "Godot_agent", "godot_agent")
        (self.agent / "docs").mkdir(parents=True)
        (self.agent / "docs" / "architecture_map.json").write_text(
            json.dumps(MAP, ensure_ascii=False), encoding="utf-8")
        core = self.agent / "python" / "godot_tools"
        core.mkdir(parents=True)
        (core / "core_mod.py").write_text(
            "def reticulate_splines():\n    return 1\n", encoding="utf-8")
        (self.agent / "python" / "browser").mkdir(parents=True)
        Path(self.root, "project.godot").write_text(
            "config_version=5\n", encoding="utf-8")
        import history_manager
        previous = history_manager._STORAGE_OVERRIDE
        self.addCleanup(setattr, history_manager, "_STORAGE_OVERRIDE", previous)

    def request_file(self, payload, name="request.json"):
        path = Path(self.store, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return str(path)

    @staticmethod
    def plan_id(output):
        match = re.search(r"^plan_id: ([0-9a-f]{24})$", output, re.MULTILINE)
        return match.group(1) if match else ""

    def _bridge(self, mode, tail, request):
        argv = (["--root", self.root, "--udd", self.store,
                 "--no-builtin-cache", "--access", mode, "--validation", "off"]
                + tail + ["--request", request])
        with patch.object(agent_bridge, "_discover_bridge_agent_dir",
                          return_value=str(self.agent)):
            return run_bridge(argv)

    def preview(self, payload, mode="agent-dev", name="request.json"):
        return self._bridge(mode, ["write", "preview"],
                            self.request_file(payload, name))

    def apply(self, payload, plan_id):
        return self._bridge("agent-dev",
                            ["write", "apply", "--plan-id", plan_id],
                            self.request_file(payload, "apply.json"))

    @staticmethod
    def create(res_path, content):
        return {"action": "create_file", "path": res_path, "content": content}

    def test_core_name_duplicate_in_consumer_is_refused(self):
        rc, out, err = self.preview(self.create(
            AGENT + "/python/browser/helper.py",
            "def reticulate_splines():\n    return 2\n"))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("дубль из ядра", out)
        self.assertIn("core_mod.py", out)
        self.assertFalse(
            (self.agent / "python" / "browser" / "helper.py").exists())

    def test_unique_consumer_file_warns_and_applies(self):
        payload = self.create(AGENT + "/python/browser/helper.py",
                              "def sweep_scene_cache():\n    return 1\n")
        rc, out, err = self.preview(payload)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("arch: new agent file(s) checked:", out)
        self.assertIn("ядре", out)
        plan_id = self.plan_id(out)
        self.assertRegex(plan_id, r"^[0-9a-f]{24}$")
        rc, out, err = self.apply(payload, plan_id)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("arch: new agent file(s) checked:", out)
        self.assertTrue(
            (self.agent / "python" / "browser" / "helper.py").exists())

    def test_core_zone_new_file_passes_without_consumer_warning(self):
        rc, out, err = self.preview(self.create(
            AGENT + "/python/godot_tools/new_mod.py",
            "def brand_new_helper():\n    return 1\n"))
        self.assertEqual(rc, 0, out + err)
        self.assertIn("arch: new agent file(s) checked:", out)
        self.assertNotIn("ядре (python/godot_tools); здесь", out)

    def test_generated_zone_is_refused(self):
        rc, out, err = self.preview(self.create(
            AGENT + "/agent_api_cache/classes.json", "{}"))
        self.assertEqual(rc, 2, out + err)
        self.assertIn("generated", out)

    def test_unknown_zone_warns_but_allows(self):
        rc, out, err = self.preview(self.create(
            AGENT + "/weird/thing.py", "def zz_unique():\n    pass\n"))
        self.assertEqual(rc, 0, out + err)
        self.assertIn("arch:", out)
        self.assertIn("unknown", out)

    def test_tests_zone_skips_name_checks(self):
        rc, out, err = self.preview(self.create(
            AGENT + "/python/tests/test_helper.py",
            "def reticulate_splines():\n    return 4\n"))
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("дубль из ядра", out)

    def test_user_project_file_is_not_gated(self):
        rc, out, err = self.preview(self.create(
            "res://src/helper.py", "def reticulate_splines():\n    return 5\n"))
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("дубль из ядра", out)

    def test_project_mode_has_no_gate(self):
        rc, out, err = self.preview(
            self.create("res://src/helper.py",
                        "def reticulate_splines():\n    return 5\n"),
            mode="project")
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn("arch:", out)


if __name__ == "__main__":
    unittest.main()
