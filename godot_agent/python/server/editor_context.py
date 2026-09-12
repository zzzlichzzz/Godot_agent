# -*- coding: utf-8 -*-
"""Validation and compact formatting for one-turn Godot editor snapshots."""

SCHEMA_VERSION = 1
DEFAULT_MAX_CHARS = 6000
HARD_MAX_CHARS = 10000
_START = "[Godot editor context v1; snapshot at send time, user request has priority]"
_END = "[/Godot editor context]"
_USER = "=== USER REQUEST ==="


def _text(value, limit=500):
    if not isinstance(value, str):
        return ""
    value = value.replace("\x00", "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[context truncated]"


def _path(value):
    value = _text(value, 300)
    return value if value.startswith("res://") else ""


def _positive_int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _format_code(value, limit):
    value = _text(value, limit)
    if not value:
        return []
    return ["    " + line for line in value.splitlines()]


def _scene_block(value):
    if not isinstance(value, dict):
        return []
    lines = []
    active = _path(value.get("active"))
    if active:
        lines.append("Active scene: " + active)
    elif value.get("unsaved") is True:
        lines.append("Active scene: unsaved")
    opened = []
    if isinstance(value.get("open"), list):
        for item in value["open"][:12]:
            path = _path(item)
            if path and path not in opened:
                opened.append(path)
    if opened:
        lines.append("Open scenes: " + ", ".join(opened))
    return lines


def _selection_block(value):
    if not isinstance(value, dict) or not isinstance(value.get("nodes"), list):
        return []
    lines = []
    for raw in value["nodes"][:8]:
        if not isinstance(raw, dict):
            continue
        path = _text(raw.get("path"), 300)
        node_type = _text(raw.get("type"), 100)
        if not path or not node_type:
            continue
        details = []
        script = _path(raw.get("script"))
        owner = _text(raw.get("owner"), 300)
        if script:
            details.append("script=" + script)
        if owner:
            details.append("owner=" + owner)
        groups = []
        if isinstance(raw.get("groups"), list):
            groups = [_text(x, 80) for x in raw["groups"][:8]]
            groups = [x for x in groups if x]
        if groups:
            details.append("groups=" + ",".join(groups))
        props = []
        if isinstance(raw.get("properties"), dict):
            for key in sorted(raw["properties"])[:12]:
                name = _text(key, 80)
                val = raw["properties"][key]
                if name and isinstance(val, (str, int, float, bool)):
                    props.append("%s=%s" % (name, _text(str(val), 120)))
        if props:
            details.append("properties=" + ", ".join(props))
        suffix = "; " + "; ".join(details) if details else ""
        lines.append("- %s (%s)%s" % (path, node_type, suffix))
    return (["Selected nodes:"] + lines) if lines else []


def _script_block(value):
    if not isinstance(value, dict):
        return []
    lines = []
    path = _path(value.get("path"))
    if path:
        lines.append("Current script: %s%s" % (
            path, " (unsaved)" if value.get("dirty") is True else ""))
    caret = value.get("caret")
    if isinstance(caret, dict):
        line = _positive_int(caret.get("line"))
        column = _positive_int(caret.get("column"))
        if line:
            lines.append("Caret: line %d%s" % (
                line, ", column %d" % column if column else ""))
    selected = value.get("selection")
    if isinstance(selected, dict) and _text(selected.get("text"), 1):
        first = _positive_int(selected.get("from_line"))
        last = _positive_int(selected.get("to_line"))
        label = "Selected code"
        if first:
            label += ", lines %d%s" % (first, "-%d" % last if last else "")
        lines.append(label + ":")
        lines.extend(_format_code(selected.get("text"), 4500))
    else:
        context = value.get("caret_context")
        if isinstance(context, dict):
            first = _positive_int(context.get("start_line"))
            last = _positive_int(context.get("end_line"))
            code = _format_code(context.get("text"), 3500)
            if code:
                label = "Code near caret"
                if first:
                    label += ", lines %d%s" % (first, "-%d" % last if last else "")
                lines.append(label + ":")
                lines.extend(code)
    opened = []
    if isinstance(value.get("open"), list):
        for item in value["open"][:12]:
            item = _path(item)
            if item and item != path and item not in opened:
                opened.append(item)
    if opened:
        lines.append("Other open scripts: " + ", ".join(opened))
    return lines


def _diagnostics_block(value):
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        return []
    lines = []
    for item in value["items"][:8]:
        if not isinstance(item, dict):
            continue
        message = _text(item.get("message"), 400)
        if not message:
            continue
        location = _path(item.get("path"))
        line = _positive_int(item.get("line"))
        if location and line:
            location += ":%d" % line
        elif not location:
            location = "editor"
        lines.append("- %s: %s" % (location, message))
    return (["Recent diagnostics:"] + lines) if lines else []


def _run_block(value):
    if not isinstance(value, dict) or not isinstance(value.get("playing"), bool):
        return []
    return ["Run state: " + ("playing" if value["playing"] else "stopped")]


def format_snapshot(value, max_chars=DEFAULT_MAX_CHARS):
    """Return (prompt block, section character counts), dropping malformed data."""
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return "", {}
    try:
        limit = max(512, min(int(max_chars), HARD_MAX_CHARS))
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_CHARS
    blocks = {
        "scene": _scene_block(value.get("scene")),
        "selection": _selection_block(value.get("selection")),
        "script": _script_block(value.get("script")),
        "diagnostics": _diagnostics_block(value.get("diagnostics")),
        "run": _run_block(value.get("run")),
    }
    stats = {name: len("\n".join(lines)) for name, lines in blocks.items() if lines}
    # Selection and diagnostics survive before lower-value scene/open-list context.
    priority = ("selection", "diagnostics", "script", "run", "scene")
    kept = {}
    remaining = limit - len(_START) - len(_END) - 2
    for name in priority:
        lines = blocks[name]
        if not lines or remaining <= 0:
            continue
        text = "\n".join(lines)
        if len(text) > remaining:
            if name not in ("selection", "diagnostics", "script") or remaining < 160:
                continue
            text = text[:remaining - 24].rstrip() + "\n[context truncated]"
        kept[name] = text
        remaining -= len(text) + 1
    order = ("scene", "selection", "script", "diagnostics", "run")
    body = "\n".join(kept[name] for name in order if name in kept)
    if not body:
        return "", stats
    result = _START + "\n" + body + "\n" + _END
    stats["total"] = len(result)
    return result, stats


def attach_to_prompt(user_prompt, snapshot, max_chars=DEFAULT_MAX_CHARS):
    block, stats = format_snapshot(snapshot, max_chars=max_chars)
    if not block:
        return user_prompt, stats
    return "%s\n\n%s\n%s" % (block, _USER, user_prompt), stats


def user_prompt_without_context(prompt):
    """Do not persist an ephemeral snapshot in API history."""
    if not isinstance(prompt, str) or not prompt.startswith(_START):
        return prompt
    marker = "\n\n%s\n" % _USER
    pos = prompt.find(marker)
    return prompt[pos + len(marker):] if pos >= 0 else prompt
