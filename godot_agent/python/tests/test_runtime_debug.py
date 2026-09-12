# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import runtime_debug


def expect_error(fn, text):
    try:
        fn()
    except runtime_debug.RuntimeDebugError as exc:
        assert text in str(exc), (text, str(exc))
        return
    raise AssertionError("expected RuntimeDebugError containing %r" % text)


status = runtime_debug.normalize_status({"enabled": True, "sessions": [
    {"session_id": 7, "run_id": "run-7", "active": True,
     "breaked": False, "debuggable": True, "bridge_ready": True},
]})
action = runtime_debug.normalize_action({
    "action": "inspect_runtime",
    "sections": ["active_scene", "tree", "properties", "metrics", "errors"],
    "properties": [{"node": "Player", "names": ["health", "global_position"]}],
    "session_id": 7, "max_age_ms": 1000, "reason": "Проверить состояние игры",
})
request = runtime_debug.create_request(action, status, "chat-1", 4, timeout_ms=2500)
public = runtime_debug.public_request(request)
assert public["session_id"] == 7 and public["run_id"] == "run-7"
assert len(public["request_id"]) == 32 and len(public["result_token"]) == 48
assert "chat_id" not in public and "deadline" not in public
assert runtime_debug.select_session(status)["session_id"] == 7

prompt = runtime_debug.attach_status("USER", status)
assert prompt.endswith("USER") and "bridge-ready" in prompt
assert runtime_debug.strip_status(prompt) == "USER"

snapshot = runtime_debug.normalize_snapshot({
    "protocol": 1,
    "captured_at_ticks_ms": 100,
    "active_scene": {"path": ".", "type": "Node2D"},
    "tree": {"nodes": [{"path": ".", "type": "Node2D"}]},
    "properties": [{"node": "Player", "name": "health", "ok": True, "value": 10}],
    "metrics": {"fps": 60.0}, "errors": {"items": []},
    "unknown": "discarded",
})
report = runtime_debug.format_snapshot(snapshot)
assert len(report) <= runtime_debug.MAX_REPORT_CHARS + 200
assert "unknown" not in report and "Godot runtime snapshot" in report

expect_error(lambda: runtime_debug.normalize_snapshot({
    "protocol": 2, "tree": {"nodes": []}}), "protocol mismatch")
expect_error(lambda: runtime_debug.validate_snapshot_request(
    {"protocol": 1, "tree": {"nodes": []}},
    {"sections": ["tree", "metrics"], "properties": []}), "misses requested")

import api_backend
import api_history
assert api_backend._guess_user_kind(report) == api_history.KIND_TOOL_RESULT

expect_error(lambda: runtime_debug.normalize_action({
    "action": "inspect_runtime", "sections": ["properties"], "properties": []}),
    "explicit selectors")
expect_error(lambda: runtime_debug.normalize_action({
    "action": "inspect_runtime", "sections": ["tree"], "set_property": True}),
    "unknown inspect_runtime fields")
expect_error(lambda: runtime_debug.normalize_action({
    "action": "inspect_runtime", "sections": ["properties"],
    "properties": [{"node": "../Player", "names": ["health"]}]}),
    "unsafe segment")
expect_error(lambda: runtime_debug.select_session({"enabled": True, "sessions": []}),
    "runtime_not_running")
expect_error(lambda: runtime_debug.select_session({"enabled": True, "sessions": [
    {"session_id": 1, "run_id": "a", "active": True, "bridge_ready": True},
    {"session_id": 2, "run_id": "b", "active": True, "bridge_ready": True},
]}), "ambiguous_session")

print("PASS runtime debug schemas, tokens, limits and formatting")
