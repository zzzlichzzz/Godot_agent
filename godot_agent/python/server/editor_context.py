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


def normalize_snapshot(value):
    """Return a bounded primitive-only schema-v1 snapshot for later local tools."""
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        return {}
    out = {"schema_version": SCHEMA_VERSION}
    scene = value.get("scene")
    if isinstance(scene, dict):
        clean = {}
        active = _path(scene.get("active"))
        if active:
            clean["active"] = active
        elif scene.get("unsaved") is True:
            clean["unsaved"] = True
        opened = []
        for item in scene.get("open", [])[:12] if isinstance(scene.get("open"), list) else []:
            path = _path(item)
            if path and path not in opened:
                opened.append(path)
        if opened:
            clean["open"] = opened
        if clean:
            out["scene"] = clean
    selection = value.get("selection")
    nodes = []
    if isinstance(selection, dict) and isinstance(selection.get("nodes"), list):
        for raw in selection["nodes"][:8]:
            if not isinstance(raw, dict):
                continue
            path, node_type = _text(raw.get("path"), 300), _text(raw.get("type"), 100)
            if not path or not node_type:
                continue
            node = {"path": path, "type": node_type}
            script = _path(raw.get("script"))
            owner = _text(raw.get("owner"), 300)
            if script:
                node["script"] = script
            if owner:
                node["owner"] = owner
            groups = [_text(x, 80) for x in raw.get("groups", [])[:8]] if isinstance(raw.get("groups"), list) else []
            groups = [x for x in groups if x]
            if groups:
                node["groups"] = groups
            props = {}
            if isinstance(raw.get("properties"), dict):
                for key in sorted(raw["properties"])[:12]:
                    name, val = _text(key, 80), raw["properties"][key]
                    if name and isinstance(val, (str, int, float, bool)):
                        props[name] = _text(str(val), 120) if isinstance(val, str) else val
            if props:
                node["properties"] = props
            nodes.append(node)
    if nodes:
        out["selection"] = {"nodes": nodes}
    script = value.get("script")
    if isinstance(script, dict):
        clean = {}
        path = _path(script.get("path"))
        if path:
            clean["path"] = path
        if script.get("dirty") is True:
            clean["dirty"] = True
        caret = script.get("caret")
        if isinstance(caret, dict):
            line, column = _positive_int(caret.get("line")), _positive_int(caret.get("column"))
            if line:
                clean["caret"] = {"line": line}
                if column:
                    clean["caret"]["column"] = column
        selected = script.get("selection")
        if isinstance(selected, dict):
            text = _text(selected.get("text"), 4500)
            if text:
                clean["selection"] = {"text": text}
                for key in ("from_line", "from_column", "to_line", "to_column"):
                    number = _positive_int(selected.get(key))
                    if number:
                        clean["selection"][key] = number
        if "selection" not in clean:
            context = script.get("caret_context")
            if isinstance(context, dict):
                text = _text(context.get("text"), 3500)
                if text:
                    clean["caret_context"] = {"text": text}
                    for key in ("start_line", "end_line"):
                        number = _positive_int(context.get(key))
                        if number:
                            clean["caret_context"][key] = number
        opened = []
        for item in script.get("open", [])[:12] if isinstance(script.get("open"), list) else []:
            item = _path(item)
            if item and item not in opened:
                opened.append(item)
        if opened:
            clean["open"] = opened
        if clean:
            out["script"] = clean
    diagnostics = value.get("diagnostics")
    items = []
    if isinstance(diagnostics, dict) and isinstance(diagnostics.get("items"), list):
        for raw in diagnostics["items"][:8]:
            if not isinstance(raw, dict):
                continue
            message = _text(raw.get("message"), 400)
            if not message:
                continue
            item = {"message": message}
            path, line = _path(raw.get("path")), _positive_int(raw.get("line"))
            if path:
                item["path"] = path
            if line:
                item["line"] = line
            items.append(item)
    if items:
        out["diagnostics"] = {"items": items}
    run = value.get("run")
    if isinstance(run, dict) and isinstance(run.get("playing"), bool):
        out["run"] = {"playing": run["playing"]}
    return out if len(out) > 1 else {}


def format_snapshot(value, max_chars=DEFAULT_MAX_CHARS):
    """Return (prompt block, section character counts), dropping malformed data."""
    value = normalize_snapshot(value)
    if not value:
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
