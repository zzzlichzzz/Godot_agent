# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import runtime_checks


def expect_error(fn, text):
    try:
        fn()
    except runtime_checks.RuntimeCheckError as exc:
        assert text in str(exc), (text, str(exc))
        return
    raise AssertionError("expected RuntimeCheckError containing %r" % text)


root = tempfile.mkdtemp(prefix="runtime_checks_")
try:
    os.makedirs(os.path.join(root, "scenes"))
    scene = os.path.join(root, "scenes", "main.tscn")
    with open(scene, "w", encoding="utf-8") as handle:
        handle.write('[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n')
    action = runtime_checks.normalize_action(root, {
        "action": "run_check", "scene": "res://scenes/main.tscn",
        "steps": [
            {"op": "wait_frames", "frames": 2},
            {"op": "input_action", "name": "jump", "pressed": True},
            {"op": "input_action", "name": "jump", "pressed": False},
            {"op": "assert_node", "node": ".", "exists": True},
            {"op": "assert_property", "node": ".", "property": "position",
             "operator": "approx", "expected": {"type": "Vector2", "value": [1, 2]},
             "tolerance": 0.01},
            {"op": "assert_no_errors"},
        ],
        "screenshot": {"when": "failure", "max_width": 320,
                       "max_height": 180, "quality": 0.6},
    })
    pending = runtime_checks.create_request(action, "chat", 3, root)
    assert "result_token" in runtime_checks.public_request(pending)
    pending.update({"state": "bound", "session_id": 4, "run_id": "run-4"})
    game = runtime_checks.game_request(pending)
    assert "result_token" not in game and game["run_id"] == "run-4"

    result = {"protocol": 1, "scene": action["scene"], "duration_ms": 30,
              "assertions": [
                  {"index": 3, "op": "assert_node", "actual": True},
                  {"index": 4, "op": "assert_property", "read_ok": True,
                   "actual": {"type": "Vector2", "value": [1.005, 2]}},
                  {"index": 5, "op": "assert_no_errors", "actual": True},
              ], "bridge_errors": [], "step_errors": [],
              "screenshot": {"ok": True, "data": "abc"}}
    report = runtime_checks.finalize_result(pending, result, log_available=True)
    assert report["passed"] and report["screenshot"] is None
    failed = dict(result, step_errors=[{"index": 1, "message": "InputMap action not found"}])
    report = runtime_checks.finalize_result(pending, failed, log_available=True)
    assert not report["passed"] and report["screenshot"]["data"] == "abc"
    assert "abc" not in runtime_checks.format_report(report)
    oversized_action = dict(action, screenshot={"when": "always", "width": 320, "height": 180, "quality": 0.6})
    oversized_pending = runtime_checks.create_request(oversized_action, "chat", 1, root, root)
    oversized = dict(result, screenshot={"ok": True, "data": "x" * 120001})
    oversized_report = runtime_checks.finalize_result(oversized_pending, oversized, log_available=True)
    assert not oversized_report["screenshot"]["ok"]

    log_dir = os.path.join(root, "logs")
    os.makedirs(log_dir)
    log_path = os.path.join(log_dir, "godot.log")
    with open(log_path, "wb") as handle:
        handle.write(b"startup\n")
    cursor = runtime_checks.capture_log_cursor(root)
    with open(log_path, "ab") as handle:
        handle.write(b"SCRIPT ERROR: check failure\n   at: res://player.gd:4\n")
    log_errors = runtime_checks.collect_log_errors(cursor)
    assert log_errors and runtime_checks.log_source_available(cursor)
    os.remove(log_path)
    assert not runtime_checks.log_source_available(cursor)

    with open(log_path, "wb") as handle:
        handle.write(b"base\n")
    cursor = runtime_checks.capture_log_cursor(root)
    with open(log_path, "ab") as handle:
        handle.write(b"x" * (runtime_checks.MAX_LOG_DELTA_BYTES + 1))
    assert runtime_checks.collect_log_errors(cursor) == []
    assert not runtime_checks.log_source_available(cursor)

    expect_error(lambda: runtime_checks.normalize_action(root, {
        "action": "run_check", "scene": action["scene"],
        "steps": [{"op": "wait_frames", "frames": 1}]}), "at least one assertion")
    expect_error(lambda: runtime_checks.normalize_action(root, {
        "action": "run_check", "scene": action["scene"],
        "steps": [{"op": "assert_node", "node": "../Main", "exists": True}]}),
        "unsafe segment")
    os.makedirs(os.path.join(root, "Addons"))
    with open(os.path.join(root, "Addons", "tool.tscn"), "w", encoding="utf-8") as handle:
        handle.write('[gd_scene format=3]\n\n[node name="Tool" type="Node"]\n')
    expect_error(lambda: runtime_checks.normalize_action(root, {
        "action": "run_check", "scene": "res://Addons/tool.tscn",
        "steps": [{"op": "assert_node", "node": ".", "exists": True}]}),
        "addon scenes")
    expect_error(lambda: runtime_checks.finalize_result(pending, dict(result, assertions=[]), log_available=True),
        "do not match")
    print("PASS runtime check schema, server assertions, screenshots and limits")
finally:
    shutil.rmtree(root, ignore_errors=True)
