"""Native scalar/vector Variant rules, not a foreign scene-domain dependency."""
import math
import re

from python.kernel.errors import AppError

ARITY = {"Vector2": 2, "Vector2i": 2, "Vector3": 3, "Vector3i": 3, "Color": 4}
SCALARS = {"Nil", "bool", "int", "float", "String", "StringName", "NodePath"}


def _fail(text):
    raise AppError("invalid_input", text)


def _node_path(value):
    if not isinstance(value, str) or not value or len(value) > 500:
        _fail("value.value должен быть непустой строкой до 500 символов")
    path = value.replace("\\", "/")
    if path == ".":
        return path
    if path.startswith("/") or path.endswith("/") or "//" in path:
        _fail("value.value должен быть путём относительно корня сцены")
    parts = path.split("/")
    if any(part in ("", ".", "..") or part.startswith("%") for part in parts):
        _fail("value.value содержит запрещённый сегмент")
    if any(not re.match(r'^[^./:@"\\]+$', part) for part in parts):
        _fail("value.value содержит недопустимое имя узла")
    return path


def normalize_variant(value):
    missing = {"type", "value"} - set(value)
    unknown = set(value) - {"type", "value"}
    if missing:
        _fail("Не хватает полей: %s" % ", ".join(sorted(missing)))
    if unknown:
        _fail("Неизвестные поля: %s" % ", ".join(sorted(unknown)))
    kind, raw = value["type"], value["value"]
    if not isinstance(kind, str) or not kind or len(kind) > 30:
        _fail("value.type должен быть непустой строкой до 30 символов")
    if kind not in SCALARS and kind not in ARITY:
        _fail("Неподдерживаемый тип свойства: %s" % kind)
    if kind == "Nil":
        if raw is not None:
            _fail("Nil должен иметь value=null")
    elif kind == "bool":
        if not isinstance(raw, bool):
            _fail("bool требует true/false")
    elif kind == "int":
        if isinstance(raw, bool) or not isinstance(raw, int):
            _fail("int требует целое число")
    elif kind == "float":
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
            _fail("float требует конечное число")
        raw = float(raw)
    elif kind in ("String", "StringName"):
        if not isinstance(raw, str) or len(raw) > 4000:
            _fail("%s требует строку до 4000 символов" % kind)
    elif kind == "NodePath":
        raw = _node_path(raw)
    else:
        arity = ARITY[kind]
        if not isinstance(raw, list) or len(raw) != arity:
            _fail("%s требует массив из %d чисел" % (kind, arity))
        converted = []
        for item in raw:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)):
                _fail("%s содержит нечисловое или бесконечное значение" % kind)
            converted.append(int(item) if kind.endswith("i") else float(item))
        raw = converted
    return {"type": kind, "value": raw}
