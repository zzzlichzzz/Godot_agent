# -*- coding: utf-8 -*-
"""Real headless Godot test for agent_updater.gd with a mock GitHub HTTP server.

Usage: python -B godot_agent/python/tests/test_updater_live.py [--godot EXE]
"""
import argparse
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SENTINEL = "UPDATER_LIVE_RESULTS "


def make_test_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in entries.items():
            zf.writestr(arcname, content)
    return buf.getvalue()


class MockGitHubHandler(BaseHTTPRequestHandler):
    release_requests = 0
    download_requests = 0
    zip_bytes = b""

    def do_GET(self):
        if self.path == "/releases/latest":
            MockGitHubHandler.release_requests += 1
            port = self.server.server_port
            payload = {
                "tag_name": "v0.8.0",
                "html_url": "https://github.com/zzzlichzzz/Godot_agent/releases/tag/v0.8.0",
                "body": "## New in 0.8.0\n- Automated 1-click updates\n- High reliability",
                "published_at": "2026-09-20T12:00:00Z",
                "assets": [
                    {
                        "name": "godot_agent_v0.8.0.zip",
                        "browser_download_url": "http://127.0.0.1:%d/download/godot_agent_v0.8.0.zip" % port
                    }
                ],
                "zipball_url": "http://127.0.0.1:%d/download/zipball.zip" % port
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/download/"):
            MockGitHubHandler.download_requests += 1
            data = MockGitHubHandler.zip_bytes
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/server/shutdown":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            body = b'{"ok": true}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


RUNNER_GDSCRIPT = """extends SceneTree

const MOCK_PORT = {PORT}

var _updater = null
var _step := 0
var _results := {}

func _initialize() -> void:
	call_deferred("_start_test")

func _start_test() -> void:
	await process_frame
	await process_frame

	var script = load("res://addons/godot_agent/agent_updater.gd")
	if script == null:
		_fail("Failed to load agent_updater.gd")
		return

	_updater = script.new()
	_updater.name = "AgentUpdater"
	root.add_child(_updater)

	_updater.update_available.connect(_on_update_available)
	_updater.update_completed.connect(_on_update_completed)
	_updater.update_error.connect(_on_update_error)
	_updater.check_completed.connect(_on_check_completed)

	_updater.releases_url = "http://127.0.0.1:" + str(MOCK_PORT) + "/releases/latest"

	# Шаг 1: Проверка наличия обновления (force = true)
	_step = 1
	_updater.check_for_updates(true)

func _on_check_completed(has_update: bool, info: Dictionary) -> void:
	if _step == 1:
		if not has_update or info.get("version", "") != "0.8.0":
			_fail("Step 1 failed: expected has_update=true and version=0.8.0, got: " + str(info))
			return
		_results["step1_check"] = true

		# Шаг 2: Проверка кэширования (force = false, не должно лезть в сеть)
		_step = 2
		_updater.check_for_updates(false)
	elif _step == 2:
		if not has_update or info.get("version", "") != "0.8.0":
			_fail("Step 2 failed: expected cached has_update=true, got: " + str(info))
			return
		_results["step2_cache"] = true

		# Шаг 3: Скачивание и установка
		_step = 3
		_updater.start_update()

func _on_update_available(_info: Dictionary) -> void:
	_results["update_available_emitted"] = true

func _on_update_completed(restart_needed: bool) -> void:
	if _step == 3:
		_results["step3_install"] = true
		_results["restart_needed"] = restart_needed

		# Проверяем, что plugin.cfg обновился до 0.8.0
		var cfg := ConfigFile.new()
		var err := cfg.load("res://addons/godot_agent/plugin.cfg")
		if err == OK:
			var ver: String = cfg.get_value("plugin", "version", "")
			_results["new_version"] = ver
			if ver == "0.8.0":
				_results["ok"] = true
				print("UPDATER_LIVE_RESULTS " + JSON.stringify(_results))
				quit(0)
				return
			else:
				_fail("Version in plugin.cfg is " + ver + ", expected 0.8.0")
				return
		_fail("Failed to load updated plugin.cfg (err " + str(err) + ")")

func _on_update_error(msg: String) -> void:
	_fail("Updater error: " + msg)

func _fail(msg: String) -> void:
	_results["ok"] = false
	_results["error"] = msg
	print("UPDATER_LIVE_RESULTS " + JSON.stringify(_results))
	quit(1)
"""


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT_AGENT_GODOT_EXECUTABLE"))
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    default_engine = r"D:\vajno\Godot\Godot v4.6.3\Godot_v4.6.3-stable_win64_console.exe"
    executable = args.godot or (default_engine if os.path.isfile(default_engine) else None) or shutil.which("godot") or shutil.which("godot4")
    if not executable or not os.path.isfile(executable):
        print("Godot binary not found. Skipping live engine test.")
        return 0

    executable = str(Path(executable).resolve(strict=True))
    addon_dir = Path(__file__).resolve().parents[2]

    # Создаем тестовый архив для обновления
    MockGitHubHandler.zip_bytes = make_test_zip({
        "godot_agent/plugin.cfg": "[plugin]\nname=\"Godot Agent\"\nversion=\"0.8.0\"\nscript=\"plugin_universal.gd\"\n",
        "godot_agent/agent_panel.gd": "# Updated panel v0.8.0\n",
    })

    mock_server = ThreadingHTTPServer(("127.0.0.1", 0), MockGitHubHandler)
    mock_port = mock_server.server_port
    server_thread = threading.Thread(target=mock_server.serve_forever, daemon=True)
    server_thread.start()

    try:
        with tempfile.TemporaryDirectory(prefix="godot-updater-live-") as temp:
            root = Path(temp)
            copied = root / "addons" / "godot_agent"
            copied.mkdir(parents=True)

            # Копируем agent_updater.gd и исходный plugin.cfg (0.7.0)
            shutil.copyfile(addon_dir / "agent_updater.gd", copied / "agent_updater.gd")
            (copied / "plugin.cfg").write_text('[plugin]\nname="Godot Agent"\nversion="0.7.0"\nscript="plugin_universal.gd"\n', encoding="utf-8")

            # Создаем runner скрипт и project.godot
            runner_code = RUNNER_GDSCRIPT.replace("{PORT}", str(mock_port))
            (root / "updater_runner.gd").write_text(runner_code, encoding="utf-8")
            (root / "project.godot").write_text(
                'config_version=5\n[application]\nconfig/name="Updater live sandbox"\n'
                '[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
                encoding="utf-8"
            )

            env = os.environ.copy()
            for name in ("APPDATA", "LOCALAPPDATA", "HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
                directory = root / "isolated_user" / name
                directory.mkdir(parents=True)
                env[name] = str(directory)

            cmd = [executable, "--headless", "--path", str(root), "--editor", "--language", "en", "--script", "res://updater_runner.gd"]

            print("RUN: " + subprocess.list2cmdline(cmd), flush=True)
            result = subprocess.run(cmd, env=env, cwd=root, capture_output=True,
                                    timeout=args.timeout, encoding="utf-8", errors="replace")

            output = result.stdout + result.stderr
            print(output)

            reports = [line[len(SENTINEL):] for line in result.stdout.splitlines()
                       if line.startswith(SENTINEL)]

            if not reports:
                print("FAIL: No sentinel received from Godot runner")
                return 1

            report = json.loads(reports[0])
            if not report.get("ok"):
                print("FAIL: Runner reported error: %s" % report.get("error"))
                return 1

            print("PASS: Live updater test succeeded! Report: %r" % report)
            print("Mock server release requests: %d, download requests: %d" %
                  (MockGitHubHandler.release_requests, MockGitHubHandler.download_requests))

            # Проверяем, что второй вызов был взят из кэша (только 1 запрос к /releases/latest)
            if MockGitHubHandler.release_requests != 1:
                print("FAIL: Expected exactly 1 release request (cache should prevent 2nd), got %d" %
                      MockGitHubHandler.release_requests)
                return 1

            if MockGitHubHandler.download_requests != 1:
                print("FAIL: Expected exactly 1 download request, got %d" %
                      MockGitHubHandler.download_requests)
                return 1

            return 0
    finally:
        mock_server.shutdown()


if __name__ == "__main__":
    sys.exit(main())
