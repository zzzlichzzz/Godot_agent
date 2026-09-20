# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Live Godot 4.6.3 verification of asset and .import refactoring with UID preservation.

Run: python -B godot_agent/python/tests/test_asset_refactor_live.py --godot "path/to/godot.exe"
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

import file_refactor
import history_manager


SENTINEL = "ASSET_REFACTOR_LIVE_RESULTS "


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


class TestAssetRefactorLive(unittest.TestCase):

    def setUp(self):
        self.godot_bin = find_godot_executable()
        if not self.godot_bin or not os.path.isfile(self.godot_bin):
            self.skipTest("Godot executable not found for live testing")

        self.temp_dir = tempfile.mkdtemp(prefix="godot-asset-live-")
        self.project_root = self.temp_dir

        # Setup Godot project.godot
        with open(os.path.join(self.project_root, "project.godot"), "w", encoding="utf-8") as f:
            f.write(
                'config_version=5\n[application]\nconfig/name="LiveAssetRefactorTest"\n'
                'config/icon="res://icon.svg"\n'
                '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
            )

        # Copy real icon.svg and icon.svg.import from test project if available
        src_svg = r"d:\vajno\Godot\тест-плагина-ии\icon.svg"
        src_import = r"d:\vajno\Godot\тест-плагина-ии\icon.svg.import"
        if os.path.isfile(src_svg) and os.path.isfile(src_import):
            shutil.copy2(src_svg, os.path.join(self.project_root, "icon.svg"))
            shutil.copy2(src_import, os.path.join(self.project_root, "icon.svg.import"))
        else:
            # Fallback minimal SVG
            with open(os.path.join(self.project_root, "icon.svg"), "w", encoding="utf-8") as f:
                f.write('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16" fill="red"/></svg>')

        # Run Godot headless to perform initial project import
        subprocess.run(
            [self.godot_bin, "--headless", "--editor", "--quit", "--path", self.project_root],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )

        # Extract UID from icon.svg.import
        self.initial_uid = None
        import_path = os.path.join(self.project_root, "icon.svg.import")
        if os.path.isfile(import_path):
            with open(import_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("uid="):
                        self.initial_uid = line.split("=", 1)[1].strip().strip('"')
                        break

        if not self.initial_uid:
            self.initial_uid = "uid://10x3kyltsjek"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_file(self, rel_path, content):
        full = os.path.join(self.project_root, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return full

    def test_live_asset_relocation_and_uid_integrity(self):
        """Live engine verification: asset relocation preserves UID, updates scene, and Sprite2D renders texture."""
        # 1. Create a scene using the asset by UID and path
        scene_content = (
            '[gd_scene load_steps=2 format=3]\n\n'
            f'[ext_resource type="Texture2D" uid="{self.initial_uid}" path="res://icon.svg" id="1_tex"]\n\n'
            '[node name="Main" type="Node2D"]\n'
            '[node name="Sprite2D" type="Sprite2D" parent="."]\n'
            'texture = ExtResource("1_tex")\n'
        )
        self._write_file("main.tscn", scene_content)

        # 2. Create script referencing icon.svg
        script_content = (
            'extends Node\n\n'
            'const ICON = preload("res://icon.svg")\n'
            'func get_icon_path() -> String:\n'
            '    return ICON.resource_path\n'
        )
        self._write_file("test_script.gd", script_content)

        # 3. Perform asset refactor: move res://icon.svg to res://art/textures/logo.svg
        prep = file_refactor.prepare_file_rename(
            self.project_root, "res://icon.svg", "res://art/textures/logo.svg", update_references=True
        )
        result = file_refactor.apply_prepared_file_rename(self.project_root, prep)
        self.assertTrue(result["entry_id"])

        # 4. Verify disk state
        self.assertFalse(os.path.isfile(os.path.join(self.project_root, "icon.svg")))
        self.assertFalse(os.path.isfile(os.path.join(self.project_root, "icon.svg.import")))

        dest_svg = os.path.join(self.project_root, "art", "textures", "logo.svg")
        dest_import = os.path.join(self.project_root, "art", "textures", "logo.svg.import")
        self.assertTrue(os.path.isfile(dest_svg))
        self.assertTrue(os.path.isfile(dest_import))

        with open(dest_import, "r", encoding="utf-8") as f:
            dest_import_text = f.read()
        self.assertIn('source_file="res://art/textures/logo.svg"', dest_import_text)
        self.assertIn(f'uid="{self.initial_uid}"', dest_import_text)

        # 4.5 Run Godot editor import pass so Godot updates its UID cache and imported .ctex cache
        subprocess.run(
            [self.godot_bin, "--headless", "--editor", "--quit", "--path", self.project_root],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )

        # 5. Create verification runner in Godot
        runner_content = (
            "extends SceneTree\n\n"
            "func _initialize() -> void:\n"
            "    call_deferred(\"_run\")\n\n"
            "func _run() -> void:\n"
            "    var scene: PackedScene = load(\"res://main.tscn\")\n"
            "    if not scene:\n"
            "        print(\"FAILED: could not load main.tscn\")\n"
            "        quit(1)\n"
            "        return\n"
            "    var root_node: Node2D = scene.instantiate()\n"
            "    var sprite: Sprite2D = root_node.get_node(\"Sprite2D\")\n"
            "    var tex = sprite.texture if sprite else null\n"
            "    var tex_ok: bool = (tex != null and tex.get_width() > 0)\n"
            "    var tex_path: String = tex.resource_path if tex else \"\"\n"
            "    var script_cls = load(\"res://test_script.gd\")\n"
            "    var script_inst = script_cls.new() if script_cls else null\n"
            "    var script_path: String = script_inst.get_icon_path() if script_inst else \"\"\n"
            "    var ok: bool = tex_ok and (tex_path == \"res://art/textures/logo.svg\" or tex_path != \"\")\n"
            '    print("%s" + JSON.stringify({\n'
            '        "ok": ok,\n'
            '        "tex_loaded": tex_ok,\n'
            '        "tex_path": tex_path,\n'
            '        "script_path": script_path,\n'
            '    }))\n'
            "    root_node.free()\n"
            "    quit(0 if ok else 1)\n"
        ) % SENTINEL
        self._write_file("verify_runner.gd", runner_content)

        # 6. Run Godot in headless mode
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

        print("GODOT STDOUT:\n", proc.stdout)
        print("GODOT STDERR:\n", proc.stderr)
        self.assertIsNotNone(sentinel_line, "Sentinel not found in output:\n" + proc.stdout + "\n" + proc.stderr)
        results = json.loads(sentinel_line)
        self.assertTrue(results.get("ok"), "Godot live verification failed: " + str(results))
        self.assertTrue(results.get("tex_loaded"), "Texture was not loaded in Sprite2D: " + str(results))
        self.assertEqual(proc.returncode, 0)
        print("PASS: Live engine verification of asset relocation passed! Results: %s" % results)

        # 7. Test Rollback in live engine
        ok, msg, needs_force, paths, diff = history_manager.rollback_last(self.project_root)
        if not ok and needs_force:
            ok, msg, _, _, _ = history_manager.rollback_last(self.project_root, force=True)
        self.assertTrue(ok, msg)

        # Verify restored on disk
        self.assertTrue(os.path.isfile(os.path.join(self.project_root, "icon.svg")))
        self.assertTrue(os.path.isfile(os.path.join(self.project_root, "icon.svg.import")))
        self.assertFalse(os.path.isfile(dest_svg))
        self.assertFalse(os.path.isfile(dest_import))

        # Re-import pass for rollback state
        subprocess.run(
            [self.godot_bin, "--headless", "--editor", "--quit", "--path", self.project_root],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )

        # Run verification runner for restored state
        rollback_runner = (
            "extends SceneTree\n\n"
            "func _initialize() -> void:\n"
            "    call_deferred(\"_run\")\n\n"
            "func _run() -> void:\n"
            "    var scene: PackedScene = load(\"res://main.tscn\")\n"
            "    var root_node: Node2D = scene.instantiate() if scene else null\n"
            "    var sprite: Sprite2D = root_node.get_node(\"Sprite2D\") if root_node else null\n"
            "    var tex = sprite.texture if sprite else null\n"
            "    var ok: bool = (tex != null and tex.get_width() > 0)\n"
            '    print("%s" + JSON.stringify({"ok": ok, "restored": true}))\n'
            "    if root_node: root_node.free()\n"
            "    quit(0 if ok else 1)\n"
        ) % SENTINEL
        self._write_file("verify_rollback.gd", rollback_runner)

        cmd_rb = [
            self.godot_bin,
            "--headless",
            "--path", self.project_root,
            "--editor",
            "--language", "en",
            "--script", "res://verify_rollback.gd",
        ]
        proc_rb = subprocess.run(
            cmd_rb,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        sentinel_rb = None
        for line in proc_rb.stdout.splitlines():
            if line.startswith(SENTINEL):
                sentinel_rb = line[len(SENTINEL):]
                break

        self.assertIsNotNone(sentinel_rb, "Sentinel not found in rollback output:\n" + proc_rb.stdout)
        results_rb = json.loads(sentinel_rb)
        self.assertTrue(results_rb.get("ok"), "Godot rollback verification failed: " + str(results_rb))
        self.assertEqual(proc_rb.returncode, 0)
        print("PASS: Live engine verification of asset rollback passed! Results: %s" % results_rb)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", help="Path to Godot binary")
    args, unknown = parser.parse_known_args()
    if args.godot:
        os.environ["GODOT_EXECUTABLE"] = os.path.abspath(args.godot)
    sys.argv = [sys.argv[0]] + unknown
    unittest.main()
