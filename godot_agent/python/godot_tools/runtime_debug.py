# -*- coding: utf-8 -*-
"""Bounded, read-only runtime debugger protocol shared by Flask routes/tests."""
import json
import secrets
import time


PROTOCOL = 1
SECTIONS = ("active_scene", "tree", "properties", "errors", "metrics", "events")
RESULT_STATUSES = {
    "ok", "runtime_not_running", "ambiguous_session", "bridge_unavailable",
    "session_stopped", "stale_runtime_session", "timeout", "protocol_error",
    "response_too_large",
}
MAX_SNAPSHOT_BYTES = 96 * 1024
MAX_HTTP_BODY_BYTES = 128 * 1024
MAX_REPORT_CHARS = 20000


class RuntimeDebugError(ValueError):
    pass


def _text(value, name, limit, allow_empty=False):
    if not isinstance(value, str):
        raise RuntimeDebugError("%s must be text" % name)
    value = value.strip()
    if (not value and not allow_empty) or len(value) > limit:
        raise RuntimeDebugError("%s must contain 1..%d characters" % (name, limit))
    return value


def _node_path(value):
    value = _text(value, "property node", 256)
    if value == ".":
        return value
    if (value.startswith("/") or "\\" in value or ":" in value
            or "//" in value or value.endswith("/")):
        raise RuntimeDebugError("runtime node path must be relative to current_scene")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise RuntimeDebugError("runtime node path contains an unsafe segment")
    return value


def normalize_status(value):
    if not isinstance(value, dict):
        return {"enabled": False, "protocol": PROTOCOL, "sessions": []}
    sessions = []
    for raw in value.get("sessions") or []:
        if not isinstance(raw, dict) or len(sessions) >= 8:
            continue
        try:
            session_id = int(raw.get("session_id"))
        except (TypeError, ValueError):
            continue
        run_id = str(raw.get("run_id") or "")[:96]
        sessions.append({
            "session_id": session_id,
            "run_id": run_id,
            "active": bool(raw.get("active")),
            "breaked": bool(raw.get("breaked")),
            "debuggable": bool(raw.get("debuggable")),
            "bridge_ready": bool(raw.get("bridge_ready")),
        })
    return {"enabled": bool(value.get("enabled", True)),
            "protocol": PROTOCOL, "sessions": sessions}


def status_prompt(status):
    status = normalize_status(status)
    ready = [item for item in status["sessions"]
             if item["active"] and item["bridge_ready"]]
    if not status["enabled"]:
        message = "Runtime debugger: disabled."
    elif ready:
        details = ", ".join("%d%s" % (item["session_id"], " paused" if item["breaked"] else "")
                            for item in ready)
        message = "Runtime debugger: %d bridge-ready session(s): %s." % (len(ready), details)
    elif any(item["active"] for item in status["sessions"]):
        message = "Runtime debugger: game is running, but AgentRuntimeBridge is not ready."
    else:
        message = "Runtime debugger: no active game session."
    return "[Godot runtime status; no snapshot]\n%s\n[/Godot runtime status]\n\n" % message


def attach_status(prompt, status):
    return status_prompt(status) + str(prompt or "")


def strip_status(prompt):
    text = str(prompt or "")
    start = text.find("[Godot runtime status; no snapshot]")
    end_marker = "[/Godot runtime status]"
    if start < 0:
        return text
    end = text.find(end_marker, start)
    if end < 0:
        return text
    return (text[:start] + text[end + len(end_marker):]).lstrip("\r\n")


def normalize_action(action):
    if not isinstance(action, dict):
        raise RuntimeDebugError("inspect_runtime must be an object")
    allowed = {"action", "sections", "properties", "session_id", "max_age_ms", "reason"}
    unknown = sorted(set(action) - allowed)
    if unknown:
        raise RuntimeDebugError("unknown inspect_runtime fields: %s" % ", ".join(unknown))
    if action.get("action") != "inspect_runtime":
        raise RuntimeDebugError("action must be inspect_runtime")
    raw_sections = action.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise RuntimeDebugError("sections must be a non-empty list")
    sections = []
    for item in raw_sections:
        if item not in SECTIONS:
            raise RuntimeDebugError("unknown runtime section: %s" % item)
        if item not in sections:
            sections.append(item)
    properties = []
    raw_properties = action.get("properties") or []
    if not isinstance(raw_properties, list) or len(raw_properties) > 8:
        raise RuntimeDebugError("properties must contain at most 8 selectors")
    total_names = 0
    seen = set()
    for selector in raw_properties:
        if not isinstance(selector, dict) or set(selector) != {"node", "names"}:
            raise RuntimeDebugError("each property selector needs exactly node and names")
        node = _node_path(selector.get("node"))
        names = selector.get("names")
        if not isinstance(names, list) or not names or len(names) > 8:
            raise RuntimeDebugError("property names must contain 1..8 values")
        normalized_names = []
        for raw_name in names:
            name = _text(raw_name, "property name", 96)
            if any(mark in name for mark in (".", ":", "/", "(", ")")):
                raise RuntimeDebugError("nested properties and expressions are forbidden")
            if name not in normalized_names:
                normalized_names.append(name)
        total_names += len(normalized_names)
        if total_names > 32:
            raise RuntimeDebugError("at most 32 runtime properties may be read")
        key = (node, tuple(normalized_names))
        if key not in seen:
            seen.add(key)
            properties.append({"node": node, "names": normalized_names})
    if properties and "properties" not in sections:
        raise RuntimeDebugError("properties selectors require the properties section")
    if "properties" in sections and not properties:
        raise RuntimeDebugError("properties section requires explicit selectors")
    session_id = action.get("session_id")
    if session_id is not None:
        try:
            session_id = int(session_id)
        except (TypeError, ValueError):
            raise RuntimeDebugError("session_id must be an integer")
        if session_id < 0:
            raise RuntimeDebugError("session_id must be non-negative")
    try:
        max_age_ms = int(action.get("max_age_ms", 1000))
    except (TypeError, ValueError):
        raise RuntimeDebugError("max_age_ms must be an integer")
    if max_age_ms < 0 or max_age_ms > 5000:
        raise RuntimeDebugError("max_age_ms must be 0..5000")
    reason = action.get("reason")
    if reason is not None:
        reason = _text(reason, "reason", 300, allow_empty=True)
    return {"action": "inspect_runtime", "sections": sections,
            "properties": properties, "session_id": session_id,
            "max_age_ms": max_age_ms, "reason": reason or ""}


def select_session(status, session_id=None):
    status = normalize_status(status)
    if not status["enabled"]:
        raise RuntimeDebugError("runtime debugger is disabled")
    ready = [item for item in status["sessions"]
             if item["active"] and item["bridge_ready"]]
    if session_id is not None:
        for item in ready:
            if item["session_id"] == session_id:
                return item
        raise RuntimeDebugError("requested runtime session is not active and bridge-ready")
    if not ready:
        raise RuntimeDebugError("runtime_not_running: no bridge-ready game session")
    if len(ready) != 1:
        raise RuntimeDebugError("ambiguous_session: specify session_id")
    return ready[0]


def create_request(action, status, chat_id, turn_id, timeout_ms=3000):
    action = normalize_action(action)
    session = select_session(status, action.get("session_id"))
    now = time.time()
    return {
        "protocol": PROTOCOL,
        "request_id": secrets.token_hex(16),
        "result_token": secrets.token_hex(24),
        "chat_id": chat_id,
        "turn_id": int(turn_id or 0),
        "session_id": session["session_id"],
        "run_id": session["run_id"],
        "sections": action["sections"],
        "properties": action["properties"],
        "max_age_ms": action["max_age_ms"],
        "timeout_ms": int(timeout_ms),
        "deadline": now + max(1.0, timeout_ms / 1000.0 + 2.0),
    }


def public_request(pending):
    return {key: pending[key] for key in (
        "protocol", "request_id", "result_token", "session_id", "run_id",
        "sections", "properties", "max_age_ms", "timeout_ms")}


def runtime_request(pending):
    """Fields allowed to cross into the running game; excludes the HTTP token."""
    return {key: pending[key] for key in (
        "protocol", "request_id", "run_id", "sections", "properties", "max_age_ms")}


def _bounded_value(value, depth=0):
    if depth > 4:
        return "<depth limit>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:2048]
    if isinstance(value, list):
        return [_bounded_value(item, depth + 1) for item in value[:64]]
    if isinstance(value, dict):
        out = {}
        for key in list(value)[:32]:
            if isinstance(key, str):
                out[key[:96]] = _bounded_value(value[key], depth + 1)
        return out
    return "<unsupported>"


def normalize_snapshot(value):
    if not isinstance(value, dict):
        raise RuntimeDebugError("runtime snapshot must be an object")
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise RuntimeDebugError("runtime snapshot exceeds 96 KiB")
    if int(value.get("protocol") or 0) != PROTOCOL:
        raise RuntimeDebugError("runtime snapshot protocol mismatch")
    out = {"protocol": PROTOCOL}
    for key in SECTIONS:
        if key in value:
            out[key] = _bounded_value(value[key])
    out["captured_at_ticks_ms"] = int(value.get("captured_at_ticks_ms") or 0)
    return out


def validate_snapshot_request(snapshot, pending):
    expected_sections = set(pending.get("sections") or [])
    present_sections = set(snapshot) & set(SECTIONS)
    missing = sorted(expected_sections - present_sections)
    unexpected = sorted(present_sections - expected_sections)
    if missing:
        raise RuntimeDebugError("runtime snapshot misses requested sections: %s" % ", ".join(missing))
    if unexpected:
        raise RuntimeDebugError("runtime snapshot contains unrequested sections: %s" % ", ".join(unexpected))
    if "properties" not in expected_sections:
        return
    values = snapshot.get("properties")
    if not isinstance(values, list):
        raise RuntimeDebugError("runtime properties must be a list")
    received = []
    for item in values:
        if not isinstance(item, dict):
            raise RuntimeDebugError("runtime property result must be an object")
        node = item.get("node")
        name = item.get("name")
        if not isinstance(node, str) or not isinstance(name, str):
            raise RuntimeDebugError("runtime property result needs node and name")
        received.append((node, name))
    expected = [(selector["node"], name)
                for selector in pending.get("properties") or [] for name in selector["names"]]
    if sorted(received) != sorted(expected):
        raise RuntimeDebugError("runtime property results do not match requested selectors")


def format_snapshot(snapshot):
    compact = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    if len(compact) > MAX_REPORT_CHARS:
        compact = compact[:MAX_REPORT_CHARS - 160] + "\n... <runtime report truncated>"
    return ("[Godot runtime snapshot; read-only evidence from the running game]\n"
            + compact + "\n[/Godot runtime snapshot]\n"
            "Analyze all requested sections together. Do not invent omitted runtime data.")
