"""modules/editing/scene_ops/domain/core.py - батч правок сцены: нормировка и проверки.

Домен ничего не пишет и не знает про Godot (R-14): он собирает канонический
запрос, считает `plan_digest` и принимает ответ моста только если тот сходится с
запросом — ревизия, отпечаток, квитанции, рост ревизии после батча. Любое
расхождение — отказ, а не частичный результат: «применилось наполовину» дороже
честной ошибки. Канонический JSON собран здесь же: `domain/` не имеет права
импортировать `json` (правило «в домене нет IO», R-11), а отпечаток должен
совпадать с `JSON.stringify` в `scene_executor.gd` побайтово.
"""

import hashlib

from python.kernel.errors import AppError
from python.kernel.schema import validate

#: Примитивы моста части B.
PLAN = "editor_scene_plan"
APPLY = "editor_scene_apply"
#: Ровно эти операции; неизвестная рушит весь батч.
OPS = ("add_node", "set_property", "attach_script", "connect_signal")
FIELDS = {"add_node": ("parent", "name", "type"),
          "set_property": ("node", "property"),
          "attach_script": ("node", "script"),
          "connect_signal": ("from", "signal", "to", "method")}
MAX_OPERATIONS = 64
MAX_VALUE_BYTES = 4096


def _string(text):
    """Строка в каноническом JSON: как `json.dumps(ensure_ascii=False)`."""
    out = ['"']
    for char in text:
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        elif char == "\b":
            out.append("\\b")
        elif char == "\f":
            out.append("\\f")
        elif ord(char) < 0x20:
            out.append("\\u%04x" % ord(char))
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _number(value):
    """Число: `repr` для float (как `json.dumps`), особые значения — как в JSON."""
    if value != value:
        return "NaN"
    if value in (float("inf"), float("-inf")):
        return "Infinity" if value > 0 else "-Infinity"
    return repr(value)


def canon(value):
    """Канонический JSON: порядок ключей не значим, порядок элементов — значим.

    Ровно то, что печатает `json.dumps(value, sort_keys=True,
    separators=(",", ":"), ensure_ascii=False)`; равенство закреплено тестом,
    потому что `domain/` не может импортировать `json` (нет IO в домене).
    """
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, int):
        return "%d" % value
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canon(item) for item in value) + "]"
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                _deny("ключ операции должен быть строкой, получено %r" % (key,))
        items = sorted(value.items())
        return "{" + ",".join(_string(key) + ":" + canon(item)
                              for key, item in items) + "}"
    _deny("значение %r не сериализуется в JSON" % (type(value).__name__,))


def digest_of(scene, revision, operations):
    """Отпечаток запроса: то же правило считает GDScript (`scene_executor.gd`)."""
    lines = ["scene=" + scene, "revision=%d" % revision]
    lines.extend(canon(op) for op in operations)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _deny(message, hint="", reason="invalid_request"):
    raise AppError("invalid_input", message, hint=hint,
                   details={"reason": reason, "problems": [message]})


def _check_operations(operations):
    if not isinstance(operations, list):
        _deny("operations должен быть массивом")
    if not 1 <= len(operations) <= MAX_OPERATIONS:
        _deny("операций %d, допустимо 1…%d" % (len(operations), MAX_OPERATIONS))
    for index, op in enumerate(operations):
        if not isinstance(op, dict):
            _deny("операция %d — не объект" % (index,))
        name = op.get("op")
        if name not in OPS:
            _deny("операция %d: неизвестное op %r" % (index, name),
                  hint="допустимы %s" % (", ".join(OPS),), reason="unknown_operation")
        for field in FIELDS[name]:
            value = op.get(field)
            if isinstance(value, str) and (value.strip() or
                                           (name == "add_node" and field == "parent")):
                continue
            _deny("операция %d (%s): поле %s должно быть непустой строкой"
                  % (index, name, field))
        if name == "set_property" and "value" not in op:
            _deny("операция %d (set_property): нет поля value" % (index,))
        if "value" in op and len(canon(op["value"]).encode("utf-8")) > MAX_VALUE_BYTES:
            _deny("операция %d: значение больше %d Б" % (index, MAX_VALUE_BYTES))


def build_request(args):
    """Нормализованный запрос: все проверки до сети, порядок операций сохраняется."""
    args = dict(args or {})
    scene = args.get("scene")
    if not isinstance(scene, str) or not scene.startswith("res://"):
        _deny("scene должен быть res://…, получено %r" % (scene,))
    revision = args.get("expected_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        _deny("expected_revision должен быть целым >= 0")
    operations = args.get("operations")
    _check_operations(operations)
    request = {"scene": scene, "expected_revision": revision,
               "operations": [dict(op) for op in operations],
               "apply": bool(args.get("apply")), "undo_label": args.get("undo_label"),
               "plan_digest": args.get("plan_digest")}
    request["digest"] = digest_of(scene, revision, request["operations"])
    if request["apply"]:
        digest = request["plan_digest"]
        if not isinstance(digest, str) or digest != request["digest"]:
            raise AppError("stale_plan", "plan_digest не описывает этот батч",
                           hint="сначала план, затем apply с его plan_digest",
                           details={"reason": "stale_plan"})
    return request


def check(verb, result, schema):
    """Ответ моста по схеме примитива: проблема — отказ с путём поля."""
    problems = validate(result, schema)
    if problems:
        raise AppError("engine_down", "ответ моста %r не по схеме" % (verb,),
                       hint="Мост и словарь примитивов разошлись (ADR-0007)",
                       details={"reason": "bad_result", "problems": problems[:3]})
    return result


def _bad(verb, problems, reason="bad_result"):
    raise AppError("engine_down", "ответ моста %r не сходится с запросом" % (verb,),
                   hint="не верьте «применилось»: батч не принят",
                   details={"reason": reason, "problems": list(problems)[:3]})


def plan(client, request):
    """Dry-run: план сверяется с запросом, сцена не меняется."""
    result = check(PLAN, _call(client, PLAN, _wire(request, False)),
                   client.result_schema(PLAN))
    if result["scene"] != request["scene"]:
        _bad(PLAN, ["scene: ответ про другую сцену"])
    if result["revision"] != request["expected_revision"]:
        raise AppError("conflict", "ревизия сцены %d, запрос рассчитывал на %d"
                       % (result["revision"], request["expected_revision"]),
                       hint="перечитайте editor_state и постройте план заново",
                       details={"reason": "revision_mismatch"})
    if result["plan_digest"] != request["digest"]:
        _bad(PLAN, ["plan_digest: мост считает отпечаток иначе"])
    return _shape(request, result, applied=False)


def apply(client, request):
    """Один undo на батч: квитанции покрывают все шаги, ревизия растёт ровно на 1."""
    result = check(APPLY, _call(client, APPLY, _wire(request, True)),
                   client.result_schema(APPLY))
    if result["scene"] != request["scene"]:
        _bad(APPLY, ["scene: ответ про другую сцену"])
    receipts = result.get("receipts") or []
    if len(receipts) != len(request["operations"]):
        _bad(APPLY, ["receipts: %d квитанций на %d операций"
                     % (len(receipts), len(request["operations"]))])
    if not all(bool(item.get("applied")) for item in receipts):
        _bad(APPLY, ["receipts: есть неприменённый шаг"])
    expected_revision = request["expected_revision"] + 1
    if result["applied_revision"] != expected_revision:
        _bad(APPLY, ["applied_revision: %r вместо %d"
                     % (result["applied_revision"], expected_revision)])
    return _shape(request, result, applied=True)


def perform(client, request):
    """План или применение по одному нормализованному запросу."""
    return apply(client, request) if request["apply"] else plan(client, request)


def _wire(request, with_digest):
    payload = {"scene": request["scene"],
               "expected_revision": request["expected_revision"],
               "operations": request["operations"]}
    if with_digest:
        payload["plan_digest"] = request["digest"]
        if request.get("undo_label"):
            payload["undo_label"] = str(request["undo_label"])
    return payload


def _call(client, verb, payload):
    result = client.call(verb, payload)
    if not isinstance(result, dict):
        _bad(verb, ["(ответ): ожидался object"])
    return result


def _shape(request, result, applied):
    return {"applied": applied, "scene": result["scene"],
            "revision": result.get("revision"),
            "applied_revision": result.get("applied_revision"),
            "plan_digest": str(result.get("plan_digest") or request["digest"]),
            "undo_label": result.get("undo_label"),
            "steps": result.get("steps") or [],
            "would_change": result.get("would_change") or [],
            "warnings": result.get("warnings") or [],
            "receipts": result.get("receipts") or [],
            "changes": result.get("changes") or []}
