# -*- coding: utf-8 -*-
"""Deterministic project-aware judge for parallel model answers.

The judge never writes to disk. It parses agent_action, applies write actions
to an in-memory overlay, reuses the Librarian project index and existing Godot
linters, and returns explainable findings suitable for response selection.
"""
import os

from gd_api_check import check_api_usage
from gd_lint import lint_gdscript
from minilich.ml_project_index import search as librarian_search
from parser_base import (answer_transfer_incomplete, parse_action_json,
                         score_answer_variant, split_net_text_and_action)
from project_tools import (_resolve_safe_path, can_read_project_path,
                           can_write_project_path)
from tscn_lint import is_scene_path, lint_and_fix_tscn
import symbol_refactor
import high_level_actions
import runtime_debug
import runtime_checks


READ_ACTIONS = {
    "ask_librarian", "read_file", "read_function", "search_project",
    "list_files", "list_scene", "gather_context", "inspect_runtime",
}
WRITE_ACTIONS = {"create_file", "patch_file", "move_file"}


def _finding(severity, category, message, path=None, step=None):
    out = {"severity": severity, "category": category, "message": message}
    if path:
        out["path"] = path
    if step is not None:
        out["step"] = step
    return out


def _judge_structural_action(project_root, action, addon_dir,
                            allow_addons=False, allow_self_edit=False):
    act = action.get("action")
    try:
        if act == "rename_symbol":
            prepared = symbol_refactor.prepare_rename(
                project_root, action, allow_addons=allow_addons,
                addon_dir=addon_dir, allow_self_edit=allow_self_edit)
            return 94, [], ["Safe rename resolves %d references in %d files" % (
                prepared["reference_count"], len(prepared["files"]))]
        if act in ("edit_scene", "create_scene"):
            import scene_actions
            normalized, _absolute = scene_actions.normalize_action(
                project_root, action, allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir)
            return 93, [], ["Structural scene action validates %d operations" %
                            len(normalized["operations"])]
        if act == "edit_project_settings":
            import project_settings_actions
            normalized, _absolute = project_settings_actions.normalize_action(
                project_root, action, allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir)
            return 93, [], ["ProjectSettings edit validates %d operations" %
                            len(normalized["operations"])]
        if act == "edit_resource":
            import resource_actions
            normalized, _absolute = resource_actions.normalize_action(
                project_root, action, allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir)
            return 93, [], ["Structural resource edit validates %d operations" %
                            len(normalized["operations"])]
        if act == "transaction":
            import transaction_actions
            prepared = transaction_actions.prepare(
                project_root, action, allow_addons=allow_addons,
                addon_dir=addon_dir, allow_self_edit=allow_self_edit)
            if prepared.get("already_satisfied"):
                return 96, [], ["Atomic transaction is already satisfied locally"]
            return 95, [], ["Atomic transaction validates %d operations in %d files" % (
                len(prepared["action"]["operations"]), len(prepared["files"]))]
    except Exception as exc:
        categories = {"rename_symbol": "refactor", "edit_scene": "scene", "create_scene": "scene",
                      "edit_project_settings": "project_settings",
                      "edit_resource": "resource",
                      "transaction": "transaction"}
        return 45, [_finding("blocking", categories.get(act, "schema"), str(exc))], []
    return 45, [_finding("blocking", "schema", "unsupported compiled action: %s" % act)], []


def _read_text(project_root, path, overlay):
    if path in overlay:
        return overlay[path]
    abs_path = _resolve_safe_path(project_root, path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(path)
    with open(abs_path, "r", encoding="utf-8-sig", errors="replace") as handle:
        return handle.read().replace("\r\n", "\n").replace("\r", "\n")


def _path_exists(project_root, path, overlay):
    if path in overlay:
        return overlay[path] is not None
    try:
        return os.path.exists(_resolve_safe_path(project_root, path))
    except Exception:
        return False


def _validate_candidate(project_root, path, text, addon_dir, planned_paths):
    findings = []
    if path.endswith(".gd"):
        for problem in lint_gdscript(text):
            findings.append(_finding("blocking", "gdscript", problem, path))
        for problem in check_api_usage(project_root, text, path, addon_dir):
            findings.append(_finding("blocking", "godot_api", problem, path))
    elif is_scene_path(path):
        _fixed, problems = lint_and_fix_tscn(
            text, project_root, addon_dir, planned_paths=planned_paths)
        for problem in problems:
            findings.append(_finding("blocking", "scene", problem, path))
    return findings


def _judge_read_action(project_root, action, addon_dir=None,
                       allow_addons=False, allow_self_edit=False):
    findings = []
    evidence = []
    act = action.get("action")
    score = 55
    if act == "run_check":
        try:
            normalized = runtime_checks.normalize_action(
                project_root, action, allow_addons=allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir)
        except runtime_checks.RuntimeCheckError as exc:
            return 45, [_finding("blocking", "runtime_check", str(exc))], evidence
        return 94, [], ["One deterministic local game check validates %d bounded steps" %
                        len(normalized["steps"])]
    if act == "inspect_runtime":
        try:
            normalized = runtime_debug.normalize_action(action)
        except runtime_debug.RuntimeDebugError as exc:
            return 45, [_finding("blocking", "runtime", str(exc))], evidence
        property_count = sum(len(item["names"]) for item in normalized["properties"])
        return 93, [], ["One bounded read-only runtime snapshot validates %d sections and %d properties" % (
            len(normalized["sections"]), property_count)]
    if act == "ask_librarian":
        score = 75
        query = action.get("query")
        if not isinstance(query, str) or not query.strip():
            findings.append(_finding("blocking", "schema",
                                     "ask_librarian requires a non-empty query"))
            return score, findings, evidence
        try:
            hits = librarian_search(project_root, query.strip(), limit=8)
        except Exception:
            hits = []
        if hits:
            score += 20
            evidence.append("Librarian found %d relevant project entries" % len(hits))
        else:
            findings.append(_finding("warning", "librarian",
                                     "Librarian query has no project hits"))
        # Automatic and broad orientation is valuable when paths are unknown,
        # but a confirmed exact file is slightly more informative.
        score += 2
        return score, findings, evidence

    if act == "gather_context":
        query = action.get("query")
        symbols = action.get("symbols")
        classes = action.get("godot_api")
        if query is not None and (not isinstance(query, str) or len(query) > 500):
            findings.append(_finding("blocking", "schema", "gather_context query must be text up to 500 characters"))
        if symbols is not None and (not isinstance(symbols, list) or len(symbols) > 8
                                    or not all(isinstance(x, str) for x in symbols)):
            findings.append(_finding("blocking", "schema", "gather_context symbols must contain at most 8 strings"))
        if classes is not None and (not isinstance(classes, list) or len(classes) > 4
                                    or not all(isinstance(x, str) for x in classes)):
            findings.append(_finding("blocking", "schema", "gather_context godot_api must contain at most 4 class names"))
        try:
            max_chars = int(action.get("max_chars", 12000))
            if max_chars < 2000 or max_chars > 20000:
                findings.append(_finding("blocking", "schema", "gather_context max_chars must be 2000..20000"))
        except (TypeError, ValueError):
            findings.append(_finding("blocking", "schema", "gather_context max_chars must be an integer"))
        if not findings:
            score = 90
            evidence.append("One bounded read-only pass replaces multiple context actions")
        return score, findings, evidence

    if act in ("read_file", "read_function"):
        paths = action.get("paths") or ([action.get("path")] if action.get("path") else [])
        if not paths:
            findings.append(_finding("blocking", "schema", "%s has no path" % act))
            return score, findings, evidence
        existing = 0
        for path in paths:
            if not isinstance(path, str) or not path.startswith("res://"):
                findings.append(_finding("blocking", "path", "invalid project path", path))
            elif not can_read_project_path(
                    path, project_root, allow_addons=allow_addons,
                    allow_self_edit=allow_self_edit, addon_dir=addon_dir):
                findings.append(_finding("blocking", "policy", "path is blocked by access policy", path))
            elif _path_exists(project_root, path, {}):
                existing += 1
                evidence.append("Exact project file exists: %s" % path)
            else:
                findings.append(_finding("blocking", "path",
                                         "requested file does not exist", path))
        if existing == len(paths):
            score += 24  # exact evidence wins over a broad librarian query
        if act == "read_function" and not isinstance(action.get("names", []), list):
            findings.append(_finding("warning", "schema", "read_function names should be a list"))
        return score, findings, evidence

    if act == "list_scene":
        path = action.get("path")
        if path and can_read_project_path(
                path, project_root, allow_addons=allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir) \
                and _path_exists(project_root, path, {}) and is_scene_path(path):
            score += 22
            evidence.append("Scene exists: %s" % path)
        else:
            findings.append(_finding("blocking", "path", "scene does not exist", path))
        return score, findings, evidence

    if act == "list_files":
        path = action.get("dir") or "res://"
        if _path_exists(project_root, path, {}):
            score += 12
        else:
            findings.append(_finding("blocking", "path", "directory does not exist", path))
        return score, findings, evidence

    if act == "search_project":
        query = action.get("query")
        if isinstance(query, str) and query.strip():
            score += 10
        else:
            findings.append(_finding("blocking", "schema", "search_project has no query"))
        return score, findings, evidence
    return score, findings, evidence


def _apply_write_action(project_root, action, overlay, addon_dir,
                        planned_paths, step=None, allow_addons=False,
                        allow_self_edit=False):
    findings = []
    evidence = []
    act = action.get("action")
    path = action.get("path")
    if not isinstance(path, str) or not path.startswith("res://"):
        return [_finding("blocking", "path", "invalid project path", path, step)], evidence
    try:
        _resolve_safe_path(project_root, path)
    except Exception as exc:
        return [_finding("blocking", "path", str(exc), path, step)], evidence
    if not can_write_project_path(
            path, project_root, allow_addons=allow_addons,
            allow_self_edit=allow_self_edit, addon_dir=addon_dir):
        return [_finding("blocking", "policy", "path is blocked by access policy", path, step)], evidence

    if act == "create_file":
        if path.lower().endswith(".tscn"):
            return [_finding("blocking", "scene", "new .tscn must use create_scene", path, step)], evidence
        content = action.get("content")
        if not isinstance(content, str):
            findings.append(_finding("blocking", "schema",
                                     "create_file has no text content", path, step))
            return findings, evidence
        overlay[path] = content.replace("\r\n", "\n")
        evidence.append("Virtual create succeeds: %s" % path)
    elif act == "patch_file":
        if path.lower().endswith(".tscn"):
            return [_finding("blocking", "scene", "existing .tscn must use edit_scene", path, step)], evidence
        search = action.get("search")
        replace = action.get("replace")
        if not search or not isinstance(replace, str):
            findings.append(_finding("blocking", "schema",
                                     "patch_file requires search and replace", path, step))
            return findings, evidence
        search = search.replace("\r\n", "\n").replace("\r", "\n")
        replace = replace.replace("\r\n", "\n").replace("\r", "\n")
        try:
            original = _read_text(project_root, path, overlay)
        except Exception:
            findings.append(_finding("blocking", "path",
                                     "patch target does not exist", path, step))
            return findings, evidence
        count = original.count(search)
        if count != 1:
            findings.append(_finding("blocking", "patch",
                                     "patch search occurs %d times, expected exactly 1" % count,
                                     path, step))
            return findings, evidence
        overlay[path] = original.replace(search, replace, 1)
        evidence.append("Virtual patch applies uniquely: %s" % path)
    elif act == "move_file":
        dest = action.get("dest")
        if not isinstance(dest, str) or not dest.startswith("res://"):
            findings.append(_finding("blocking", "schema",
                                     "move_file has invalid destination", path, step))
            return findings, evidence
        if not can_write_project_path(
                dest, project_root, allow_addons=allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir):
            return [_finding("blocking", "policy", "destination is blocked by access policy", dest, step)], evidence
        if path.lower().endswith(".tscn") or dest.lower().endswith(".tscn"):
            return [_finding("blocking", "scene", ".tscn paths must use create_scene/edit_scene", path, step)], evidence
        try:
            content = _read_text(project_root, path, overlay)
        except Exception:
            findings.append(_finding("blocking", "path",
                                     "move source does not exist", path, step))
            return findings, evidence
        if _path_exists(project_root, dest, overlay):
            findings.append(_finding("blocking", "path",
                                     "move destination already exists", dest, step))
            return findings, evidence
        overlay[path] = None
        overlay[dest] = content
        evidence.append("Virtual move succeeds: %s -> %s" % (path, dest))
        path = dest

    candidate = overlay.get(path)
    if isinstance(candidate, str):
        for finding in _validate_candidate(project_root, path, candidate,
                                           addon_dir, planned_paths):
            finding["step"] = step
            findings.append(finding)
    return findings, evidence


def judge_answer(project_root, full_text, addon_dir=None,
                 allow_addons=False, allow_self_edit=False):
    """Return an explainable deterministic judgment for one model answer."""
    structural = score_answer_variant(full_text)
    prose, action_raw = split_net_text_and_action(full_text or "")
    findings = []
    evidence = []
    action = None
    vote_eligible = False
    if not action_raw:
        findings.append(_finding("warning", "protocol", "answer has no agent_action"))
        # A clarifying/explanatory response ending in DONE is a valid agent
        # response. It ranks below a proven project action, but must not trigger
        # Skip merely because no file operation is appropriate yet.
        score = 68 + (7 if prose.strip() else 0)
        if "===DONE===" not in (full_text or ""):
            findings.append(_finding("blocking", "protocol",
                                     "plain answer is missing ===DONE==="))
            vote_eligible = True
    else:
        # An attempted agent action is objectively checkable: schema,
        # paths, syntax and project evidence can support an Arena vote.
        vote_eligible = True
        if answer_transfer_incomplete(action_raw, full_text or ""):
            findings.append(_finding("blocking", "protocol", "action transfer is incomplete"))
        action, error = parse_action_json(action_raw)
        if error or not isinstance(action, dict):
            findings.append(_finding("blocking", "protocol",
                                     "agent_action cannot be parsed: %s" % error))
            score = 10
        else:
            act = action.get("action")
            score = 58
            if act in READ_ACTIONS or act == "run_check":
                action_score, action_findings, action_evidence = _judge_read_action(
                    project_root, action, addon_dir=addon_dir,
                    allow_addons=allow_addons, allow_self_edit=allow_self_edit)
                score = action_score
                findings.extend(action_findings)
                evidence.extend(action_evidence)
            elif act in WRITE_ACTIONS or act == "plan":
                overlay = {}
                steps = action.get("steps") if act == "plan" else [action]
                if not isinstance(steps, list) or not steps:
                    findings.append(_finding("blocking", "schema", "plan has no steps"))
                else:
                    planned_paths = {
                        step.get("path") for step in steps
                        if isinstance(step, dict) and step.get("action") == "create_file"
                    }
                    for index, step_action in enumerate(steps, 1):
                        if not isinstance(step_action, dict):
                            findings.append(_finding("blocking", "schema",
                                                     "plan step is not an object", step=index))
                            continue
                        if step_action.get("action") not in WRITE_ACTIONS:
                            findings.append(_finding("blocking", "schema",
                                                     "unsupported plan action: %s"
                                                     % step_action.get("action"), step=index))
                            continue
                        fs, ev = _apply_write_action(
                            project_root, step_action, overlay, addon_dir,
                            planned_paths, step=index,
                            allow_addons=allow_addons,
                            allow_self_edit=allow_self_edit)
                        findings.extend(fs)
                        evidence.extend(ev)
                    score = 88 - min(20, max(0, len(steps) - 1) * 2)
            elif act in ("rename_symbol", "edit_scene", "create_scene", "edit_project_settings", "edit_resource", "transaction"):
                score, action_findings, action_evidence = _judge_structural_action(
                    project_root, action, addon_dir,
                    allow_addons=allow_addons, allow_self_edit=allow_self_edit)
                findings.extend(action_findings)
                evidence.extend(action_evidence)
            elif act == "project_command":
                try:
                    compiled = high_level_actions.compile_action(
                        project_root, action, allow_addons=allow_addons,
                        allow_self_edit=allow_self_edit, addon_dir=addon_dir)
                except Exception as exc:
                    score = 45
                    findings.append(_finding("blocking", "project_command", str(exc)))
                else:
                    score, action_findings, action_evidence = _judge_structural_action(
                        project_root, compiled, addon_dir,
                        allow_addons=allow_addons, allow_self_edit=allow_self_edit)
                    findings.extend(action_findings)
                    evidence.append("High-level %s deterministically compiles to %s" % (
                        action["command"]["type"], compiled["action"]))
                    evidence.extend(action_evidence)
            else:
                findings.append(_finding("blocking", "schema",
                                         "unknown action: %s" % act))

    blocking = [finding for finding in findings
                if finding.get("severity") == "blocking"]
    warnings = [finding for finding in findings
                if finding.get("severity") == "warning"]
    score -= len(blocking) * 35 + len(warnings) * 3
    score += structural[2] * 3 + structural[4] * 2
    score = max(0, min(100, int(score)))
    return {
        "score": score,
        "acceptable": not blocking and score >= 70,
        "vote_eligible": vote_eligible,
        "blocking": blocking,
        "warnings": warnings,
        "evidence": evidence[:12],
        "action": action,
        "structural_score": structural,
    }


def select_best_project_answer(project_root, variants, addon_dir=None,
                               allow_addons=False, allow_self_edit=False):
    """Return (key, text, judgment, all_judgments), preserving order on ties."""
    judged = []
    best = None
    for key, text in variants:
        result = judge_answer(
            project_root, text, addon_dir=addon_dir,
            allow_addons=allow_addons, allow_self_edit=allow_self_edit)
        judged.append((key, result))
        candidate = (key, text, result)
        if best is None or result["score"] > best[2]["score"]:
            best = candidate
    return best[0], best[1], best[2], judged
