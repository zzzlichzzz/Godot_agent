# -*- coding: utf-8 -*-
"""Prepare and atomically apply deterministic multi-file transactions."""
import hashlib
import os
import tempfile
import threading
import uuid

import gd_api_check
import gd_lint
import godot_headless_validation
import history_manager
from project_tools import (_resolve_safe_path, build_diff_preview,
                           can_write_project_path, sanitize_llm_text)


MAX_OPERATIONS = 30
MAX_CHECKS = 32
_ALLOWED = {"create_file", "patch_file", "move_file"}
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_replace_file = os.replace


class TransactionError(RuntimeError):
    pass


class StaleTransactionError(TransactionError):
    pass


def _lock(project_root):
    key = os.path.normcase(os.path.realpath(project_root))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _hash(data):
    # Validation receipts protect the exact candidate bytes. History may ignore
    # newline-only changes independently when deciding whether rollback is safe.
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _text_equivalent(left, right):
    if left is None or right is None:
        return left is right
    try:
        left_text = left.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        right_text = right.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        return left == right
    return left_text == right_text


def _read(path):
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return handle.read()


def _canonical(project_root, value, allow_addons,
               allow_self_edit=False, addon_dir=None):
    path = str(value or "").replace("\\", "/")
    if not path.startswith("res://") or path.lower() in ("res://", "res://project.godot"):
        raise TransactionError("Некорректный или запрещённый путь: %s" % path)
    rel = path[6:].strip("/")
    if not rel or any(part in ("", ".", "..") for part in rel.split("/")):
        raise TransactionError("Некорректный путь: %s" % path)
    if not can_write_project_path(
            path, project_root, allow_addons=allow_addons,
            allow_self_edit=allow_self_edit, addon_dir=addon_dir):
        raise TransactionError("Изменение res://addons требует явного запроса пользователя и разрешённой политики доступа: %s" % path)
    absolute = _resolve_safe_path(project_root, path)
    if os.path.normcase(absolute) == os.path.normcase(os.path.realpath(os.path.join(project_root, "project.godot"))):
        raise TransactionError("project.godot изменяется только через edit_project_settings")
    return "res://" + rel


def _exact(obj, allowed, label):
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        raise TransactionError("%s содержит неизвестные поля: %s" % (label, ", ".join(unknown)))


def normalize_action(project_root, action, allow_addons=False,
                     allow_self_edit=False, addon_dir=None):
    if not isinstance(action, dict) or action.get("action") != "transaction":
        raise TransactionError("Ожидалось action=transaction")
    _exact(action, ("action", "operations", "checks", "summary"), "transaction")
    raw_operations = action.get("operations")
    if not isinstance(raw_operations, list) or not 1 <= len(raw_operations) <= MAX_OPERATIONS:
        raise TransactionError("transaction должна содержать от 1 до %d операций" % MAX_OPERATIONS)
    operations = []
    for index, raw in enumerate(raw_operations, 1):
        if not isinstance(raw, dict) or raw.get("action") not in _ALLOWED:
            raise TransactionError("Операция %d должна быть create_file, patch_file или move_file" % index)
        kind = raw["action"]
        if kind == "create_file":
            allowed = ("action", "path", "summary", "content")
        elif kind == "patch_file":
            allowed = ("action", "path", "summary", "search", "replace")
        else:
            allowed = ("action", "path", "summary", "dest")
        _exact(raw, allowed, "операция %d" % index)
        item = {"action": kind, "path": _canonical(
            project_root, raw.get("path"), allow_addons,
            allow_self_edit=allow_self_edit, addon_dir=addon_dir)}
        if item["path"].lower().endswith(".tscn"):
            raise TransactionError("Структурные сцены нельзя менять в transaction; используй create_scene/edit_scene")
        if raw.get("summary"):
            item["summary"] = str(raw["summary"])[:500]
        if kind == "create_file":
            if not isinstance(raw.get("content"), str):
                raise TransactionError("create_file %d не содержит text content" % index)
            item["content"] = sanitize_llm_text(raw["content"].replace("\r\n", "\n")) or ""
        elif kind == "patch_file":
            if not isinstance(raw.get("search"), str) or not raw["search"] or not isinstance(raw.get("replace"), str):
                raise TransactionError("patch_file %d требует непустой search и текстовый replace" % index)
            item["search"] = sanitize_llm_text(raw["search"].replace("\r\n", "\n")) or ""
            item["replace"] = sanitize_llm_text(raw["replace"].replace("\r\n", "\n")) or ""
        else:
            item["dest"] = _canonical(
                project_root, raw.get("dest"), allow_addons,
                allow_self_edit=allow_self_edit, addon_dir=addon_dir)
            if item["dest"].lower().endswith(".tscn"):
                raise TransactionError("Структурные сцены нельзя перемещать в transaction")
            if item["dest"] == item["path"]:
                raise TransactionError("move_file не меняет путь")
        operations.append(item)
    raw_checks = action.get("checks", [])
    if not isinstance(raw_checks, list) or len(raw_checks) > MAX_CHECKS:
        raise TransactionError("checks должен быть списком до %d элементов" % MAX_CHECKS)
    checks = []
    for index, raw in enumerate(raw_checks, 1):
        if not isinstance(raw, dict):
            raise TransactionError("Проверка %d не является объектом" % index)
        _exact(raw, ("type", "path"), "проверка %d" % index)
        kind = raw.get("type")
        path = _canonical(project_root, raw.get("path"), allow_addons,
                         allow_self_edit=allow_self_edit, addon_dir=addon_dir)
        if kind == "parse_script" and not path.lower().endswith(".gd"):
            raise TransactionError("parse_script принимает только .gd")
        if kind == "load_scene" and not path.lower().endswith(".tscn"):
            raise TransactionError("load_scene принимает только .tscn")
        if kind not in ("parse_script", "load_scene"):
            raise TransactionError("Неизвестная проверка: %s" % kind)
        check = {"type": kind, "path": path}
        if check not in checks:
            checks.append(check)
    return {"action": "transaction", "operations": operations, "checks": checks,
            "summary": str(action.get("summary") or "")[:500]}


def _entry(project_root, overlay, path):
    if path not in overlay:
        absolute = _resolve_safe_path(project_root, path)
        identity = os.path.normcase(absolute)
        for other in overlay:
            if os.path.normcase(_resolve_safe_path(project_root, other)) == identity:
                raise TransactionError("Один файл указан разными путями: %s, %s" % (other, path))
        before = _read(absolute)
        overlay[path] = {"path": path, "before_bytes": before, "after_bytes": before,
                         "before_hash": _hash(before)}
    return overlay[path]


def _validate_script(project_root, path, data, addon_dir):
    if data is None or not path.lower().endswith(".gd"):
        return
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TransactionError("%s не является UTF-8: %s" % (path, exc))
    errors = list(gd_lint.lint_gdscript(text) or [])
    errors.extend(gd_api_check.check_api_usage(project_root, text, path, addon_dir=addon_dir) or [])
    if errors:
        raise TransactionError("%s не прошёл локальную проверку: %s" % (path, "; ".join(str(x) for x in errors[:8])))


def prepare(project_root, action, allow_addons=False, addon_dir=None,
            allow_self_edit=False):
    normalized = normalize_action(
        project_root, action, allow_addons,
        allow_self_edit=allow_self_edit, addon_dir=addon_dir)
    overlay = {}
    public_paths = []
    effective_operation_count = 0
    skipped_operation_count = 0
    for operation in normalized["operations"]:
        kind, path = operation["action"], operation["path"]
        item = _entry(project_root, overlay, path)
        if kind == "create_file":
            candidate = operation["content"].encode("utf-8")
            if _text_equivalent(item["after_bytes"], candidate):
                skipped_operation_count += 1
            else:
                item["after_bytes"] = candidate
                effective_operation_count += 1
            public_paths.append(path)
        elif kind == "patch_file":
            if item["after_bytes"] is None:
                raise TransactionError("Файл для patch_file не существует в overlay: %s" % path)
            try:
                text = item["after_bytes"].decode("utf-8-sig").replace("\r\n", "\n")
            except UnicodeDecodeError:
                raise TransactionError("patch_file поддерживает только UTF-8: %s" % path)
            if text.count(operation["search"]) != 1:
                raise TransactionError("patch_file должен иметь одно точное совпадение: %s" % path)
            candidate = text.replace(operation["search"], operation["replace"], 1).encode("utf-8")
            if _text_equivalent(item["after_bytes"], candidate):
                skipped_operation_count += 1
            else:
                item["after_bytes"] = candidate
                effective_operation_count += 1
            public_paths.append(path)
        else:
            dest = operation["dest"]
            if item["after_bytes"] is None:
                raise TransactionError("Источник move_file не существует: %s" % path)
            dest_item = _entry(project_root, overlay, dest)
            if dest_item["after_bytes"] is not None:
                raise TransactionError("Назначение move_file уже существует: %s" % dest)
            dest_item["after_bytes"] = item["after_bytes"]
            item["after_bytes"] = None
            effective_operation_count += 1
            public_paths.extend((path, dest))
            uid_source = path + ".uid"
            uid_item = _entry(project_root, overlay, uid_source)
            if uid_item["after_bytes"] is not None:
                uid_dest = dest + ".uid"
                uid_dest_item = _entry(project_root, overlay, uid_dest)
                if uid_dest_item["after_bytes"] is not None:
                    raise TransactionError("UID назначения уже существует: %s" % uid_dest)
                uid_dest_item["after_bytes"] = uid_item["after_bytes"]
                uid_item["after_bytes"] = None
    files = []
    for path in sorted(overlay):
        item = overlay[path]
        if item["before_bytes"] == item["after_bytes"]:
            continue
        item["after_hash"] = _hash(item["after_bytes"])
        _validate_script(project_root, path, item["after_bytes"], addon_dir)
        files.append(item)
    final = {item["path"]: item["after_bytes"] for item in overlay.values()}
    for check in normalized["checks"]:
        data = final.get(check["path"], _read(_resolve_safe_path(project_root, check["path"])))
        if data is None:
            raise TransactionError("Файл проверки отсутствует в итоговом overlay: %s" % check["path"])
        if check["type"] == "parse_script":
            _validate_script(project_root, check["path"], data, addon_dir)
    if not files:
        check_targets = [check["path"] for check in normalized["checks"]]
        batch = (godot_headless_validation.make_batch(
            "transaction", [], check_targets,
            {path: item["before_hash"] for path, item in overlay.items()},
            required_targets=check_targets) if check_targets else None)
        return {"transaction_id": uuid.uuid4().hex, "action": normalized,
                "files": [], "paths": [], "batch": batch, "state": "already_satisfied",
                "already_satisfied": True, "effective_operation_count": 0,
                "skipped_operation_count": len(normalized["operations"])}
    batch_operations = []
    source_hashes = {}
    targets = [check["path"] for check in normalized["checks"]]
    for item in files:
        source_hashes[item["path"]] = item["before_hash"]
        if item["after_bytes"] is None:
            batch_operations.append({"op": "delete", "path": item["path"]})
        else:
            batch_operations.append({"op": "write", "path": item["path"], "content": item["after_bytes"]})
            if item["path"].lower().endswith(godot_headless_validation.RESOURCE_EXTENSIONS):
                targets.append(item["path"])
    targets.extend(godot_headless_validation._referencer_targets(
        project_root, source_hashes.keys(), excluded=source_hashes.keys()))
    batch = godot_headless_validation.make_batch(
        "transaction", batch_operations, targets, source_hashes,
        required_targets=[check["path"] for check in normalized["checks"]])
    return {"transaction_id": uuid.uuid4().hex, "action": normalized, "files": files,
            "paths": [item["path"] for item in files], "batch": batch, "state": "preview",
            "already_satisfied": False,
            "effective_operation_count": effective_operation_count,
            "skipped_operation_count": skipped_operation_count}


def attach_validation(prepared, receipt):
    prepared["receipt"] = receipt
    return prepared


def public_prepared(prepared):
    return {"action": "transaction", "transaction_id": prepared["transaction_id"],
            "summary": prepared["action"].get("summary", ""), "paths": prepared["paths"],
            "operation_count": len(prepared["action"]["operations"]),
            "check_count": len(prepared["action"]["checks"]), "file_count": len(prepared["files"]),
            "already_satisfied": bool(prepared.get("already_satisfied")),
            "effective_operation_count": int(prepared.get("effective_operation_count", 0)),
            "skipped_operation_count": int(prepared.get("skipped_operation_count", 0))}


def prepared_diffs(prepared):
    result = []
    for item in prepared["files"]:
        if item["path"].endswith(".uid"):
            continue
        before = None if item["before_bytes"] is None else item["before_bytes"].decode("utf-8-sig", errors="replace")
        after = "" if item["after_bytes"] is None else item["after_bytes"].decode("utf-8-sig", errors="replace")
        diff = build_diff_preview(before, after)
        if diff:
            diff.update({"path": item["path"], "action": "transaction"})
            result.append(diff)
    return result


def verify_prepared(project_root, prepared):
    if prepared.get("already_satisfied"):
        raise TransactionError("Уже выполненная транзакция не требует применения")
    godot_headless_validation.verify_receipt(project_root, prepared["batch"], prepared["receipt"])
    for item in prepared["files"]:
        current = _read(_resolve_safe_path(project_root, item["path"]))
        if _hash(current) != item["before_hash"]:
            raise StaleTransactionError("Файл изменился после предпросмотра: %s" % item["path"])


def _restore(project_root, files):
    for item in files:
        absolute = _resolve_safe_path(project_root, item["path"])
        before = item["before_bytes"]
        if before is None:
            if os.path.exists(absolute):
                os.remove(absolute)
            continue
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".agent_tx_restore_", dir=os.path.dirname(absolute))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(before)
                handle.flush()
                os.fsync(handle.fileno())
            _replace_file(temporary, absolute)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)


def apply_prepared(project_root, prepared, chat_id=None, chat_title=None):
    with _lock(project_root):
        verify_prepared(project_root, prepared)
        prepared["state"] = "applying"
        entry_id = history_manager.record_batch_change(
            project_root, "transaction", [item["path"] for item in prepared["files"]],
            chat_id, chat_title, states=prepared["files"])
        temps = {}
        try:
            for item in prepared["files"]:
                if item["after_bytes"] is None:
                    continue
                absolute = _resolve_safe_path(project_root, item["path"])
                os.makedirs(os.path.dirname(absolute), exist_ok=True)
                descriptor, temporary = tempfile.mkstemp(prefix=".agent_tx_", dir=os.path.dirname(absolute))
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(item["after_bytes"])
                    handle.flush()
                    os.fsync(handle.fileno())
                temps[item["path"]] = temporary
            applied = []
            for item in prepared["files"]:
                absolute = _resolve_safe_path(project_root, item["path"])
                if item["after_bytes"] is None:
                    if os.path.exists(absolute):
                        os.remove(absolute)
                else:
                    _replace_file(temps.pop(item["path"]), absolute)
                applied.append(item)
            history_manager.commit_change(project_root, entry_id)
        except Exception:
            restore_error = None
            try:
                _restore(project_root, applied if "applied" in locals() else [])
            except Exception as exc:
                restore_error = exc
            if restore_error is None:
                history_manager.abort_change(project_root, entry_id)
            else:
                prepared["state"] = "recovery_required"
            for temporary in temps.values():
                try:
                    os.remove(temporary)
                except OSError:
                    pass
            if restore_error is not None:
                raise TransactionError(
                    "Применение прервано, автоматическое восстановление не завершено: %s" % restore_error)
            raise
        prepared["state"] = "committed"
        return {"entry_id": entry_id, "changed_paths": prepared["paths"],
                "file_count": len(prepared["files"])}
