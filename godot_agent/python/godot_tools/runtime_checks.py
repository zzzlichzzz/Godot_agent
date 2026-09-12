# -*- coding: utf-8 -*-
"""Strict deterministic game-check protocol; no arbitrary runtime RPC."""
import json
import math
import os
import secrets
import time

from project_tools import _resolve_safe_path


PROTOCOL = 1
MAX_STEPS = 32
MAX_INPUT_STEPS = 16
MAX_ASSERTIONS = 16
MAX_WAIT_FRAMES = 1200
MAX_WAIT_MS = 10000
MAX_RESULT_BYTES = 160 * 1024
MAX_HTTP_BODY_BYTES = 192 * 1024
MAX_LOG_DELTA_BYTES = 256 * 1024
RESULT_STATUSES = {
    "ok", "runtime_already_running", "launch_failed", "launch_timeout",
    "bridge_unavailable", "stale_runtime_session", "session_stopped",
    "timeout", "cancelled", "protocol_error", "response_too_large",
}
OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "approx"}
SAFE_TYPES = {"Vector2": 2, "Vector2i": 2, "Vector3": 3, "Vector3i": 3, "Color": 4}


class RuntimeCheckError(ValueError):
    pass


def _exact(value, allowed, name):
    if not isinstance(value, dict):
        raise RuntimeCheckError("%s must be an object" % name)
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise RuntimeCheckError("unknown %s fields: %s" % (name, ", ".join(unknown)))


def _text(value, name, limit, allow_empty=False):
    if not isinstance(value, str):
        raise RuntimeCheckError("%s must be text" % name)
    value = value.strip()
    if (not value and not allow_empty) or len(value) > limit:
        raise RuntimeCheckError("%s must contain %s..%d characters" % (
            name, 0 if allow_empty else 1, limit))
    return value


def _node_path(value):
    value = _text(value, "node", 256)
    if value == ".":
        return value
    if value.startswith("/") or "\\" in value or ":" in value or "//" in value or value.endswith("/"):
        raise RuntimeCheckError("node path must be relative to current_scene")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise RuntimeCheckError("node path contains an unsafe segment")
    return value


def _property_name(value):
    value = _text(value, "property", 96)
    if any(mark in value for mark in (".", ":", "/", "(", ")")):
        raise RuntimeCheckError("nested properties and expressions are forbidden")
    return value


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise RuntimeCheckError("%s must be a finite number" % name)
    return value


def _expected(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _number(value, "expected")
    if isinstance(value, str):
        return _text(value, "expected", 2048, allow_empty=True)
    if isinstance(value, dict):
        _exact(value, {"type", "value"}, "typed expected value")
        kind = value.get("type")
        if kind not in SAFE_TYPES:
            raise RuntimeCheckError("unsupported expected value type")
        items = value.get("value")
        if not isinstance(items, list) or len(items) != SAFE_TYPES[kind]:
            raise RuntimeCheckError("typed expected value has invalid arity")
        return {"type": kind, "value": [_number(item, "expected component") for item in items]}
    raise RuntimeCheckError("expected must be a bounded scalar or typed vector/color")


def _scene_path(project_root, value, allow_addons):
    path = _text(value, "scene", 256).replace("\\", "/")
    if not path.startswith("res://") or not path.lower().endswith(".tscn"):
        raise RuntimeCheckError("scene must be an existing res://*.tscn")
    if path.lower().startswith("res://addons/") and not allow_addons:
        raise RuntimeCheckError("addon scenes require explicit addon intent")
    absolute = _resolve_safe_path(project_root, path)
    if not os.path.isfile(absolute):
        raise RuntimeCheckError("scene not found: %s" % path)
    return path


def normalize_action(project_root, action, allow_addons=False):
    _exact(action, {"action", "scene", "steps", "timeout_ms", "screenshot", "reason"}, "run_check")
    if action.get("action") != "run_check":
        raise RuntimeCheckError("action must be run_check")
    scene = _scene_path(project_root, action.get("scene"), allow_addons)
    raw_steps = action.get("steps")
    if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= MAX_STEPS:
        raise RuntimeCheckError("steps must contain 1..%d operations" % MAX_STEPS)
    steps = []
    input_count = assertion_count = wait_frames = wait_ms = no_errors = 0
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise RuntimeCheckError("step %d must be an object" % index)
        op = raw.get("op")
        if op == "wait_frames":
            _exact(raw, {"op", "frames"}, "wait_frames")
            frames = int(raw.get("frames") or 0)
            if not 1 <= frames <= 600:
                raise RuntimeCheckError("wait_frames.frames must be 1..600")
            wait_frames += frames
            step = {"op": op, "frames": frames}
        elif op == "wait_time":
            _exact(raw, {"op", "ms"}, "wait_time")
            ms = int(raw.get("ms") or 0)
            if not 1 <= ms <= 5000:
                raise RuntimeCheckError("wait_time.ms must be 1..5000")
            wait_ms += ms
            step = {"op": op, "ms": ms}
        elif op == "input_action":
            _exact(raw, {"op", "name", "pressed", "strength"}, "input_action")
            name = _text(raw.get("name"), "InputMap action", 96)
            if not isinstance(raw.get("pressed"), bool):
                raise RuntimeCheckError("input_action.pressed must be bool")
            pressed = raw["pressed"]
            strength = float(_number(raw.get("strength", 1.0 if pressed else 0.0), "input strength"))
            if not 0.0 <= strength <= 1.0 or (not pressed and "strength" in raw):
                raise RuntimeCheckError("input strength must be 0..1 and is only valid when pressed")
            input_count += 1
            step = {"op": op, "name": name, "pressed": pressed, "strength": strength}
        elif op == "assert_node":
            _exact(raw, {"op", "node", "exists"}, "assert_node")
            if not isinstance(raw.get("exists"), bool):
                raise RuntimeCheckError("assert_node.exists must be bool")
            assertion_count += 1
            step = {"op": op, "node": _node_path(raw.get("node")), "exists": raw["exists"]}
        elif op == "assert_property":
            _exact(raw, {"op", "node", "property", "operator", "expected", "tolerance"}, "assert_property")
            operator = raw.get("operator")
            if operator not in OPERATORS:
                raise RuntimeCheckError("unsupported assertion operator")
            step = {"op": op, "node": _node_path(raw.get("node")),
                    "property": _property_name(raw.get("property")),
                    "operator": operator, "expected": _expected(raw.get("expected"))}
            if operator == "approx":
                tolerance = float(_number(raw.get("tolerance", 0.001), "tolerance"))
                if not 0.0 <= tolerance <= 1000000.0:
                    raise RuntimeCheckError("tolerance must be 0..1000000")
                step["tolerance"] = tolerance
            elif "tolerance" in raw:
                raise RuntimeCheckError("tolerance is only valid for approx")
            assertion_count += 1
        elif op == "assert_no_errors":
            _exact(raw, {"op"}, "assert_no_errors")
            no_errors += 1
            assertion_count += 1
            step = {"op": op}
        else:
            raise RuntimeCheckError("unsupported run_check step: %s" % op)
        step["index"] = index
        steps.append(step)
    if input_count > MAX_INPUT_STEPS or assertion_count > MAX_ASSERTIONS:
        raise RuntimeCheckError("run_check exceeds input/assertion limits")
    if assertion_count < 1:
        raise RuntimeCheckError("run_check requires at least one assertion")
    if wait_frames > MAX_WAIT_FRAMES or wait_ms > MAX_WAIT_MS:
        raise RuntimeCheckError("run_check exceeds total wait limits")
    if no_errors > 1:
        raise RuntimeCheckError("assert_no_errors may appear only once")
    timeout_ms = int(action.get("timeout_ms", 12000))
    if not 1000 <= timeout_ms <= 20000:
        raise RuntimeCheckError("timeout_ms must be 1000..20000")
    screenshot = action.get("screenshot") or {"when": "never"}
    _exact(screenshot, {"when", "max_width", "max_height", "quality"}, "screenshot")
    when = screenshot.get("when", "never")
    if when not in ("never", "always", "failure"):
        raise RuntimeCheckError("screenshot.when must be never, always, or failure")
    width = int(screenshot.get("max_width", 480))
    height = int(screenshot.get("max_height", 270))
    quality = float(_number(screenshot.get("quality", 0.65), "screenshot quality"))
    if not 64 <= width <= 480 or not 64 <= height <= 270 or not 0.4 <= quality <= 0.8:
        raise RuntimeCheckError("screenshot limits are 64..480 x 64..270 and quality 0.4..0.8")
    reason = _text(action.get("reason", ""), "reason", 300, allow_empty=True)
    return {"action": "run_check", "scene": scene, "steps": steps,
            "timeout_ms": timeout_ms,
            "screenshot": {"when": when, "max_width": width,
                           "max_height": height, "quality": quality},
            "reason": reason}


def _log_path(user_data_dir):
    return os.path.join(str(user_data_dir or ""), "logs", "godot.log")


def capture_log_cursor(user_data_dir):
    path = _log_path(user_data_dir)
    try:
        stat = os.stat(path)
        return {"path": path, "offset": stat.st_size, "available": True,
                "device": getattr(stat, "st_dev", None),
                "inode": getattr(stat, "st_ino", None), "complete": None}
    except OSError:
        return {"path": path, "offset": 0, "available": False, "complete": False}


def collect_log_errors(cursor):
    if not isinstance(cursor, dict):
        return []
    path = str(cursor.get("path") or "")
    try:
        stat = os.stat(path)
        offset = max(0, int(cursor.get("offset") or 0))
        same_file = ((cursor.get("device") is None or cursor.get("device") == getattr(stat, "st_dev", None))
                     and (cursor.get("inode") in (None, 0) or cursor.get("inode") == getattr(stat, "st_ino", None)))
        delta_size = stat.st_size - offset
        if not same_file or delta_size < 0 or delta_size > MAX_LOG_DELTA_BYTES:
            cursor["complete"] = False
            return []
        with open(path, "rb") as handle:
            handle.seek(offset)
            raw = handle.read(delta_size)
    except OSError:
        cursor["complete"] = False
        return []
    cursor["complete"] = len(raw) == delta_size
    lines = raw.decode("utf-8", errors="replace").splitlines()
    errors = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        upper = stripped.upper()
        if not (upper.startswith("ERROR") or upper.startswith("SCRIPT ERROR")
                or "SCRIPT ERROR:" in upper):
            continue
        stack = []
        for following in lines[index + 1:index + 17]:
            item = following.strip()
            if item.startswith("at:"):
                stack.append(item[3:].strip()[:512])
            elif item:
                break
        errors.append({"message": stripped[:2048], "stack": stack})
        if len(errors) >= 25:
            break
    return errors


def log_source_available(cursor):
    if not isinstance(cursor, dict):
        return False
    if not bool(cursor.get("available")) or cursor.get("complete") is not True:
        return False
    path = str(cursor.get("path") or "")
    try:
        stat = os.stat(path)
    except OSError:
        return False
    return ((cursor.get("device") is None or cursor.get("device") == getattr(stat, "st_dev", None))
            and (cursor.get("inode") in (None, 0) or cursor.get("inode") == getattr(stat, "st_ino", None)))


def create_request(action, chat_id, turn_id, project_root, user_data_dir=None):
    now = time.time()
    return {"protocol": PROTOCOL, "request_id": secrets.token_hex(16),
            "result_token": secrets.token_hex(24), "chat_id": chat_id,
            "turn_id": int(turn_id or 0), "project_root": project_root,
            "state": "awaiting_bind", "session_id": None, "run_id": "",
            "action": action, "deadline": now + action["timeout_ms"] / 1000.0 + 12.0,
            "log_cursor": capture_log_cursor(user_data_dir)}


def public_request(pending):
    action = pending["action"]
    return {"protocol": PROTOCOL, "request_id": pending["request_id"],
            "result_token": pending["result_token"], "scene": action["scene"],
            "timeout_ms": action["timeout_ms"]}


def game_request(pending):
    action = pending["action"]
    return {"protocol": PROTOCOL, "request_id": pending["request_id"],
            "run_id": pending["run_id"], "steps": action["steps"],
            "timeout_ms": action["timeout_ms"], "screenshot": action["screenshot"]}


def normalize_result(value):
    if not isinstance(value, dict):
        raise RuntimeCheckError("runtime check result must be an object")
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        raise RuntimeCheckError("runtime check result exceeds 160 KiB")
    if int(value.get("protocol") or 0) != PROTOCOL:
        raise RuntimeCheckError("runtime check protocol mismatch")
    assertions = value.get("assertions")
    if not isinstance(assertions, list) or len(assertions) > MAX_ASSERTIONS:
        raise RuntimeCheckError("runtime assertion results are invalid")
    out = {"protocol": PROTOCOL, "scene": str(value.get("scene") or "")[:256],
           "duration_ms": max(0, int(value.get("duration_ms") or 0)),
           "assertions": [], "bridge_errors": [], "step_errors": []}
    for raw in assertions:
        if not isinstance(raw, dict):
            raise RuntimeCheckError("runtime assertion result must be an object")
        item = {"index": int(raw.get("index", -1)), "op": str(raw.get("op") or "")[:32]}
        if "actual" in raw:
            item["actual"] = _expected(raw["actual"])
        if "read_ok" in raw:
            item["read_ok"] = bool(raw["read_ok"])
        if raw.get("error"):
            item["error"] = str(raw["error"])[:256]
        out["assertions"].append(item)
    for raw in (value.get("bridge_errors") or [])[:25]:
        if isinstance(raw, dict):
            out["bridge_errors"].append({"message": str(raw.get("message") or "")[:2048]})
    for raw in (value.get("step_errors") or [])[:25]:
        if isinstance(raw, dict):
            out["step_errors"].append({"index": int(raw.get("index", -1)),
                                       "message": str(raw.get("message") or "")[:512]})
    if isinstance(value.get("screenshot"), dict):
        shot = value["screenshot"]
        data = str(shot.get("data") or "")
        if len(data) > 120000:
            out["screenshot"] = {"ok": False, "data": "", "error": "screenshot_too_large"}
        else:
            out["screenshot"] = {"ok": bool(shot.get("ok")), "data": data,
                                  "error": str(shot.get("error") or "")[:128]}
    return out


def _components(value):
    if isinstance(value, dict) and value.get("type") in SAFE_TYPES:
        items = value.get("value")
        if isinstance(items, list) and len(items) == SAFE_TYPES[value["type"]]:
            return value["type"], items
    return None, None


def _equal(actual, expected, tolerance=0.0):
    actual_type, actual_items = _components(actual)
    expected_type, expected_items = _components(expected)
    if actual_type or expected_type:
        if actual_type != expected_type:
            return False
        return all(abs(float(a) - float(b)) <= tolerance for a, b in zip(actual_items, expected_items))
    if isinstance(actual, (int, float)) and not isinstance(actual, bool) and isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return abs(float(actual) - float(expected)) <= tolerance
    return actual == expected


def _compare(actual, expected, operator, tolerance):
    if operator == "eq": return _equal(actual, expected)
    if operator == "ne": return not _equal(actual, expected)
    if operator == "approx": return _equal(actual, expected, tolerance)
    if isinstance(actual, bool) or isinstance(expected, bool): return False
    if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)): return False
    if operator == "gt": return actual > expected
    if operator == "gte": return actual >= expected
    if operator == "lt": return actual < expected
    if operator == "lte": return actual <= expected
    return False


def finalize_result(pending, result, log_errors=None, log_available=True):
    result = normalize_result(result)
    action = pending["action"]
    if result["scene"] != action["scene"]:
        raise RuntimeCheckError("runtime check scene does not match requested scene")
    expected = [step for step in action["steps"] if step["op"].startswith("assert_")]
    by_index = {}
    for item in result["assertions"]:
        if item["index"] in by_index:
            raise RuntimeCheckError("duplicate runtime assertion result")
        by_index[item["index"]] = item
    if set(by_index) != {item["index"] for item in expected}:
        raise RuntimeCheckError("runtime assertion results do not match requested steps")
    failures = ["step %d (%s)" % (item["index"], item["message"])
                for item in result.get("step_errors") or []]
    details = []
    merged_errors = list(result.get("bridge_errors") or []) + list(log_errors or [])
    for step in expected:
        actual = by_index[step["index"]]
        if actual.get("op") != step["op"]:
            raise RuntimeCheckError("runtime assertion operation mismatch")
        passed = False
        if step["op"] == "assert_node":
            passed = bool(actual.get("actual")) == step["exists"]
        elif step["op"] == "assert_property":
            passed = bool(actual.get("read_ok")) and _compare(
                actual.get("actual"), step["expected"], step["operator"], step.get("tolerance", 0.0))
        elif step["op"] == "assert_no_errors":
            passed = bool(log_available) and not merged_errors
        detail = {"index": step["index"], "op": step["op"], "passed": passed}
        if "actual" in actual: detail["actual"] = actual["actual"]
        if actual.get("error"): detail["error"] = actual["error"]
        details.append(detail)
        if not passed:
            failures.append("step %d (%s)" % (step["index"], step["op"]))
            if step["op"] == "assert_no_errors" and not log_available:
                merged_errors.append({"message": "Godot file log is unavailable; assert_no_errors cannot be evaluated"})
    passed = not failures
    screenshot = result.get("screenshot")
    if action.get("screenshot", {}).get("when") == "failure" and passed:
        screenshot = None
    return {"protocol": PROTOCOL, "scene": action["scene"], "passed": passed,
            "duration_ms": result["duration_ms"], "assertions": details,
            "failures": failures, "errors": merged_errors[:25],
            "screenshot": screenshot}


def format_report(report):
    safe = dict(report)
    safe.pop("screenshot", None)
    text = json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True)
    return ("[Godot local game check; deterministic evidence]\n" + text[:16000]
            + "\n[/Godot local game check]\nAnalyze the failed assertions/errors once; do not request an automatic check loop.")
