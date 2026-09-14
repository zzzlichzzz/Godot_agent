# -*- coding: utf-8 -*-
"""Validate staged project changes with Godot in isolated project copies.

The existing text linters remain the first barrier. This module adds an
independent engine barrier and never writes to the real project.
"""
import collections
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from project_tools import _resolve_safe_path


SCHEMA_VERSION = 1
DEFAULT_TIMEOUT = 35.0
MAX_OUTPUT_CHARS = 200000
RESOURCE_EXTENSIONS = (".gd", ".tscn", ".tres", ".res", ".gdshader", ".shader")
_COPY_EXCLUDED = {".git", ".agent_history", "__pycache__", "build", "dist"}
_DIAGNOSTIC_RE = re.compile(
    r"(?P<severity>SCRIPT ERROR|ERROR|WARNING):\s*(?P<message>.*?)(?:\s+at:\s*)?"
    r"(?P<path>res://[^:\r\n]+)?(?::(?P<line>\d+))?(?::(?P<column>\d+))?\s*$",
    re.IGNORECASE,
)


class HeadlessValidationError(RuntimeError):
    pass


class StaleValidationError(HeadlessValidationError):
    pass


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _file_hash(path):
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return _sha256(handle.read())


def _canonical_rel(path):
    value = str(path or "").replace("\\", "/")
    if not value.startswith("res://"):
        raise HeadlessValidationError("Путь кандидата должен начинаться с res://: %s" % value)
    rel = value[6:].strip("/")
    if not rel or any(part in ("", ".", "..") for part in rel.split("/")):
        raise HeadlessValidationError("Некорректный путь кандидата: %s" % value)
    return "res://" + rel


def _action_candidate(project_root, action):
    kind = str(action.get("action") or "")
    path = _canonical_rel(action.get("path"))
    absolute = _resolve_safe_path(project_root, path)
    operations = []
    targets = []
    source_hashes = {path: _file_hash(absolute)}
    if kind == "create_file":
        operations.append({"op": "write", "path": path,
                           "content": str(action.get("content") or "").encode("utf-8")})
        target_path = path
    elif kind == "patch_file":
        if not os.path.isfile(absolute):
            raise HeadlessValidationError("Файл для patch_file не найден: %s" % path)
        with open(absolute, "r", encoding="utf-8-sig", errors="strict") as handle:
            before = handle.read().replace("\r\n", "\n")
        search = str(action.get("search") or "").replace("\r\n", "\n")
        if not search or before.count(search) != 1:
            raise HeadlessValidationError("patch_file не имеет одного точного совпадения: %s" % path)
        after = before.replace(search, str(action.get("replace") or "").replace("\r\n", "\n"), 1)
        operations.append({"op": "write", "path": path, "content": after.encode("utf-8")})
        target_path = path
    elif kind == "move_file":
        dest = _canonical_rel(action.get("dest"))
        dest_absolute = _resolve_safe_path(project_root, dest)
        if not os.path.isfile(absolute):
            raise HeadlessValidationError("Исходный файл для move_file не найден: %s" % path)
        source_hashes[dest] = _file_hash(dest_absolute)
        operations.append({"op": "move", "path": path, "dest": dest})
        target_path = dest
    else:
        raise HeadlessValidationError("Неподдерживаемый кандидат: %s" % kind)
    if target_path.lower().endswith(RESOURCE_EXTENSIONS):
        targets.append(target_path)
    targets.extend(_referencer_targets(project_root, [path], excluded=[path, target_path]))
    return make_batch(kind, operations, targets, source_hashes)


def batch_from_action(project_root, action):
    return _action_candidate(project_root, action)


def batch_from_rename(project_root, prepared):
    operations, targets, hashes = [], [], {}
    for item in prepared.get("files") or []:
        path = _canonical_rel(item.get("path"))
        operations.append({"op": "write", "path": path, "content": item["after_bytes"]})
        hashes[path] = item.get("before_hash")
        if path.lower().endswith(RESOURCE_EXTENSIONS):
            targets.append(path)
    if not operations:
        raise HeadlessValidationError("Пустой кандидат переименования")
    targets.extend(_referencer_targets(project_root, hashes.keys(), excluded=hashes.keys()))
    return make_batch("rename_symbol", operations, targets, hashes)


def _referencer_targets(project_root, changed_paths, excluded=()):
    needles = [path.encode("utf-8") for path in changed_paths]
    excluded = set(excluded)
    targets = []
    if not needles:
        return targets
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [name for name in dirs if name not in _COPY_EXCLUDED]
        for name in files:
            absolute = os.path.join(root, name)
            rel = "res://" + os.path.relpath(absolute, project_root).replace(os.sep, "/")
            if rel in excluded or not rel.lower().endswith(RESOURCE_EXTENSIONS):
                continue
            try:
                with open(absolute, "rb") as handle:
                    content = handle.read()
            except OSError:
                continue
            if any(needle in content for needle in needles):
                targets.append(rel)
    return targets


def make_batch(action_kind, operations, targets, source_hashes, required_targets=()):
    serial = []
    for operation in operations:
        row = {key: value for key, value in operation.items() if key != "content"}
        if "content" in operation:
            row["content_sha256"] = _sha256(operation["content"])
        serial.append(row)
    digest = _sha256(json.dumps({"kind": action_kind, "operations": serial,
                                 "targets": sorted(set(targets)),
                                 "required_targets": sorted(set(required_targets))},
                                sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return {"schema_version": SCHEMA_VERSION, "action_kind": action_kind,
            "operations": operations, "targets": sorted(set(targets)),
            "required_targets": sorted(set(required_targets)),
            "source_hashes": dict(source_hashes), "candidate_digest": digest}


def discover_executable(explicit=None):
    candidates = [explicit, os.environ.get("GODOT_AGENT_GODOT_EXECUTABLE"),
                  os.environ.get("GODOT4"), os.environ.get("GODOT")]
    for name in ("godot4", "godot"):
        candidates.append(shutil.which(name))
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.abspath(candidate)):
            return os.path.abspath(candidate)
    return None


def _copy_project(source, destination):
    source_real = os.path.realpath(source)

    def ignored(current, names):
        skipped = []
        for name in names:
            if name in _COPY_EXCLUDED or name.startswith(".godot_agent_validation"):
                skipped.append(name)
        return skipped

    shutil.copytree(source_real, destination, ignore=ignored)


def _overlay_path(root, res_path):
    rel = _canonical_rel(res_path)[6:].replace("/", os.sep)
    absolute = os.path.realpath(os.path.join(root, rel))
    root_real = os.path.realpath(root)
    if os.path.commonpath([root_real, absolute]) != root_real:
        raise HeadlessValidationError("Путь вышел за overlay: %s" % res_path)
    return absolute


def _apply_operations(root, operations):
    for operation in operations:
        op = operation["op"]
        source = _overlay_path(root, operation["path"])
        if op == "write":
            os.makedirs(os.path.dirname(source), exist_ok=True)
            with open(source, "wb") as handle:
                handle.write(operation["content"])
        elif op == "move":
            dest = _overlay_path(root, operation["dest"])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.exists(dest):
                raise HeadlessValidationError("Назначение move уже существует: %s" % operation["dest"])
            os.replace(source, dest)
            if os.path.isfile(source + ".uid"):
                os.replace(source + ".uid", dest + ".uid")
        elif op == "delete":
            if os.path.exists(source):
                os.remove(source)
        else:
            raise HeadlessValidationError("Неизвестная overlay-операция: %s" % op)


def _harness_source(harness_path=None):
    candidates = [harness_path] if harness_path else []
    candidates.append(os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "agent_headless_validator.gd")))
    if getattr(sys, "_MEIPASS", None):
        candidates.append(os.path.join(sys._MEIPASS, "agent_headless_validator.gd"))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise HeadlessValidationError("Не найден headless harness")


def _write_manifest(root, targets, harness_path=None):
    service = os.path.join(root, ".godot_agent_validation")
    os.makedirs(service, exist_ok=True)
    shutil.copy2(_harness_source(harness_path), os.path.join(service, "validator.gd"))
    manifest = {"schema_version": 1, "targets": list(targets),
                "result_path": "res://.godot_agent_validation/result.json"}
    with open(os.path.join(service, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, sort_keys=True)


def _sandbox_env(base):
    env = dict(os.environ)
    home = os.path.join(base, "home")
    os.makedirs(home, exist_ok=True)
    env.update({"HOME": home, "APPDATA": os.path.join(home, "appdata"),
                "LOCALAPPDATA": os.path.join(home, "localappdata"),
                "XDG_DATA_HOME": os.path.join(home, "data"),
                "XDG_CONFIG_HOME": os.path.join(home, "config")})
    return env


def _normalize_message(message):
    value = re.sub(r"[A-Za-z]:[\\/][^\r\n]+", "<temp>", str(message or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _diag(severity, category, message, path="", line=0, column=0):
    row = {"source": "godot", "severity": severity, "category": category,
           "message": _normalize_message(message), "path": path if str(path).startswith("res://") else "",
           "line": int(line or 0), "column": int(column or 0)}
    row["id"] = _sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8"))[:16]
    return row


def _parse_output(text):
    diagnostics = []
    for line in str(text or "").splitlines():
        match = _DIAGNOSTIC_RE.search(line.strip())
        if not match:
            continue
        severity = "warning" if match.group("severity").upper() == "WARNING" else "error"
        diagnostics.append(_diag(severity, "engine", match.group("message"),
                                 match.group("path") or "", match.group("line"), match.group("column")))
    return diagnostics


def _diagnostic_key(item):
    return (item.get("severity"), item.get("category"), item.get("path"), item.get("line", 0),
            item.get("column", 0), _normalize_message(item.get("message")))


def _subtract_baseline(baseline, candidate):
    remaining = collections.Counter(_diagnostic_key(item) for item in baseline)
    new_items, old_items = [], []
    for item in candidate:
        key = _diagnostic_key(item)
        if remaining[key] > 0:
            remaining[key] -= 1
            old_items.append(dict(item, pre_existing=True))
        else:
            new_items.append(dict(item, pre_existing=False))
    return new_items, old_items


def validate_batch(project_root, batch, executable=None, mode=None, timeout=DEFAULT_TIMEOUT,
                   command_prefix=None, harness_path=None, temp_root=None):
    mode = str(mode or os.environ.get("GODOT_AGENT_HEADLESS_VALIDATION", "auto")).lower()
    if mode not in ("off", "auto", "required"):
        mode = "auto"
    # Explicit checks assert validity, not just absence of regressions. They
    # cannot succeed when the engine is missing or when baseline has errors.
    if batch.get("required_targets"):
        mode = "required"
    if mode == "off" or not batch.get("targets"):
        return _receipt(batch, {"status": "skipped", "mode": mode, "new_diagnostics": [],
                                "pre_existing_diagnostics": []})
    found = discover_executable(executable)
    command = list(command_prefix or ([found] if found else []))
    if not command:
        report = {"status": "unavailable", "mode": mode, "new_diagnostics": [],
                  "pre_existing_diagnostics": [], "blocking": mode == "required"}
        return _receipt(batch, report)
    batch = dict(batch, source_hashes=dict(batch["source_hashes"]))
    for path in batch["targets"]:
        batch["source_hashes"].setdefault(path, _file_hash(_resolve_safe_path(project_root, path)))
    owner = tempfile.mkdtemp(prefix="godot_agent_validation_", dir=temp_root)
    baseline = os.path.join(owner, "baseline")
    candidate = os.path.join(owner, "candidate")
    try:
        with open(os.path.join(owner, ".owner"), "w", encoding="ascii") as handle:
            handle.write(str(uuid.uuid4()))
        _copy_project(project_root, baseline)
        for path, expected in batch["source_hashes"].items():
            if _file_hash(_overlay_path(baseline, path)) != expected:
                raise StaleValidationError("Файл изменился при подготовке проверки Godot: %s" % path)
        shutil.copytree(baseline, candidate)
        _apply_operations(candidate, batch["operations"])
        for root in (baseline, candidate):
            _write_manifest(root, batch["targets"], harness_path)
        baseline_run = _run_process(baseline, command, timeout)
        candidate_run = _run_process(candidate, command, timeout)
        new_items, old_items = _subtract_baseline(baseline_run["diagnostics"], candidate_run["diagnostics"])
        required = set(batch.get("required_targets") or [])
        check_errors = [item for item in candidate_run["diagnostics"]
                        if required and item["severity"] == "error"]
        infrastructure_bad = candidate_run["status"] in ("timeout", "crashed")
        baseline_bad = baseline_run["status"] in ("timeout", "crashed")
        blocking = (infrastructure_bad or baseline_bad or bool(check_errors) or
                    any(item["severity"] == "error" for item in new_items))
        status = "inconclusive" if baseline_bad else ("failed" if blocking else "passed")
        report = {"status": status, "mode": mode, "blocking": blocking,
                  "baseline_status": baseline_run["status"], "candidate_status": candidate_run["status"],
                  "new_diagnostics": new_items, "pre_existing_diagnostics": old_items,
                  "check_diagnostics": check_errors,
                  "duration_ms": baseline_run["duration_ms"] + candidate_run["duration_ms"],
                  "timed_out": baseline_run.get("timed_out") or candidate_run.get("timed_out"),
                  "output_truncated": baseline_run.get("output_truncated") or candidate_run.get("output_truncated")}
        return _receipt(batch, report)
    finally:
        shutil.rmtree(owner, ignore_errors=True)


def _run_process(root, command, timeout):
    """Run a prepared overlay without touching its manifest."""
    log_path = os.path.join(root, ".godot_agent_validation", "godot.log")
    argv = list(command) + ["--headless", "--path", root, "--language", "en", "--log-file", log_path,
                            "--script", "res://.godot_agent_validation/validator.gd"]
    started = time.monotonic()
    proc = None
    output_path = os.path.join(root, ".godot_agent_validation", "process-output.log")
    try:
        with open(output_path, "wb") as output_handle:
            proc = subprocess.Popen(argv, cwd=root, env=_sandbox_env(root), stdout=output_handle,
                                    stderr=subprocess.STDOUT, shell=False,
                                    start_new_session=(os.name != "nt"))
            try:
                proc.wait(timeout=timeout)
                timed_out, code = False, proc.returncode
            except subprocess.TimeoutExpired:
                timed_out, code = True, None
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    try:
                        os.killpg(proc.pid, 9)
                    except OSError:
                        proc.kill()
                proc.wait(timeout=5)
    except OSError as exc:
        return {"status": "crashed", "diagnostics": [_diag("error", "process", str(exc))],
                "duration_ms": 0, "timed_out": False, "output_truncated": False}
    output_bytes, output_truncated = _read_tail(output_path, MAX_OUTPUT_CHARS)
    log_bytes, log_truncated = _read_tail(log_path, MAX_OUTPUT_CHARS)
    decoded = (output_bytes + b"\n" + log_bytes)[-MAX_OUTPUT_CHARS:].decode("utf-8", "replace")
    truncated = output_truncated or log_truncated or len(output_bytes) + len(log_bytes) > MAX_OUTPUT_CHARS
    diagnostics = _parse_output(decoded)
    result_path = os.path.join(root, ".godot_agent_validation", "result.json")
    harness_failed = False
    try:
        with open(result_path, "r", encoding="utf-8") as handle:
            result = json.load(handle)
        diagnostics.extend(_diag(item.get("severity", "error"), item.get("category", "load"),
                                 item.get("message", "Ошибка загрузки ресурса"), item.get("path", ""))
                           for item in (result.get("diagnostics") or []))
    except Exception:
        harness_failed = True
        if not timed_out:
            diagnostics.append(_diag("error", "harness", "Godot не вернул структурированный результат"))
    status = "timeout" if timed_out else ("crashed" if harness_failed or truncated else
                                         "failed" if any(d["severity"] == "error" for d in diagnostics)
                                           else ("passed" if code == 0 else "crashed"))
    return {"status": status, "diagnostics": diagnostics, "duration_ms": int((time.monotonic()-started)*1000),
            "timed_out": timed_out, "output_truncated": truncated, "exit_code": code}


def _read_tail(path, limit):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if size > limit:
                handle.seek(-limit, os.SEEK_END)
            return handle.read(limit), size > limit
    except OSError:
        return b"", False


def _receipt(batch, report):
    return {"schema_version": SCHEMA_VERSION, "candidate_digest": batch["candidate_digest"],
            "source_hashes": dict(batch["source_hashes"]), "report": report}


def verify_receipt(project_root, batch, receipt):
    if not isinstance(receipt, dict) or receipt.get("candidate_digest") != batch.get("candidate_digest"):
        raise StaleValidationError("Кандидат не совпадает с проверенным Godot вариантом")
    for path, expected in (receipt.get("source_hashes") or {}).items():
        actual = _file_hash(_resolve_safe_path(project_root, path))
        if actual != expected:
            raise StaleValidationError("Файл изменился после проверки Godot: %s" % path)
    if (receipt.get("report") or {}).get("blocking"):
        raise HeadlessValidationError("Проверка Godot заблокировала кандидат")
    return True


def blocking_message(receipt):
    report = receipt.get("report") or {}
    if not report.get("blocking"):
        return None
    if report.get("status") == "unavailable":
        return "[Система]: обязательная проверка настоящим Godot недоступна: executable не найден."
    diagnostics = report.get("check_diagnostics") or report.get("new_diagnostics") or []
    if diagnostics:
        lines = ["- %s%s: %s" % (item.get("path") or "Godot",
                                  (":%s" % item.get("line")) if item.get("line") else "",
                                  item.get("message")) for item in diagnostics[:8]]
        return ("[Система]: кандидат не прошёл изолированную проверку настоящим Godot. "
                "Движок нашёл ошибки кандидата или явно запрошенной проверки:\n" + "\n".join(lines) +
                "\nИсправь действие и пришли agent_action заново.")
    return "[Система]: изолированная проверка Godot завершилась сбоем или таймаутом; действие не применено."
