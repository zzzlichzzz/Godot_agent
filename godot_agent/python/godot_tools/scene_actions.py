# -*- coding: utf-8 -*-
"""Validation and private server state for structural Godot scene edits.

The module deliberately does not parse or rewrite .tscn. Godot validates and
executes the normalized operation list through agent_scene_executor.gd.
"""
import hashlib
import json
import math
import os
import re
import uuid

from project_tools import _resolve_safe_path


class SceneActionError(ValueError):
    pass


MAX_OPERATIONS = 20
_NODE_NAME_RE = re.compile(r"^[^./:@\"\\]+$")
_MEMBER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CLASS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VARIANT_ARITY = {
    "Vector2": 2, "Vector2i": 2, "Vector3": 3, "Vector3i": 3,
    "Color": 4,
}
_SCALAR_TYPES = {"Nil", "bool", "int", "float", "String", "StringName", "NodePath"}


def _exact_fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise SceneActionError("Операция сцены должна быть JSON-объектом")
    missing = set(required) - set(value)
    unknown = set(value) - set(required) - set(optional)
    if missing:
        raise SceneActionError("Не хватает полей: %s" % ", ".join(sorted(missing)))
    if unknown:
        raise SceneActionError("Неизвестные поля: %s" % ", ".join(sorted(unknown)))


def _text(value, field, limit=240):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise SceneActionError("%s должен быть непустой строкой до %d символов" % (field, limit))
    return value


def normalize_node_path(value, field="node"):
    path = _text(value, field, 500).replace("\\", "/")
    if path == ".":
        return path
    if path.startswith("/") or path.endswith("/") or "//" in path:
        raise SceneActionError("%s должен быть путём относительно корня сцены" % field)
    parts = path.split("/")
    if any(part in ("", ".", "..") or part.startswith("%") for part in parts):
        raise SceneActionError("%s содержит запрещённый сегмент" % field)
    if any(not _NODE_NAME_RE.match(part) for part in parts):
        raise SceneActionError("%s содержит недопустимое имя узла" % field)
    return path


def _normalize_scene_path(project_root, value, allow_addons=False, must_exist=True):
    path = _text(value, "scene", 500).replace("\\", "/")
    if not path.startswith("res://") or not path.lower().endswith(".tscn"):
        raise SceneActionError("scene должен быть res:// путём к текстовой .tscn")
    relative = path[len("res://"):].lstrip("/")
    if relative.lower().startswith("addons/") and not allow_addons:
        raise SceneActionError("Сцены аддонов разрешены только по явному запросу пользователя")
    absolute = _resolve_safe_path(project_root, path)
    if must_exist and not os.path.isfile(absolute):
        raise SceneActionError("Сцена не найдена: %s" % path)
    if must_exist is False and os.path.lexists(absolute):
        raise SceneActionError("Сцена уже существует: %s" % path)
    return path, absolute


def _normalize_script(project_root, value, allow_addons=False):
    script = _text(value, "script", 500).replace("\\", "/")
    if not script.startswith("res://") or not script.lower().endswith(".gd"):
        raise SceneActionError("script должен быть res:// путём к .gd")
    relative = script[len("res://"):].lstrip("/")
    if relative.lower().startswith("addons/") and not allow_addons:
        raise SceneActionError("Скрипты аддонов разрешены только по явному запросу пользователя")
    if not os.path.isfile(_resolve_safe_path(project_root, script)):
        raise SceneActionError("Скрипт не найден: %s" % script)
    return script


def normalize_variant(value):
    _exact_fields(value, ("type", "value"))
    kind = _text(value["type"], "value.type", 30)
    raw = value["value"]
    if kind not in _SCALAR_TYPES and kind not in _VARIANT_ARITY:
        raise SceneActionError("Неподдерживаемый тип свойства: %s" % kind)
    if kind == "Nil":
        if raw is not None:
            raise SceneActionError("Nil должен иметь value=null")
    elif kind == "bool":
        if not isinstance(raw, bool):
            raise SceneActionError("bool требует true/false")
    elif kind == "int":
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise SceneActionError("int требует целое число")
    elif kind == "float":
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
            raise SceneActionError("float требует конечное число")
        raw = float(raw)
    elif kind in ("String", "StringName"):
        if not isinstance(raw, str) or len(raw) > 4000:
            raise SceneActionError("%s требует строку до 4000 символов" % kind)
    elif kind == "NodePath":
        raw = normalize_node_path(raw, "value.value")
    else:
        arity = _VARIANT_ARITY[kind]
        if not isinstance(raw, list) or len(raw) != arity:
            raise SceneActionError("%s требует массив из %d чисел" % (kind, arity))
        converted = []
        for item in raw:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
                raise SceneActionError("%s содержит нечисловое или бесконечное значение" % kind)
            converted.append(int(item) if kind.endswith("i") else float(item))
        raw = converted
    return {"type": kind, "value": raw}


def _normalize_operation(raw):
    if not isinstance(raw, dict):
        raise SceneActionError("Каждая операция должна быть объектом")
    op = raw.get("op")
    if op == "add_node":
        _exact_fields(raw, ("op", "parent", "name", "type"))
        name = _text(raw["name"], "name", 120)
        if not _NODE_NAME_RE.match(name):
            raise SceneActionError("Недопустимое имя нового узла: %s" % name)
        node_type = _text(raw["type"], "type", 120)
        if not _CLASS_RE.match(node_type):
            raise SceneActionError("Недопустимое имя класса узла")
        return {"op": op, "parent": normalize_node_path(raw["parent"], "parent"),
                "name": name, "type": node_type}
    if op == "set_node_property":
        _exact_fields(raw, ("op", "node", "property", "value"))
        prop = _text(raw["property"], "property", 160)
        if not _MEMBER_RE.match(prop):
            raise SceneActionError("Недопустимое имя свойства")
        return {"op": op, "node": normalize_node_path(raw["node"]),
                "property": prop, "value": normalize_variant(raw["value"])}
    if op == "attach_script":
        _exact_fields(raw, ("op", "node", "script"), ("replace_existing",))
        script = _text(raw["script"], "script", 500).replace("\\", "/")
        if not script.startswith("res://") or not script.endswith(".gd"):
            raise SceneActionError("script должен быть res:// путём к .gd")
        relative = script[len("res://"):].lstrip("/")
        if relative.startswith("addons/"):
            # Addon policy is enforced with the project root in normalize_action.
            pass
        return {"op": op, "node": normalize_node_path(raw["node"]), "script": script,
                "replace_existing": bool(raw.get("replace_existing", False))}
    if op == "connect_signal":
        _exact_fields(raw, ("op", "source", "signal", "target", "method"))
        signal = _text(raw["signal"], "signal", 160)
        method = _text(raw["method"], "method", 160)
        if not _MEMBER_RE.match(signal) or not _MEMBER_RE.match(method):
            raise SceneActionError("signal и method должны быть идентификаторами")
        return {"op": op, "source": normalize_node_path(raw["source"], "source"),
                "signal": signal, "target": normalize_node_path(raw["target"], "target"),
                "method": method}
    if op == "reparent_node":
        _exact_fields(raw, ("op", "node", "new_parent"), ("keep_global_transform",))
        node = normalize_node_path(raw["node"])
        parent = normalize_node_path(raw["new_parent"], "new_parent")
        if node == ".":
            raise SceneActionError("Корень сцены нельзя перемещать")
        if parent == node or parent.startswith(node + "/"):
            raise SceneActionError("Нельзя переместить узел внутрь самого себя")
        return {"op": op, "node": node, "new_parent": parent,
                "keep_global_transform": bool(raw.get("keep_global_transform", True))}
    raise SceneActionError("Неизвестная структурная операция: %s" % op)


def _join(parent, name):
    return name if parent == "." else parent + "/" + name


def _validate_sequence(operations):
    created = set()
    moved_old = set()
    for index, operation in enumerate(operations):
        paths = [operation[key] for key in ("node", "parent", "source", "target", "new_parent")
                 if key in operation]
        stale = sorted(path for path in paths if path in moved_old)
        if stale:
            raise SceneActionError("Операция %d использует старый путь после reparent: %s" %
                                   (index + 1, ", ".join(stale)))
        if operation["op"] == "add_node":
            path = _join(operation["parent"], operation["name"])
            if path in created:
                raise SceneActionError("Узел %s создаётся дважды" % path)
            created.add(path)
        elif operation["op"] == "reparent_node":
            old = operation["node"]
            moved_old.add(old)


def normalize_action(project_root, action, allow_addons=False, require_target_state=True):
    kind = action.get("action") if isinstance(action, dict) else None
    if kind not in ("edit_scene", "create_scene"):
        raise SceneActionError("Ожидалось action=edit_scene или action=create_scene")
    required = ("action", "scene", "operations", "root") if kind == "create_scene" else (
        "action", "scene", "operations")
    _exact_fields(action, required, ("summary",))
    must_exist = True if kind == "edit_scene" else False
    if not require_target_state:
        must_exist = None
    scene, absolute = _normalize_scene_path(project_root, action["scene"], allow_addons, must_exist)
    raw_operations = action["operations"]
    minimum = 0 if kind == "create_scene" else 1
    if not isinstance(raw_operations, list) or not (minimum <= len(raw_operations) <= MAX_OPERATIONS):
        raise SceneActionError("operations должен содержать от %d до %d операций" % (minimum, MAX_OPERATIONS))
    operations = [_normalize_operation(item) for item in raw_operations]
    for operation in operations:
        if operation["op"] != "attach_script":
            continue
        operation["script"] = _normalize_script(project_root, operation["script"], allow_addons)
    _validate_sequence(operations)
    normalized = {"action": kind, "scene": scene, "operations": operations}
    if kind == "create_scene":
        root = action["root"]
        _exact_fields(root, ("name", "type"), ("script",))
        name = _text(root["name"], "root.name", 120)
        node_type = _text(root["type"], "root.type", 120)
        if not _NODE_NAME_RE.match(name) or not _CLASS_RE.match(node_type):
            raise SceneActionError("Некорректное имя или native type корня сцены")
        normalized_root = {"name": name, "type": node_type}
        if root.get("script") is not None:
            normalized_root["script"] = _normalize_script(
                project_root, root["script"], allow_addons)
        normalized["root"] = normalized_root
    summary = action.get("summary")
    if summary is not None:
        if not isinstance(summary, str) or not summary.strip() or len(summary.strip()) > 500:
            raise SceneActionError("summary должен быть непустой строкой до 500 символов")
        normalized["summary"] = summary.strip()
    return normalized, absolute


def canonical_digest(action):
    payload = json.dumps(action, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(absolute):
    with open(absolute, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def staged_scene_path(absolute, action_id):
    if not isinstance(action_id, str) or not re.fullmatch(r"[0-9a-f]{32}", action_id):
        raise SceneActionError("Некорректный идентификатор временной сцены")
    return absolute + ".agent-create-%s.tmp.tscn" % action_id


def materialize_staged_scene(absolute, action_id, expected_hash):
    """Atomically publish a staged scene without ever replacing a destination."""
    staged = staged_scene_path(absolute, action_id)
    if os.path.lexists(absolute):
        raise SceneActionError("Целевая сцена появилась после предпросмотра")
    if not os.path.isfile(staged) or os.path.islink(staged):
        raise SceneActionError("Временная сцена не найдена или небезопасна")
    actual_hash = file_sha256(staged)
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise SceneActionError("Godot не передал корректный хэш временной сцены")
    if actual_hash != expected_hash:
        raise SceneActionError("Хэш временной сцены не совпал с отчётом Godot")
    try:
        # The staged file is a sibling, so hard-link creation is atomic and
        # fails when another process has already claimed the destination.
        os.link(staged, absolute)
    except FileExistsError:
        raise SceneActionError("Целевая сцена появилась после предпросмотра")
    except OSError as exc:
        raise SceneActionError("Не удалось атомарно опубликовать сцену: %s" % exc)
    try:
        os.unlink(staged)
    except OSError:
        # Destination is already complete and authoritative. A stale staging
        # file is harmless and can be removed by a later preparation.
        pass
    return file_sha256(absolute)


def discard_staged_scene(absolute, action_id):
    staged = staged_scene_path(absolute, action_id)
    if os.path.isfile(staged) and not os.path.islink(staged):
        try:
            os.unlink(staged)
        except OSError:
            pass


def prepare(project_root, action, allow_addons=False):
    normalized, absolute = normalize_action(project_root, action, allow_addons)
    return {
        "action_id": uuid.uuid4().hex,
        "action": normalized,
        "scene": normalized["scene"],
        "action_digest": canonical_digest(normalized),
        "before_hash": file_sha256(absolute) if normalized["action"] == "edit_scene" else None,
        "state": "preview",
    }


def public_prepared(prepared):
    return {
        "action_id": prepared["action_id"],
        "action_digest": prepared["action_digest"],
        "expected_scene_hash": prepared["before_hash"] or "",
        "prepare_in_editor": True,
    }


def operation_summary(action):
    labels = {
        "add_node": "добавить узел", "set_node_property": "изменить свойство",
        "connect_signal": "подключить сигнал", "attach_script": "назначить скрипт",
        "reparent_node": "переместить узел",
    }
    result = []
    if action.get("action") == "create_scene":
        root = action.get("root") or {}
        result.append("0. создать корень %s (%s)" % (root.get("name", ""), root.get("type", "")))
    result.extend("%d. %s" % (index, labels.get(op["op"], op["op"]))
                  for index, op in enumerate(action.get("operations") or [], 1))
    return result
