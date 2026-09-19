# -*- coding: utf-8 -*-
"""Strict schema for project settings changes executed by Godot itself."""
import hashlib
import json
import math
import os
import re
import uuid

from project_tools import _resolve_safe_path, is_addon_path


class ProjectSettingsActionError(ValueError):
    pass


MAX_OPERATIONS = 20
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_./-]{0,119}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_KEY_RE = re.compile(r"^[A-Z0-9_]{1,80}$")
_LAYERS = {
    "2d_render": 20, "2d_physics": 32, "2d_navigation": 32,
    "3d_render": 20, "3d_physics": 32, "3d_navigation": 32,
}
_WINDOW_MODES = {"windowed", "minimized", "maximized", "fullscreen", "exclusive_fullscreen"}
_STRETCH_MODES = {"disabled", "canvas_items", "viewport"}
_STRETCH_ASPECTS = {"ignore", "keep", "keep_width", "keep_height", "expand"}


def _exact_fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise ProjectSettingsActionError("Операция настроек должна быть JSON-объектом")
    missing = set(required) - set(value)
    unknown = set(value) - set(required) - set(optional)
    if missing:
        raise ProjectSettingsActionError("Не хватает полей: %s" % ", ".join(sorted(missing)))
    if unknown:
        raise ProjectSettingsActionError("Неизвестные поля: %s" % ", ".join(sorted(unknown)))


def _text(value, field, limit=240):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ProjectSettingsActionError(
            "%s должен быть непустой строкой до %d символов" % (field, limit))
    return value


def _project_path(project_root, value, field, extensions, allow_addons=False):
    path = _text(value, field, 500).replace("\\", "/")
    if not path.startswith("res://") or not path.lower().endswith(extensions):
        raise ProjectSettingsActionError("%s имеет неподдерживаемый res:// путь" % field)
    if not allow_addons and is_addon_path(path, project_root):
        raise ProjectSettingsActionError("Ресурсы аддонов разрешены только по явному запросу")
    absolute = _resolve_safe_path(project_root, path)
    if not os.path.isfile(absolute):
        raise ProjectSettingsActionError("Ресурс не найден: %s" % path)
    return path


def _normalize_event(raw):
    if not isinstance(raw, dict):
        raise ProjectSettingsActionError("event должен быть объектом")
    kind = raw.get("type")
    if kind == "key":
        _exact_fields(raw, ("type", "key"), ("physical", "ctrl", "alt", "shift", "meta"))
        key = _text(raw["key"], "event.key", 80).upper()
        if not _KEY_RE.match(key):
            raise ProjectSettingsActionError("event.key должен быть символическим именем клавиши")
        return {"type": kind, "key": key,
                "physical": bool(raw.get("physical", False)),
                "ctrl": bool(raw.get("ctrl", False)), "alt": bool(raw.get("alt", False)),
                "shift": bool(raw.get("shift", False)), "meta": bool(raw.get("meta", False))}
    if kind == "mouse_button":
        _exact_fields(raw, ("type", "button"))
        button = raw["button"]
        if isinstance(button, bool) or not isinstance(button, int) or not 1 <= button <= 9:
            raise ProjectSettingsActionError("mouse button должен быть целым числом 1..9")
        return {"type": kind, "button": button}
    if kind == "joypad_button":
        _exact_fields(raw, ("type", "button"), ("device",))
        button, device = raw["button"], raw.get("device", -1)
        if (isinstance(button, bool) or not isinstance(button, int) or not 0 <= button <= 31
                or isinstance(device, bool) or not isinstance(device, int) or not -1 <= device <= 15):
            raise ProjectSettingsActionError("Некорректная кнопка или устройство joypad")
        return {"type": kind, "button": button, "device": device}
    if kind == "joypad_motion":
        _exact_fields(raw, ("type", "axis", "axis_value"), ("device",))
        axis, value, device = raw["axis"], raw["axis_value"], raw.get("device", -1)
        if isinstance(axis, bool) or not isinstance(axis, int) or not 0 <= axis <= 9:
            raise ProjectSettingsActionError("joypad axis должен быть целым числом 0..9")
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(float(value)) or not -1.0 <= float(value) <= 1.0
                or float(value) == 0.0):
            raise ProjectSettingsActionError("axis_value должен быть конечным ненулевым числом -1..1")
        if isinstance(device, bool) or not isinstance(device, int) or not -1 <= device <= 15:
            raise ProjectSettingsActionError("Некорректное устройство joypad")
        return {"type": kind, "axis": axis, "axis_value": float(value), "device": device}
    raise ProjectSettingsActionError("Неподдерживаемый тип InputEvent: %s" % kind)


def _normalize_operation(project_root, raw, allow_addons):
    if not isinstance(raw, dict):
        raise ProjectSettingsActionError("Каждая операция должна быть объектом")
    op = raw.get("op")
    if op == "add_input_action":
        _exact_fields(raw, ("op", "name"), ("deadzone",))
        name = _text(raw["name"], "name", 120)
        deadzone = raw.get("deadzone", 0.2)
        if not _NAME_RE.match(name):
            raise ProjectSettingsActionError("Недопустимое имя InputMap action")
        if (isinstance(deadzone, bool) or not isinstance(deadzone, (int, float))
                or not math.isfinite(float(deadzone)) or not 0.0 <= float(deadzone) <= 1.0):
            raise ProjectSettingsActionError("deadzone должен быть конечным числом 0..1")
        return {"op": op, "name": name, "deadzone": float(deadzone)}
    if op == "add_input_event":
        _exact_fields(raw, ("op", "action", "event"))
        name = _text(raw["action"], "action", 120)
        if not _NAME_RE.match(name):
            raise ProjectSettingsActionError("Недопустимое имя InputMap action")
        return {"op": op, "action": name, "event": _normalize_event(raw["event"])}
    if op in ("add_autoload", "remove_autoload"):
        required = ("op", "name", "path") if op == "add_autoload" else ("op", "name")
        _exact_fields(raw, required)
        name = _text(raw["name"], "name", 120)
        if not _IDENTIFIER_RE.match(name):
            raise ProjectSettingsActionError("Имя autoload должно быть GDScript-идентификатором")
        result = {"op": op, "name": name}
        if op == "add_autoload":
            result["path"] = _project_path(
                project_root, raw["path"], "path", (".gd", ".tscn"), allow_addons)
        return result
    if op == "set_main_scene":
        _exact_fields(raw, ("op", "scene"))
        return {"op": op, "scene": _project_path(
            project_root, raw["scene"], "scene", (".tscn",), allow_addons)}
    if op == "set_layer_name":
        _exact_fields(raw, ("op", "layer", "index", "name"))
        layer, index, name = raw["layer"], raw["index"], raw["name"]
        if layer not in _LAYERS:
            raise ProjectSettingsActionError("Неизвестная категория layer")
        if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= _LAYERS[layer]:
            raise ProjectSettingsActionError("index слоя вне допустимого диапазона")
        if not isinstance(name, str) or len(name) > 120:
            raise ProjectSettingsActionError("name слоя должен быть строкой до 120 символов")
        return {"op": op, "layer": layer, "index": index, "name": name}
    if op == "set_display_settings":
        allowed = {"op", "viewport_width", "viewport_height", "window_mode",
                   "resizable", "stretch_mode", "stretch_aspect"}
        unknown = set(raw) - allowed
        if unknown:
            raise ProjectSettingsActionError("Неизвестные поля: %s" % ", ".join(sorted(unknown)))
        if len(raw) == 1:
            raise ProjectSettingsActionError("set_display_settings не содержит настроек")
        result = {"op": op}
        for field in ("viewport_width", "viewport_height"):
            if field in raw:
                value = raw[field]
                if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 16384:
                    raise ProjectSettingsActionError("%s должен быть целым числом 1..16384" % field)
                result[field] = value
        if "window_mode" in raw:
            if raw["window_mode"] not in _WINDOW_MODES:
                raise ProjectSettingsActionError("Неподдерживаемый window_mode")
            result["window_mode"] = raw["window_mode"]
        if "resizable" in raw:
            if not isinstance(raw["resizable"], bool):
                raise ProjectSettingsActionError("resizable требует true/false")
            result["resizable"] = raw["resizable"]
        if "stretch_mode" in raw:
            if raw["stretch_mode"] not in _STRETCH_MODES:
                raise ProjectSettingsActionError("Неподдерживаемый stretch_mode")
            result["stretch_mode"] = raw["stretch_mode"]
        if "stretch_aspect" in raw:
            if raw["stretch_aspect"] not in _STRETCH_ASPECTS:
                raise ProjectSettingsActionError("Неподдерживаемый stretch_aspect")
            result["stretch_aspect"] = raw["stretch_aspect"]
        return result
    raise ProjectSettingsActionError("Неизвестная операция настроек: %s" % op)


def _validate_sequence(operations):
    added_actions, added_autoloads = set(), set()
    for index, operation in enumerate(operations, 1):
        if operation["op"] == "add_input_action":
            name = operation["name"]
            if name in added_actions:
                raise ProjectSettingsActionError("InputMap action %s создаётся дважды" % name)
            added_actions.add(name)
        elif operation["op"] == "add_autoload":
            name = operation["name"]
            if name in added_autoloads:
                raise ProjectSettingsActionError("Autoload %s создаётся дважды" % name)
            added_autoloads.add(name)
        elif operation["op"] == "remove_autoload" and operation["name"] in added_autoloads:
            raise ProjectSettingsActionError(
                "Операция %d удаляет autoload, созданный той же транзакцией" % index)


def normalize_action(project_root, action, allow_addons=False):
    _exact_fields(action, ("action", "operations"), ("summary",))
    if action.get("action") != "edit_project_settings":
        raise ProjectSettingsActionError("Ожидалось action=edit_project_settings")
    operations = action["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise ProjectSettingsActionError("operations должен содержать от 1 до %d операций" % MAX_OPERATIONS)
    normalized_ops = [_normalize_operation(project_root, item, allow_addons) for item in operations]
    _validate_sequence(normalized_ops)
    normalized = {"action": "edit_project_settings", "operations": normalized_ops}
    summary = action.get("summary")
    if isinstance(summary, str) and summary.strip():
        normalized["summary"] = summary.strip()[:500]
    project_file = _resolve_safe_path(project_root, "res://project.godot")
    if not os.path.isfile(project_file):
        raise ProjectSettingsActionError("project.godot не найден")
    return normalized, project_file


def canonical_digest(action):
    payload = json.dumps(action, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(absolute):
    with open(absolute, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def prepare(project_root, action, allow_addons=False):
    normalized, absolute = normalize_action(project_root, action, allow_addons)
    return {"action_id": uuid.uuid4().hex, "action": normalized,
            "action_digest": canonical_digest(normalized),
            "before_hash": file_sha256(absolute), "state": "preview",
            "target": "res://project.godot", "kind": "project_settings"}


def public_prepared(prepared):
    return {"action_id": prepared["action_id"], "action_digest": prepared["action_digest"],
            "expected_project_hash": prepared["before_hash"], "prepare_in_editor": True}
