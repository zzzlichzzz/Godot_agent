"""Compile the actual addon scripts in an isolated project using real Godot 4.

Usage: python -B tests/test_godot_live.py --godot C:/tools/godot.exe
No editor plugin, project autoload or user game is started by this test.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


HARNESS = '''extends SceneTree

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	await process_frame
	await process_frame
	while EditorInterface.get_resource_filesystem().is_scanning():
		await process_frame
	var paths: Array = JSON.parse_string(FileAccess.get_file_as_string("res://scripts.json"))
	var failures: Array[String] = []
	for path in paths:
		var script: Script = ResourceLoader.load(str(path), "Script", ResourceLoader.CACHE_MODE_IGNORE)
		if script == null or script.reload(true) != OK:
			failures.append(str(path))
	print("GODOT_SCRIPT_CHECK " + JSON.stringify({"count": paths.size(), "failures": failures}))
	await process_frame
	quit(0 if failures.is_empty() else 1)
'''


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT_AGENT_GODOT_EXECUTABLE"))
    args = parser.parse_args()
    executable = args.godot or shutil.which("godot") or shutil.which("godot4")
    if not executable:
        parser.error("Specify --godot; static tests cannot replace engine compilation.")
    executable = str(Path(executable).resolve())
    addon = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="godot-agent-live-") as temp:
        root = Path(temp)
        copied = root / "addons" / "godot_agent"
        copied.mkdir(parents=True)
        paths = []
        for source in sorted(addon.iterdir()):
            if source.suffix not in (".gd", ".tscn"):
                continue
            shutil.copyfile(source, copied / source.name)
            if source.suffix == ".gd":
                paths.append("res://addons/godot_agent/" + source.name)
        (root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Agent live verification"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
        (root / "scripts.json").write_text(json.dumps(paths), encoding="utf-8")
        (root / "verify.gd").write_text(HARNESS, encoding="utf-8")
        env = os.environ.copy()
        for name in ("APPDATA", "LOCALAPPDATA", "HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
            directory = root / "isolated_user" / name
            directory.mkdir(parents=True)
            env[name] = str(directory)
        base = [executable, "--headless", "--path", str(root), "--editor", "--language", "en"]
        for arguments in (["--import", "--quit"], ["--script", "res://verify.gd"]):
            result = subprocess.run(base + arguments, env=env, cwd=root,
                                    capture_output=True, timeout=90, encoding="utf-8", errors="replace")
            print(result.stdout)
            print(result.stderr)
            if result.returncode != 0:
                raise AssertionError("Godot exited with %d" % result.returncode)
            if arguments[0] == "--script":
                if "GODOT_SCRIPT_CHECK " not in result.stdout:
                    raise AssertionError("Godot did not complete the script check")
                if any(error in result.stderr for error in ("SCRIPT ERROR:", "Parse Error:", "Unicode parsing error")):
                    raise AssertionError("Godot reported script errors despite successful exit")
        print("PASS: real Godot compiled %d addon scripts in isolation" % len(paths))


if __name__ == "__main__":
    main()
