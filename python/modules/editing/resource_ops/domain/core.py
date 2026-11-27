"""Native resource schema over immutable path facts; no filesystem or transformer."""
import hashlib
import math
import re

from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel
from python.kernel.write_plan import canonical_json

from .variants import normalize_variant

MAX_OPERATIONS = 20
POLICY_MESSAGE = "Ресурсы аддонов разрешены только по явному запросу и текущей политике доступа"
_MEMBER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_THEME_TYPES = {"color": {"Color"}, "constant": {"int"}, "font_size": {"int"},
                "font": {"ResourcePath", "NewSubresource"}, "icon": {"ResourcePath", "NewSubresource"},
                "stylebox": {"ResourcePath", "NewSubresource"}}


def _exact(value, required, optional=()):
    if not isinstance(value, dict):
        raise AppError("invalid_input", "Операция ресурса должна быть JSON-объектом")
    missing = set(required) - set(value)
    unknown = set(value) - set(required) - set(optional)
    if missing:
        raise AppError("invalid_input", "Не хватает полей: %s" % ", ".join(sorted(missing)))
    if unknown:
        raise AppError("invalid_input", "Неизвестные поля: %s" % ", ".join(sorted(unknown)))


def _text(value, field, limit=500, allow_empty=False):
    if not isinstance(value, str) or len(value) > limit or (not allow_empty and not value):
        raise AppError("invalid_input", "%s должен быть строкой до %d символов" % (field, limit))
    return value


def _number(value, field, minimum=None, maximum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise AppError("invalid_input", "%s должен быть конечным числом" % field)
    result = float(value)
    if positive and result <= 0:
        raise AppError("invalid_input", "%s должен быть положительным" % field)
    if minimum is not None and result < minimum or maximum is not None and result > maximum:
        raise AppError("invalid_input", "%s вне допустимого диапазона" % field)
    return result


def _fact(paths, path):
    rel = normalize_rel(path[6:])
    return paths.get(path, next((v for k, v in paths.items() if k.casefold() == path.casefold()),
                               {"relative": rel, "contained": rel is not None, "is_file": False}))


def allowed(fact):
    rel = (fact.get("relative") or "").casefold()
    return bool(fact.get("contained") and rel and rel.split("/")[0] not in
                ("addons", ".agent_history") and rel != "project.godot")


def _path(paths, value, field, extensions=None):
    path = _text(value, field).replace("\\", "/")
    if not path.startswith("res://"):
        raise AppError("invalid_input", "%s должен быть res:// путём" % field)
    fact = _fact(paths, path)
    if not allowed(fact):
        raise AppError("denied", POLICY_MESSAGE)
    if extensions and not path.lower().endswith(tuple(extensions)):
        raise AppError("invalid_input", "%s имеет неподдерживаемое расширение" % field)
    if not fact["is_file"]:
        raise AppError("not_found", "Ресурс не найден: %s" % path)
    return path, fact["relative"]


def _target(value):
    if not isinstance(value, list) or len(value) > 8:
        raise AppError("invalid_input", "target должен быть массивом до 8 свойств")
    result = []
    for item in value:
        name = _text(item, "target", 160)
        if not _MEMBER_RE.match(name):
            raise AppError("invalid_input", "target содержит недопустимое имя свойства")
        result.append(name)
    return result


def _tagged(paths, value, depth=0, counter=None):
    if not isinstance(value, dict):
        raise AppError("invalid_input", "value должен быть tagged JSON-объектом")
    kind = value.get("type")
    if kind == "ResourcePath":
        _exact(value, ("type", "value"))
        path, _ = _path(paths, value["value"], "ResourcePath")
        return {"type": kind, "value": path}
    if kind == "NewSubresource":
        _exact(value, ("type", "class"), ("properties",))
        if depth >= 4:
            raise AppError("invalid_input", "NewSubresource глубже 4 уровней запрещён")
        cls = _text(value["class"], "class", 120)
        if not _MEMBER_RE.match(cls):
            raise AppError("invalid_input", "Недопустимый класс NewSubresource")
        properties = value.get("properties") or []
        if not isinstance(properties, list) or len(properties) > 32:
            raise AppError("invalid_input", "properties NewSubresource должен быть массивом до 32 элементов")
        counter = counter if counter is not None else [0]
        counter[0] += 1
        if counter[0] > 32:
            raise AppError("invalid_input", "Одно действие не может создавать более 32 subresource")
        normalized, seen = [], set()
        for item in properties:
            _exact(item, ("property", "value"))
            prop = _text(item["property"], "property", 160)
            if not _MEMBER_RE.match(prop) or prop in seen or prop in ("resource_path", "resource_name", "script"):
                raise AppError("invalid_input", "Недопустимое или повторное свойство NewSubresource: %s" % prop)
            seen.add(prop)
            normalized.append({"property": prop, "value": _tagged(paths, item["value"], depth + 1, counter)})
        return {"type": kind, "class": cls, "properties": normalized}
    return normalize_variant(value)


def _normalize_operation(paths, raw, subresource_counter=None):
    if not isinstance(raw, dict):
        raise AppError("invalid_input", "Каждая операция должна быть объектом")
    op = raw.get("op")
    if op == "set_property":
        _exact(raw, ("op", "target", "property", "value"))
        prop = _text(raw["property"], "property", 160)
        if not _MEMBER_RE.match(prop):
            raise AppError("invalid_input", "Недопустимое имя свойства")
        return {"op": op, "target": _target(raw["target"]), "property": prop,
                "value": _tagged(paths, raw["value"], counter=subresource_counter)}
    if op == "replace_reference":
        _exact(raw, ("op", "target", "old", "new", "expected_count"))
        old, _ = _path(paths, raw["old"], "old")
        new, _ = _path(paths, raw["new"], "new")
        count = raw["expected_count"]
        if isinstance(count, bool) or not isinstance(count, int) or not (1 <= count <= 10000):
            raise AppError("invalid_input", "expected_count должен быть целым числом 1..10000")
        if old == new:
            raise AppError("invalid_input", "old и new должны различаться")
        return {"op": op, "target": _target(raw["target"]), "old": old, "new": new, "expected_count": count}
    if op == "animation_add_value_track":
        _exact(raw, ("op", "path", "keys"), ("interpolation", "update_mode"))
        keys = raw["keys"]
        if not isinstance(keys, list) or not (1 <= len(keys) <= 512):
            raise AppError("invalid_input", "keys должен содержать от 1 до 512 ключей")
        result, previous = [], -1.0
        for key in keys:
            _exact(key, ("time", "value"), ("transition",))
            timestamp = _number(key["time"], "time", minimum=0)
            if timestamp <= previous:
                raise AppError("invalid_input", "Время ключей Animation должно строго возрастать")
            previous = timestamp
            result.append({"time": timestamp, "value": _tagged(paths, key["value"], counter=subresource_counter),
                           "transition": _number(key.get("transition", 1.0), "transition", positive=True)})
        interpolation, update_mode = raw.get("interpolation", "linear"), raw.get("update_mode", "continuous")
        if interpolation not in {"nearest", "linear", "cubic"} or update_mode not in {"continuous", "discrete", "capture"}:
            raise AppError("invalid_input", "Неподдерживаемый режим Animation")
        return {"op": op, "path": _text(raw["path"], "path", 500), "keys": result,
                "interpolation": interpolation, "update_mode": update_mode}
    if op == "sprite_frames_add_animation":
        _exact(raw, ("op", "name", "fps", "loop", "frames"))
        frames = raw["frames"]
        if not isinstance(frames, list) or not (1 <= len(frames) <= 256):
            raise AppError("invalid_input", "frames должен содержать от 1 до 256 кадров")
        result = []
        for frame in frames:
            _exact(frame, ("texture",), ("duration",))
            texture = _tagged(paths, frame["texture"])
            if texture.get("type") != "ResourcePath":
                raise AppError("invalid_input", "texture кадра должен быть ResourcePath")
            result.append({"texture": texture, "duration": _number(frame.get("duration", 1.0), "duration", positive=True)})
        if not isinstance(raw["loop"], bool):
            raise AppError("invalid_input", "loop должен быть bool")
        return {"op": op, "name": _text(raw["name"], "name", 120), "fps": _number(raw["fps"], "fps", positive=True),
                "loop": raw["loop"], "frames": result}
    if op == "theme_set_item":
        _exact(raw, ("op", "data_type", "theme_type", "name", "value"), ("overwrite",))
        data_type = raw["data_type"]
        if data_type not in _THEME_TYPES:
            raise AppError("invalid_input", "Неподдерживаемый тип Theme item")
        if "overwrite" in raw and not isinstance(raw["overwrite"], bool):
            raise AppError("invalid_input", "overwrite должен быть bool")
        tagged = _tagged(paths, raw["value"], counter=subresource_counter)
        if tagged.get("type") not in _THEME_TYPES[data_type]:
            raise AppError("invalid_input", "Тип value не подходит для Theme item %s" % data_type)
        return {"op": op, "data_type": data_type, "theme_type": _text(raw["theme_type"], "theme_type", 120),
                "name": _text(raw["name"], "name", 120), "overwrite": raw.get("overwrite", False), "value": tagged}
    if op == "tileset_add_atlas_source":
        _exact(raw, ("op", "source_id", "texture", "texture_region_size", "tiles"))
        source_id = raw["source_id"]
        if isinstance(source_id, bool) or not isinstance(source_id, int) or source_id < 0:
            raise AppError("invalid_input", "source_id должен быть неотрицательным целым")
        texture = _tagged(paths, raw["texture"])
        if texture.get("type") != "ResourcePath":
            raise AppError("invalid_input", "texture TileSet должен быть ResourcePath")
        size = raw["texture_region_size"]
        if not isinstance(size, list) or len(size) != 2 or any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in size):
            raise AppError("invalid_input", "texture_region_size должен содержать два положительных целых")
        tiles = raw["tiles"]
        if not isinstance(tiles, list) or not (1 <= len(tiles) <= 512):
            raise AppError("invalid_input", "tiles должен содержать от 1 до 512 координат")
        result, seen = [], set()
        for tile in tiles:
            if not isinstance(tile, list) or len(tile) != 2 or any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in tile):
                raise AppError("invalid_input", "Координата TileSet должна содержать два неотрицательных целых")
            pair = tuple(tile)
            if pair in seen:
                raise AppError("invalid_input", "Координаты TileSet не должны повторяться")
            seen.add(pair)
            result.append(list(pair))
        return {"op": op, "source_id": source_id, "texture": texture, "texture_region_size": size, "tiles": result}
    raise AppError("invalid_input", "Неизвестная операция ресурса: %s" % op)


def normalize_action(paths, action, allow_addons=False, require_exists=True, allow_self_edit=False, addon_dir=None):
    _exact(action, ("action", "resource", "operations"), ("wait_for_import", "summary"))
    if action.get("action") != "edit_resource":
        raise AppError("invalid_input", "Ожидалось action=edit_resource")
    if require_exists:
        resource, rel = _path(paths, action["resource"], "resource", (".tres",))
    else:
        raw = action["resource"]
        if not isinstance(raw, str) or not raw.startswith("res://") or not raw.lower().endswith(".tres"):
            raise AppError("invalid_input", "resource должен быть путём res://*.tres")
        fact = _fact(paths, raw.replace("\\", "/"))
        if not fact["contained"]:
            raise AppError("denied", "Путь вне проекта отклонен: %s" % raw)
        if fact["relative"].casefold().split("/")[0] == ".agent_history":
            raise AppError("denied", "Доступ к служебной папке истории запрещён.")
        if not allowed(fact):
            raise AppError("denied", POLICY_MESSAGE)
        rel, resource = fact["relative"], "res://" + fact["relative"]
    operations = action["operations"]
    if not isinstance(operations, list) or not (1 <= len(operations) <= MAX_OPERATIONS):
        raise AppError("invalid_input", "operations должен содержать от 1 до %d операций" % MAX_OPERATIONS)
    imports = action.get("wait_for_import") or []
    if not isinstance(imports, list) or len(imports) > 32:
        raise AppError("invalid_input", "wait_for_import должен быть массивом до 32 путей")
    normalized_imports = []
    for item in imports:
        path, _ = _path(paths, item, "wait_for_import")
        if path not in normalized_imports:
            normalized_imports.append(path)
    counter = [0]
    normalized = {"action": "edit_resource", "resource": resource,
                  "operations": [_normalize_operation(paths, item, counter) for item in operations]}
    for operation in normalized["operations"]:
        for dependency in _operation_dependencies(operation):
            if dependency not in normalized_imports:
                normalized_imports.append(dependency)
    if normalized_imports:
        normalized["wait_for_import"] = normalized_imports
    summary = action.get("summary")
    if summary is not None:
        text = _text(summary, "summary", 500).strip()
        if text:
            normalized["summary"] = text
    return normalized, rel


def _operation_dependencies(value):
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
    return [path for i, path in enumerate(result) if isinstance(path, str) and path not in result[:i]]


def canonical_digest(action):
    return hashlib.sha256(canonical_json(action).encode("utf-8")).hexdigest()


def public_prepared(prepared):
    return {"action_id": prepared["action_id"], "action_digest": prepared["action_digest"],
            "expected_resource_hash": prepared["before_hash"], "prepare_in_editor": True}


def operation_summary(action):
    labels = {"set_property": "изменить свойство", "replace_reference": "заменить ссылку",
              "animation_add_value_track": "добавить трек Animation", "sprite_frames_add_animation": "добавить анимацию SpriteFrames",
              "theme_set_item": "изменить Theme", "tileset_add_atlas_source": "добавить atlas TileSet"}
    return ["%d. %s" % (i, labels.get(item["op"], item["op"])) for i, item in enumerate(action.get("operations") or [], 1)]
