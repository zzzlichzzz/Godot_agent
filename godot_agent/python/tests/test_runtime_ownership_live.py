"""Dedicated Godot 4.6.1 ownership-refusal and screenshot regressions.

Run: python -B python/tests/test_runtime_ownership_live.py --godot EXE --temp-parent DIR
Only disposable projects are opened. No game process is launched by this suite.
The screenshot probe substitutes an Image for viewport readback; resizing and JPEG
encoding execute the production method unchanged in the real engine.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


SENTINEL = "RUNTIME_OWNERSHIP_RESULTS "


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", required=True)
    parser.add_argument("--temp-parent", default=None)
    args = parser.parse_args()
    executable = str(Path(args.godot).resolve(strict=True))
    addon = Path(__file__).resolve().parents[2]
    panel = (addon / "agent_panel.gd").read_text(encoding="utf-8")
    # These are intentionally whole-panel invariants: no timeout, unload,
    # result retry or late bind callback may bypass the conservative refusal.
    for forbidden in (
        "EditorInterface.play_custom_scene(", "EditorInterface.stop_playing_scene(",
        "_runtime_debugger.run_check(", "RUNTIME_CHECK_BIND_URL", "OS.kill(",
    ):
        assert forbidden not in panel, "Unsafe runtime path returned: " + forbidden

    bridge = (addon / "agent_runtime_bridge.gd").read_text(encoding="utf-8")
    method = bridge.split("func _capture_check_screenshot(", 1)[1].split("\n\nfunc ", 1)[0]
    method = "func _capture_check_screenshot(" + method
    readback = "get_viewport().get_texture().get_image()"
    assert method.count(readback) == 1
    probe = "extends RefCounted\nvar source_image: Image\n\n" + method.replace(readback, "source_image")

    with tempfile.TemporaryDirectory(prefix="runtime-ownership-", dir=args.temp_parent) as temp:
        root = Path(temp)
        copied = root / "addon"
        copied.mkdir()
        # Panel's existing global UI types need their scripts for full parsing.
        for source in addon.iterdir():
            if source.suffix in (".gd", ".tscn"):
                shutil.copyfile(source, copied / source.name)
        shutil.copyfile(Path(__file__).parent / "fixtures" / "runtime_ownership_live.gd_fixture",
                        root / "runtime_ownership_live.gd")
        (root / "screenshot_probe.gd").write_text(probe, encoding="utf-8")
        (root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Runtime ownership sandbox"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
        env = os.environ.copy()
        for name in ("APPDATA", "LOCALAPPDATA", "HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            directory = root / "isolated_user" / name
            directory.mkdir(parents=True)
            env[name] = str(directory)
        base = [executable, "--headless", "--path", str(root), "--editor", "--language", "en"]
        for arguments in (["--import", "--quit"], ["--script", "res://runtime_ownership_live.gd"]):
            command = base + arguments
            print("RUN " + subprocess.list2cmdline(command), flush=True)
            result = subprocess.run(command, env=env, cwd=root, capture_output=True,
                                    timeout=120, encoding="utf-8", errors="replace")
            output = result.stdout + result.stderr
            print(output)
            # --editor --script on this build leaks renderer RIDs on shutdown.
            # Keep diagnostics visible and reject every other engine error.
            shutdown = [line for line in output.splitlines() if re.fullmatch(
                r"ERROR: \d+ RID allocations of type '[^']+' were leaked at exit\.", line)]
            fatal = "\n".join(line for line in output.splitlines() if line not in shutdown)
            if result.returncode or any(text in fatal for text in ("SCRIPT ERROR:", "Parse Error:", "ERROR:")):
                raise RuntimeError("Godot runtime ownership regressions failed")
            if arguments[0] == "--script":
                reports = [json.loads(line[len(SENTINEL):]) for line in result.stdout.splitlines()
                           if line.startswith(SENTINEL)]
                assert len(reports) == 1, "Missing/duplicate completion report"
                assert reports[0] == {"failures": [], "refusals": 5, "screenshots": 8, "api_audit": True}, reports
            if shutdown:
                print("LIMITATION: editor-script shutdown RID leak diagnostics shown above.")
    print("PASS: API audit, 5 refusal scenarios, late-bind/cleanup checks, 8 screenshot dimensions")


if __name__ == "__main__":
    main()
