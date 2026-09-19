"""Run real executor regressions in a disposable, plugin-free Godot editor project.

Usage from godot_agent: python -B python/tests/test_godot_executor_live.py --godot EXE
Only top-level addon .gd/.tscn files are copied; the user project is never opened.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


CASES = {"replace_probe", "scene", "settings", "resource_property", "theme", "sprite_frames", "animation",
         "tileset", "tileset_rejections", "scene_open_clean", "scene_open_dirty", "scene_open_inactive",
         "resource_open_inspector", "resource_open_embedded", "autoreload_false_preserved", "autoreload_true_preserved"}
CASES.update("resource_safety_" + mode for mode in (
    "sentinel", "stale_preview", "stale_publish", "stale_temp", "backup_collision", "publish_failure",
    "restore", "restore_conflict", "restore_failure", "save_failure"))
SENTINEL = "GODOT_EXECUTOR_RESULTS "


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT_AGENT_GODOT_EXECUTABLE"))
    parser.add_argument("--temp-parent", default=None)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--replace-probe-only", action="store_true")
    args = parser.parse_args()
    executable = args.godot or shutil.which("godot") or shutil.which("godot4")
    if not executable:
        parser.error("Specify --godot; these tests require the real engine.")
    executable = str(Path(executable).resolve(strict=True))
    addon = Path(__file__).resolve().parents[2]
    expected_cases = {"replace_probe"} if args.replace_probe_only else CASES
    with tempfile.TemporaryDirectory(prefix="godot-executors-", dir=args.temp_parent) as temp:
        root = Path(temp)
        copied = root / "addons" / "godot_agent"
        copied.mkdir(parents=True)
        for source in addon.iterdir():
            if source.suffix in (".gd", ".tscn"):
                shutil.copyfile(source, copied / source.name)
        for source in (Path(__file__).parent / "fixtures").glob("executor_*.gd"):
            shutil.copyfile(source, root / source.name)
        (root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Executor regression sandbox"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
        env = os.environ.copy()
        for name in ("APPDATA", "LOCALAPPDATA", "HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            directory = root / "isolated_user" / name
            directory.mkdir(parents=True)
            env[name] = str(directory)
        base = [executable, "--headless", "--path", str(root), "--editor", "--language", "en"]
        harness = ["--script", "res://executor_live.gd"]
        if args.replace_probe_only:
            harness += ["--", "--replace-probe-only"]
        for arguments in (["--import", "--quit"], harness):
            command = base + arguments
            print("RUN " + subprocess.list2cmdline(command), flush=True)
            try:
                result = subprocess.run(command, env=env, cwd=root, capture_output=True,
                                        timeout=args.timeout, encoding="utf-8", errors="replace")
            except subprocess.TimeoutExpired as error:
                print(error.stdout or "")
                print(error.stderr or "")
                raise RuntimeError("Godot executor regression timed out") from error
            print(result.stdout)
            print(result.stderr)
            output = result.stdout + result.stderr
            # Godot 4.6.1 --editor --script emits these shutdown diagnostics even
            # after all cases complete. Keep them visible, not confused with a
            # script failure or a resource/scene API error during the tests.
            cleanup = [line for line in output.splitlines() if re.fullmatch(
                r"ERROR: \d+ RID allocations of type '[^']+' were leaked at exit\.", line)]
            errors = ("SCRIPT ERROR:", "Parse Error:", "Unicode parsing error", "ERROR:")
            fatal_output = "\n".join(line for line in output.splitlines() if line not in cleanup)
            if result.returncode != 0 or any(marker in fatal_output for marker in errors):
                raise RuntimeError("Godot failed or reported engine/script errors (exit %d)" % result.returncode)
            if arguments[0] == "--script":
                reports = [line[len(SENTINEL):] for line in result.stdout.splitlines()
                           if line.startswith(SENTINEL)]
                if len(reports) != 1:
                    raise RuntimeError("Missing or duplicate executor completion sentinel")
                report = json.loads(reports[0])
                if set(report.get("completed", [])) != expected_cases or report.get("failures") != []:
                    raise RuntimeError("Incomplete or failing executor results: %r" % report)
            if cleanup:
                print("LIMITATION: Godot emitted %d shutdown RID leak diagnostics (shown above)." % len(cleanup))
        print("PASS: %d real Godot executor scenarios in an isolated editor project" % len(expected_cases))


if __name__ == "__main__":
    main()
