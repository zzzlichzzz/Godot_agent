# -*- coding: utf-8 -*-
"""Bounded, read-only context bundle for one model follow-up."""
import re

import editor_context
import gd_api_cache
import gd_functions
import gd_lint
import gd_api_check
import librarian
import log_reader
import tscn_lint
from project_tools import (_resolve_safe_path, describe_scene, read_project_file,
                           search_project_text, is_addon_path)


DEFAULT_MAX_CHARS = 12000
MIN_MAX_CHARS = 2000
HARD_MAX_CHARS = 20000
MAX_SYMBOLS = 8
MAX_API_CLASSES = 4
_CLASS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CLASS_NAME_RE = re.compile(r"(?m)^\s*class_name\s+([A-Za-z_]\w*)\b")
_AUTOLOAD_RE = re.compile(r'^([A-Za-z_]\w*)\s*=\s*"\*?(res://[^"]+)"')


def _clean_text(value, limit):
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "").strip()[:limit]


def _bool(value, default=False):
    return value if isinstance(value, bool) else default


def validate_request(action):
    """Return a small canonical request and human-readable schema errors."""
    if not isinstance(action, dict):
        return {}, ["gather_context action must be an object"]
    query = _clean_text(action.get("query"), 500)
    symbols = action.get("symbols") if isinstance(action.get("symbols"), list) else []
    symbols = [_clean_text(item, 160) for item in symbols[:MAX_SYMBOLS]]
    symbols = [item for item in symbols if item]
    classes = action.get("godot_api") if isinstance(action.get("godot_api"), list) else []
    classes = [_clean_text(item, 80) for item in classes[:MAX_API_CLASSES]]
    classes = [item for item in classes if _CLASS_RE.match(item)]
    try:
        max_chars = int(action.get("max_chars", DEFAULT_MAX_CHARS))
    except (TypeError, ValueError):
        max_chars = DEFAULT_MAX_CHARS
    max_chars = max(MIN_MAX_CHARS, min(max_chars, HARD_MAX_CHARS))
    spec = {
        "query": query,
        "symbols": symbols,
        "godot_api": classes,
        "editor": _bool(action.get("editor"), True),
        "active_scene": _bool(action.get("active_scene"), True),
        "dependencies": _bool(action.get("dependencies"), True),
        "diagnostics": _bool(action.get("diagnostics"), True),
        "project_settings": _bool(action.get("project_settings"), True),
        "max_chars": max_chars,
    }
    selectors = (query or symbols or classes or spec["editor"] or
                 spec["active_scene"] or spec["diagnostics"])
    return spec, ([] if selectors else ["gather_context has no context selectors"])


def _allowed_path(project_root, path, allow_addons=False):
    if not isinstance(path, str) or not path.startswith("res://"):
        return ""
    try:
        if not allow_addons and is_addon_path(path, project_root):
            return ""
        _resolve_safe_path(project_root, path)
    except Exception:
        return ""
    return path


def _read_script(project_root, path):
    try:
        text, _truncated = read_project_file(project_root, path, max_chars=160000)
        return text
    except Exception:
        return ""


def _candidate_scripts(project_root, function_name, allow_addons):
    rows, _truncated = search_project_text(
        project_root, "func " + function_name, max_results=30, context_lines=0,
        exclude_rel_prefixes=None if allow_addons else ("addons/",))
    paths = []
    for row in rows:
        path = row.get("path", "")
        if path.endswith(".gd") and path not in paths:
            text = _read_script(project_root, path)
            if function_name in gd_functions.list_functions(text):
                paths.append(path)
    return paths


def _resolve_symbol(project_root, request, allow_addons=False):
    class_name = ""
    if "::" in request:
        path, function_name = request.rsplit("::", 1)
        path = _allowed_path(project_root, path, allow_addons)
        candidates = [path] if path and path.endswith(".gd") else []
    else:
        if "." in request:
            class_name, function_name = request.rsplit(".", 1)
        else:
            function_name = request
        candidates = _candidate_scripts(project_root, function_name, allow_addons)
        if class_name:
            exact = []
            for path in candidates:
                match = _CLASS_NAME_RE.search(_read_script(project_root, path))
                if match and match.group(1) == class_name:
                    exact.append(path)
            candidates = exact
    candidates = [path for path in candidates if path]
    if len(candidates) != 1:
        return {"request": request, "status": "missing" if not candidates else "ambiguous",
                "candidates": candidates[:8]}
    path = candidates[0]
    found, _missing = gd_functions.extract_functions(
        _read_script(project_root, path), [function_name])
    if not found:
        return {"request": request, "status": "missing", "candidates": [path]}
    item = found[0]
    snippet = item["snippet"]
    if len(snippet) > 4000:
        snippet = snippet[:3950].rstrip() + "\n# [function truncated]"
    return {"request": request, "status": "found", "path": path,
            "name": item["name"], "start_line": item["start_line"],
            "end_line": item["end_line"], "snippet": snippet}


def _project_settings(project_root, query):
    try:
        text, _truncated = read_project_file(
            project_root, "res://project.godot", max_chars=120000)
    except Exception:
        return []
    autoloads = []
    in_autoload = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_autoload = stripped == "[autoload]"
            continue
        if in_autoload:
            match = _AUTOLOAD_RE.match(stripped)
            if match:
                autoloads.append("%s -> %s" % (match.group(1), match.group(2)))
    actions = log_reader.list_input_actions(project_root) or []
    terms = {part.lower() for part in re.findall(r"[A-Za-z0-9_]+", query or "")}
    if terms:
        relevant = [name for name in actions if name.lower() in terms]
        actions = relevant or actions
    lines = []
    if autoloads:
        lines.append("Autoloads: " + ", ".join(autoloads[:12]))
    if actions:
        lines.append("InputMap actions: " + ", ".join(actions[:20]))
    return lines


def _api_sections(project_root, classes, addon_dir):
    blocks = []
    for class_name in classes:
        try:
            chain = gd_api_cache.resolve_chain(
                project_root, class_name, addon_dir=addon_dir)
            methods, properties, signals = gd_api_cache.collect_members(
                project_root, class_name, addon_dir=addon_dir)
        except Exception:
            continue
        if not chain:
            blocks.append("%s: not found in the project's ClassDB cache" % class_name)
            continue
        method_rows = []
        for name in sorted(methods)[:20]:
            arity = methods[name]
            if isinstance(arity, (list, tuple)):
                arity_text = "..".join(str(x) for x in arity)
            else:
                arity_text = str(arity)
            method_rows.append("%s(%s)" % (name, arity_text))
        rows = ["%s inherits: %s" % (class_name, " -> ".join(chain))]
        if method_rows:
            rows.append("methods: " + ", ".join(method_rows))
        if properties:
            rows.append("properties: " + ", ".join(sorted(properties)[:20]))
        if signals:
            rows.append("signals: " + ", ".join(sorted(signals)[:20]))
        blocks.append("\n".join(rows))
    return blocks


def _diagnostics(project_root, paths, addon_dir, dirty_path):
    lines = []
    if dirty_path:
        lines.append("- %s: editor buffer is unsaved; diagnostics below use disk content" % dirty_path)
    for path in paths[:6]:
        text = _read_script(project_root, path) if path.endswith(".gd") else ""
        try:
            if path.endswith(".gd") and text:
                for problem in gd_lint.lint_gdscript(text)[:4]:
                    lines.append("- gd_lint %s: %s" % (path, problem))
                for problem in gd_api_check.check_api_usage(
                        project_root, text, path, addon_dir)[:4]:
                    lines.append("- gd_api_check %s: %s" % (path, problem))
            elif path.endswith(".tscn"):
                scene_text, _truncated = read_project_file(
                    project_root, path, max_chars=160000)
                _fixed, problems = tscn_lint.lint_and_fix_tscn(
                    scene_text, project_root, addon_dir)
                for problem in problems[:4]:
                    lines.append("- tscn_lint %s: %s" % (path, problem))
        except Exception as exc:
            lines.append("- diagnostic error %s: %s" % (path, exc))
        if len(lines) >= 12:
            break
    return lines[:12]


def _references(project_root, paths, allow_addons):
    if not paths:
        return []
    rows, truncated = search_project_text(
        project_root, "", needles=paths[:6], max_results=5, context_lines=0,
        exclude_rel_prefixes=None if allow_addons else ("addons/",))
    out = []
    source_set = set(paths)
    for row in rows:
        if row.get("path") in source_set:
            continue
        out.append("- %s:%s references %s: %s" % (
            row.get("path"), row.get("line"), row.get("needle"),
            str(row.get("snippet", "")).strip()))
        if len(out) >= 20:
            break
    if truncated:
        out.append("- reference results truncated")
    return out


def gather(project_root, action, editor_snapshot=None, addon_dir=None,
           allow_addons=False):
    """Collect structured sections without changing project files."""
    spec, errors = validate_request(action)
    result = {"schema_version": 1, "spec": spec, "sections": [],
              "sources": [], "omitted": [], "errors": errors}
    if errors:
        return result
    snapshot = editor_context.normalize_snapshot(editor_snapshot)
    source_paths = []
    if spec["editor"] and snapshot:
        block, _stats = editor_context.format_snapshot(snapshot, max_chars=4500)
        if block:
            result["sections"].append(("EDITOR SNAPSHOT", block))
        script_path = ((snapshot.get("script") or {}).get("path") or "")
        if _allowed_path(project_root, script_path, allow_addons):
            source_paths.append(script_path)

    for symbol in spec["symbols"]:
        item = _resolve_symbol(project_root, symbol, allow_addons)
        if item["status"] != "found":
            result["omitted"].append("%s: %s%s" % (
                symbol, item["status"],
                " (%s)" % ", ".join(item.get("candidates") or [])
                if item.get("candidates") else ""))
            continue
        path = item["path"]
        source_paths.append(path)
        body = ("Source: %s:%d-%d\n```gdscript\n%s\n```" %
                (path, item["start_line"], item["end_line"], item["snippet"]))
        result["sections"].append(("SYMBOL " + symbol, body))

    scene_path = ((snapshot.get("scene") or {}).get("active") or "")
    scene_path = _allowed_path(project_root, scene_path, allow_addons)
    if spec["active_scene"] and scene_path and scene_path.endswith(".tscn"):
        try:
            result["sections"].append((
                "ACTIVE SCENE " + scene_path,
                describe_scene(project_root, scene_path, max_chars=3500)))
            source_paths.append(scene_path)
        except Exception as exc:
            result["omitted"].append("%s: %s" % (scene_path, exc))

    query = spec["query"]
    if query:
        result["sections"].append((
            "PROJECT REFERENCE",
            librarian.answer(project_root, query, budget_chars=4000,
                             addon_dir=addon_dir)))
    source_paths = list(dict.fromkeys(source_paths))
    if spec["dependencies"]:
        dependency_paths = [path for path in source_paths if not path.endswith(".tscn")]
        refs = _references(project_root, dependency_paths, allow_addons)
        if refs:
            result["sections"].append(("DEPENDENCIES (textual references)", "\n".join(refs)))
    if spec["diagnostics"]:
        script = snapshot.get("script") or {}
        dirty_path = script.get("path") if script.get("dirty") is True else ""
        diagnostics = _diagnostics(project_root, source_paths, addon_dir, dirty_path)
        if diagnostics:
            result["sections"].append(("DIAGNOSTICS", "\n".join(diagnostics)))
    api_blocks = _api_sections(project_root, spec["godot_api"], addon_dir)
    if api_blocks:
        result["sections"].append(("GODOT API", "\n\n".join(api_blocks)))
    if spec["project_settings"]:
        settings = _project_settings(project_root, query)
        if settings:
            result["sections"].append(("PROJECT SETTINGS", "\n".join(settings)))
    result["sources"] = source_paths
    return result


def _fit_block(title, body, remaining):
    header = "\n## " + title + "\n"
    if len(header) + len(body) <= remaining:
        return header + body
    if remaining < len(header) + 120:
        return ""
    room = remaining - len(header) - len("\n[section truncated]")
    clipped = body[:room].rstrip()
    if "```" in clipped and clipped.count("```") % 2:
        fence = clipped.rfind("```")
        clipped = clipped[:fence].rstrip()
    return header + clipped + "\n[section truncated]"


def format_result(result, max_chars=None):
    """Format one bounded plain-text model message; JSON is reserved for actions."""
    spec = result.get("spec") or {}
    try:
        limit = int(max_chars if max_chars is not None else spec.get("max_chars"))
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_CHARS
    limit = max(MIN_MAX_CHARS, min(limit, HARD_MAX_CHARS))
    start = "[Gather context v1; read-only local project evidence]"
    end = "\n[/Gather context]"
    parts = [start]
    if result.get("errors"):
        parts.append("\nERRORS\n- " + "\n- ".join(result["errors"]))
    for title, body in result.get("sections") or []:
        remaining = limit - len("".join(parts)) - len(end)
        fitted = _fit_block(str(title), str(body), remaining)
        if fitted:
            parts.append(fitted)
    if result.get("sources"):
        body = "\n".join("- " + path for path in result["sources"])
        fitted = _fit_block("SOURCES", body, limit - len("".join(parts)) - len(end))
        if fitted:
            parts.append(fitted)
    if result.get("omitted"):
        body = "\n".join("- " + item for item in result["omitted"])
        fitted = _fit_block("OMITTED", body, limit - len("".join(parts)) - len(end))
        if fitted:
            parts.append(fitted)
    return "".join(parts) + end
