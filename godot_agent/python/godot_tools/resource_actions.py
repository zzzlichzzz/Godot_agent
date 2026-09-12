# -*- coding: utf-8 -*-
"""Strict schema and private state for structural edits of existing .tres files."""
import hashlib
import json
import math
import os
import re
import uuid

from project_tools import _resolve_safe_path
from scene_actions import normalize_variant


class ResourceActionError(ValueError):
    pass


MAX_OPERATIONS = 20
_MEMBER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CLASS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_THEME_TYPES = {"color", "constant", "font", "font_size", "icon", "stylebox"}
_INTERPOLATION = {"nearest", "linear", "cubic"}
_UPDATE_MODES = {"continuous", "discrete", "capture"}
_THEME_VALUE_TYPES = {"color": {"Color"}, "constant": {"int"},
                      "font_size": {"int"}, "font": {"ResourcePath", "NewSubresource"},
                      "icon": {"ResourcePath", "NewSubresource"},
                      "stylebox": {"ResourcePath", "NewSubresource"}}


def _exact(value, required, optional=()):
    if not isinstance(value, dict):
        raise ResourceActionError("Операция ресурса должна быть JSON-объектом")
    missing = set(required) - set(value)
    unknown = set(value) - set(required) - set(optional)
    if missing:
        raise ResourceActionError("Не хватает полей: %s" % ", ".join(sorted(missing)))
    if unknown:
        raise ResourceActionError("Неизвестные поля: %s" % ", ".join(sorted(unknown)))


def _text(value, field, limit=500, allow_empty=False):
    if not isinstance(value, str) or len(value) > limit or (not allow_empty and not value):
        raise ResourceActionError("%s должен быть строкой до %d символов" % (field, limit))
    return value


def _number(value, field, minimum=None, maximum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ResourceActionError("%s должен быть конечным числом" % field)
    result = float(value)
    if positive and result <= 0:
        raise ResourceActionError("%s должен быть положительным" % field)
    if minimum is not None and result < minimum or maximum is not None and result > maximum:
        raise ResourceActionError("%s вне допустимого диапазона" % field)
    return result


def _path(project_root, value, field, extensions=None, allow_addons=False):
    path = _text(value, field).replace("\\", "/")
    if not path.startswith("res://"):
        raise ResourceActionError("%s должен быть res:// путём" % field)
    relative = path[6:].lstrip("/")
    if relative.startswith("addons/") and not allow_addons:
        raise ResourceActionError("Ресурсы аддонов разрешены только по явному запросу пользователя")
    if extensions and not path.lower().endswith(tuple(extensions)):
        raise ResourceActionError("%s имеет неподдерживаемое расширение" % field)
    absolute = _resolve_safe_path(project_root, path)
    if not os.path.isfile(absolute):
        raise ResourceActionError("Ресурс не найден: %s" % path)
    return path, absolute


def _target(value):
    if not isinstance(value, list) or len(value) > 8:
        raise ResourceActionError("target должен быть массивом до 8 свойств")
    result = []
    for item in value:
        name = _text(item, "target", 160)
        if not _MEMBER_RE.match(name):
            raise ResourceActionError("target содержит недопустимое имя свойства")
        result.append(name)
    return result


def _tagged(project_root, value, allow_addons=False, depth=0, counter=None):
    if not isinstance(value, dict):
        raise ResourceActionError("value должен быть tagged JSON-объектом")
    kind = value.get("type")
    if kind == "ResourcePath":
        _exact(value, ("type", "value"))
        path, _absolute = _path(project_root, value["value"], "ResourcePath", allow_addons=allow_addons)
        return {"type": kind, "value": path}
    if kind == "NewSubresource":
        _exact(value, ("type", "class"), ("properties",))
        if depth >= 4:
            raise ResourceActionError("NewSubresource глубже 4 уровней запрещён")
        cls = _text(value["class"], "class", 120)
        if not _CLASS_RE.match(cls):
            raise ResourceActionError("Недопустимый класс NewSubresource")
        properties = value.get("properties") or []
        if not isinstance(properties, list) or len(properties) > 32:
            raise ResourceActionError("properties NewSubresource должен быть массивом до 32 элементов")
        counter = counter if counter is not None else [0]
        counter[0] += 1
        if counter[0] > 32:
            raise ResourceActionError("Одно действие не может создавать более 32 subresource")
        normalized = []
        seen = set()
        for item in properties:
            _exact(item, ("property", "value"))
            prop = _text(item["property"], "property", 160)
            if not _MEMBER_RE.match(prop) or prop in seen or prop in ("resource_path", "resource_name", "script"):
                raise ResourceActionError("Недопустимое или повторное свойство NewSubresource: %s" % prop)
            seen.add(prop)
            normalized.append({"property": prop,
                               "value": _tagged(project_root, item["value"], allow_addons, depth + 1, counter)})
        return {"type": kind, "class": cls, "properties": normalized}
    try:
        return normalize_variant(value)
    except Exception as exc:
        raise ResourceActionError(str(exc))


def _normalize_operation(project_root, raw, allow_addons=False, subresource_counter=None):
    if not isinstance(raw, dict):
        raise ResourceActionError("Каждая операция должна быть объектом")
    op = raw.get("op")
    if op == "set_property":
        _exact(raw, ("op", "target", "property", "value"))
        prop = _text(raw["property"], "property", 160)
        if not _MEMBER_RE.match(prop):
            raise ResourceActionError("Недопустимое имя свойства")
        return {"op": op, "target": _target(raw["target"]), "property": prop,
                "value": _tagged(project_root, raw["value"], allow_addons,
                                  counter=subresource_counter)}
    if op == "replace_reference":
        _exact(raw, ("op", "target", "old", "new", "expected_count"))
        old, _ = _path(project_root, raw["old"], "old", allow_addons=allow_addons)
        new, _ = _path(project_root, raw["new"], "new", allow_addons=allow_addons)
        count = raw["expected_count"]
        if isinstance(count, bool) or not isinstance(count, int) or not (1 <= count <= 10000):
            raise ResourceActionError("expected_count должен быть целым числом 1..10000")
        if old == new:
            raise ResourceActionError("old и new должны различаться")
        return {"op": op, "target": _target(raw["target"]), "old": old, "new": new,
                "expected_count": count}
    if op == "animation_add_value_track":
        _exact(raw, ("op", "path", "keys"), ("interpolation", "update_mode"))
        keys = raw["keys"]
        if not isinstance(keys, list) or not (1 <= len(keys) <= 512):
            raise ResourceActionError("keys должен содержать от 1 до 512 ключей")
        normalized_keys = []
        previous = -1.0
        for key in keys:
            _exact(key, ("time", "value"), ("transition",))
            timestamp = _number(key["time"], "time", minimum=0)
            if timestamp <= previous:
                raise ResourceActionError("Время ключей Animation должно строго возрастать")
            previous = timestamp
            normalized_keys.append({"time": timestamp,
                                    "value": _tagged(project_root, key["value"], allow_addons,
                                                     counter=subresource_counter),
                                    "transition": _number(key.get("transition", 1.0), "transition", positive=True)})
        interpolation = raw.get("interpolation", "linear")
        update_mode = raw.get("update_mode", "continuous")
        if interpolation not in _INTERPOLATION or update_mode not in _UPDATE_MODES:
            raise ResourceActionError("Неподдерживаемый режим Animation")
        return {"op": op, "path": _text(raw["path"], "path", 500), "keys": normalized_keys,
                "interpolation": interpolation, "update_mode": update_mode}
    if op == "sprite_frames_add_animation":
        _exact(raw, ("op", "name", "fps", "loop", "frames"))
        frames = raw["frames"]
        if not isinstance(frames, list) or not (1 <= len(frames) <= 256):
            raise ResourceActionError("frames должен содержать от 1 до 256 кадров")
        result = []
        for frame in frames:
            _exact(frame, ("texture",), ("duration",))
            texture = _tagged(project_root, frame["texture"], allow_addons)
            if texture.get("type") != "ResourcePath":
                raise ResourceActionError("texture кадра должен быть ResourcePath")
            result.append({"texture": texture,
                           "duration": _number(frame.get("duration", 1.0), "duration", positive=True)})
        if not isinstance(raw["loop"], bool):
            raise ResourceActionError("loop должен быть bool")
        return {"op": op, "name": _text(raw["name"], "name", 120),
                "fps": _number(raw["fps"], "fps", positive=True),
                "loop": raw["loop"], "frames": result}
    if op == "theme_set_item":
        _exact(raw, ("op", "data_type", "theme_type", "name", "value"), ("overwrite",))
        data_type = raw["data_type"]
        if data_type not in _THEME_TYPES:
            raise ResourceActionError("Неподдерживаемый тип Theme item")
        if "overwrite" in raw and not isinstance(raw["overwrite"], bool):
            raise ResourceActionError("overwrite должен быть bool")
        tagged = _tagged(project_root, raw["value"], allow_addons,
                         counter=subresource_counter)
        if tagged.get("type") not in _THEME_VALUE_TYPES[data_type]:
            raise ResourceActionError("Тип value не подходит для Theme item %s" % data_type)
        return {"op": op, "data_type": data_type,
                "theme_type": _text(raw["theme_type"], "theme_type", 120),
                "name": _text(raw["name"], "name", 120),
                "overwrite": raw.get("overwrite", False),
                "value": tagged}
    if op == "tileset_add_atlas_source":
        _exact(raw, ("op", "source_id", "texture", "texture_region_size", "tiles"))
        source_id = raw["source_id"]
        if isinstance(source_id, bool) or not isinstance(source_id, int) or source_id < 0:
            raise ResourceActionError("source_id должен быть неотрицательным целым")
        texture = _tagged(project_root, raw["texture"], allow_addons)
        if texture.get("type") != "ResourcePath":
            raise ResourceActionError("texture TileSet должен быть ResourcePath")
        size = raw["texture_region_size"]
        if not isinstance(size, list) or len(size) != 2 or any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in size):
            raise ResourceActionError("texture_region_size должен содержать два положительных целых")
        tiles = raw["tiles"]
        if not isinstance(tiles, list) or not (1 <= len(tiles) <= 512):
            raise ResourceActionError("tiles должен содержать от 1 до 512 координат")
        normalized_tiles = []
        seen = set()
        for tile in tiles:
            if not isinstance(tile, list) or len(tile) != 2 or any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in tile):
                raise ResourceActionError("Координата TileSet должна содержать два неотрицательных целых")
            pair = tuple(tile)
            if pair in seen:
                raise ResourceActionError("Координаты TileSet не должны повторяться")
            seen.add(pair)
            normalized_tiles.append(list(pair))
        return {"op": op, "source_id": source_id, "texture": texture,
                "texture_region_size": size, "tiles": normalized_tiles}
    raise ResourceActionError("Неизвестная операция ресурса: %s" % op)


def normalize_action(project_root, action, allow_addons=False, require_exists=True):
    _exact(action, ("action", "resource", "operations"), ("wait_for_import", "summary"))
    if action.get("action") != "edit_resource":
        raise ResourceActionError("Ожидалось action=edit_resource")
    if require_exists:
        resource, absolute = _path(project_root, action["resource"], "resource", (".tres",), allow_addons)
    else:
        raw_resource = action["resource"]
        if not isinstance(raw_resource, str) or not raw_resource.startswith("res://") or not raw_resource.lower().endswith(".tres"):
            raise ResourceActionError("resource должен быть путём res://*.tres")
        absolute = _resolve_safe_path(project_root, raw_resource)
        resource = "res://" + os.path.relpath(absolute, project_root).replace("\\", "/")
        if not allow_addons and resource.lower().startswith("res://addons/"):
            raise ResourceActionError("Пути addons требуют явного намерения")
    raw_operations = action["operations"]
    if not isinstance(raw_operations, list) or not (1 <= len(raw_operations) <= MAX_OPERATIONS):
        raise ResourceActionError("operations должен содержать от 1 до %d операций" % MAX_OPERATIONS)
    imports = action.get("wait_for_import") or []
    if not isinstance(imports, list) or len(imports) > 32:
        raise ResourceActionError("wait_for_import должен быть массивом до 32 путей")
    normalized_imports = []
    for item in imports:
        path, _ = _path(project_root, item, "wait_for_import", allow_addons=allow_addons)
        if path not in normalized_imports:
            normalized_imports.append(path)
    subresource_counter = [0]
    normalized = {"action": "edit_resource", "resource": resource,
                  "operations": [_normalize_operation(project_root, item, allow_addons,
                                                       subresource_counter)
                                  for item in raw_operations]}
    for operation in normalized["operations"]:
        for dependency in _operation_dependencies(operation):
            if dependency not in normalized_imports:
                normalized_imports.append(dependency)
    if normalized_imports:
        normalized["wait_for_import"] = normalized_imports
    summary = action.get("summary")
    if summary is not None:
        normalized_summary = _text(summary, "summary", 500).strip()
        if normalized_summary:
            normalized["summary"] = normalized_summary
    return normalized, absolute


def _operation_dependencies(value):
    """Return every external resource path that affects deterministic execution."""
    result = []

    def walk(item):
        if isinstance(item, dict):
            if item.get("type") == "ResourcePath" and isinstance(item.get("value"), str):
                result.append(item["value"])
            if item.get("op") == "replace_reference":
                result.extend((item.get("old"), item.get("new")))
            for nested in item.values():
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    walk(value)
    return [path for index, path in enumerate(result)
            if isinstance(path, str) and path not in result[:index]]


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
            "resource": normalized["resource"], "target": normalized["resource"],
            "action_digest": canonical_digest(normalized),
            "before_hash": file_sha256(absolute), "state": "preview"}


def public_prepared(prepared):
    return {"action_id": prepared["action_id"], "action_digest": prepared["action_digest"],
            "expected_resource_hash": prepared["before_hash"], "prepare_in_editor": True}


def operation_summary(action):
    labels = {"set_property": "изменить свойство", "replace_reference": "заменить ссылку",
              "animation_add_value_track": "добавить трек Animation",
              "sprite_frames_add_animation": "добавить анимацию SpriteFrames",
              "theme_set_item": "изменить Theme", "tileset_add_atlas_source": "добавить atlas TileSet"}
    return ["%d. %s" % (index, labels.get(item["op"], item["op"]))
            for index, item in enumerate(action.get("operations") or [], 1)]
