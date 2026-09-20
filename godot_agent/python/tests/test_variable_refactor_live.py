# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Live Godot 4.6.3 verification of @export variable refactoring.

Run: python -B godot_agent/python/tests/test_variable_refactor_live.py --godot "path/to/godot.exe"
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from godot_tools import symbol_refactor


SENTINEL = "VARIABLE_REFACTOR_LIVE_RESULTS "


def find_godot_executable():
    env_path = os.environ.get("GODOT_EXECUTABLE")
    if env_path and os.path.isfile(env_path):
        return env_path
    candidates = [
        r"D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe",
        r"D:\vajno\Godot\Godot v4.6\Godot_v4.6-stable_win64_console.exe",
        r"D:\vajno\Godot\Godot v4.5.1\Godot_v4.5.1-stable_win64_console.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return shutil.which("godot")


class TestVariableRefactorLive(unittest.TestCase):

    def setUp(self):
        self.godot_bin = find_godot_executable()
        if not self.godot_bin or not os.path.isfile(self.godot_bin):
            self.skipTest("Godot executable not found for live testing")

        self.temp_dir = tempfile.mkdtemp(prefix="godot-var-live-")
        self.project_root = self.temp_dir
        with open(os.path.join(self.project_root, "project.godot"), "w", encoding="utf-8") as f:
            f.write(
                'config_version=5\n[application]\nconfig/name="LiveVarRefactorTest"\n'
                '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
            )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_file(self, rel_path, content):
        full = os.path.join(self.project_root, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return full

    def test_live_export_property_preservation(self):
        # 1. Create player script with @export properties
        player_gd = (
            "extends CharacterBody2D\n"
            "@export var health: int = 100\n"
            "@export var speed: float = 250.0\n\n"
            "func get_hp() -> int:\n"
            "    return health\n"
        )
        self._write_file("player.gd", player_gd)

        # 2. Create scene setting health = 42 and speed = 350.0
        player_tscn = (
            '[gd_scene format=3 uid="uid://live_var_test_scene"]\n\n'
            '[ext_resource type="Script" path="res://player.gd" id="1_plr"]\n\n'
            '[node name="Player" type="CharacterBody2D"]\n'
            'script = ExtResource("1_plr")\n'
            'health = 42\n'
            'speed = 350.0\n'
        )
        self._write_file("player.tscn", player_tscn)

        # 3. Perform refactoring: health -> current_health
        action = {
            "action": "rename_symbol",
            "kind": "variable",
            "declaration": "res://player.gd:2",
            "old_name": "health",
            "new_name": "current_health",
        }
        prepared = symbol_refactor.prepare_rename(self.project_root, action)
        symbol_refactor.apply_prepared_rename(self.project_root, prepared)

        # Verify files on disk before running Godot
        with open(os.path.join(self.project_root, "player.tscn"), "r", encoding="utf-8") as f:
            tscn_content = f.read()
        self.assertIn("current_health = 42", tscn_content)
        self.assertNotIn("\nhealth = 42", tscn_content)

        # 4. Create verification runner for live engine check
        verify_runner = (
            "extends SceneTree\n\n"
            "func _initialize() -> void:\n"
            "    call_deferred(\"_run\")\n\n"
            "func _run() -> void:\n"
            "    var scene: PackedScene = load(\"res://player.tscn\")\n"
            "    if not scene:\n"
            "        print(\"FAILED: could not load scene\")\n"
            "        quit(1)\n"
            "        return\n"
            "    var node: Node = scene.instantiate()\n"
            "    var hp = node.get(\"current_health\")\n"
            '    var old_hp = node.get(String("heal") + "th")\n'
            "    var spd = node.get(\"speed\")\n"
            "    var ok: bool = (hp == 42 and old_hp == null and spd == 350.0)\n"
            '    print("%s", %s)\n'
            '    print("%s" + JSON.stringify({"ok": ok, "current_health": hp, "speed": spd}))\n'
            "    node.free()\n"
            "    quit(0 if ok else 1)\n"
        ) % ("VERIFY_CHECK", "ok", SENTINEL)
        self._write_file("verify_runner.gd", verify_runner)

        # 5. Run Godot in headless mode to instantiate the scene and check values
        cmd = [
            self.godot_bin,
            "--headless",
            "--path", self.project_root,
            "--editor",
            "--language", "en",
            "--script", "res://verify_runner.gd",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        sentinel_line = None
        for line in proc.stdout.splitlines():
            if line.startswith(SENTINEL):
                sentinel_line = line[len(SENTINEL):]
                break

        self.assertIsNotNone(sentinel_line, "Sentinel not found in output:\n" + proc.stdout)
        results = json.loads(sentinel_line)
        self.assertTrue(results.get("ok"), "Godot live verification failed: " + str(results))
        self.assertEqual(results.get("current_health"), 42)
        self.assertEqual(results.get("speed"), 350.0)
        self.assertEqual(proc.returncode, 0)
        print("PASS: Live engine verification of @export property rename with Godot 4.6.3 passed! Results: %s" % results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", help="Path to Godot binary")
    args, unknown = parser.parse_known_args()
    if args.godot:
        os.environ["GODOT_EXECUTABLE"] = os.path.abspath(args.godot)
    sys.argv = [sys.argv[0]] + unknown
    unittest.main()
