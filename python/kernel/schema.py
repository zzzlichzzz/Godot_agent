"""kernel/schema.py - минимальная проверка JSON-схем (stdlib, без зависимостей).

Поддерживается ровно то, что нужно контрактам: `type`, `properties`, `required`,
`additionalProperties`, `items`, `enum`, `minimum`/`maximum`,
`minLength`/`maxLength`, `minItems`/`maxItems`. `type` может быть списком
(`["string", "null"]`): значение подходит, если подходит хотя бы под один элемент
списка. Незнакомые *ключи* схемы игнорируются: валидатор не обязан быть полным
JSON Schema — он обязан не пропускать мусор в домен.

Неизвестный *тип* (опечатка `"date"`) — отказ, а не пропуск: `validate` считает
такое значение невалидным (fail closed — лучше отказать, чем принять
непроверенное), а `unknown_schema_types` перечисляет места схемы с неизвестным
типом, чтобы опечатка ловилась в контракте (`tools/gen_contract.py --check`), а не
в первом ответе моста редактора.

`validate` тотальна: мусорная схема (`type: 5`, `items: "x"`, `required: "path"`,
`properties` не-dict) даёт проблемы или пустой список, но не исключение.

`type: null` — «тип не задан», а не отказ: `None` в `type` не проверяется
вовсе (так же и в `unknown_schema_types`). Неизвестный тип — любое не-`null`
значение вне семи имён (`"date"`, `5`, `{"x": 1}`) — оно и даёт отказ.
"""


def _is_integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_null(value):
    return value is None


#: Поддерживаемые типы: имя → проверка. Ключи только строки, поэтому
#: `_TYPES.get` не может получить нехэшируемое значение: union-список
#: разбирается в `_type_ok` до обращения к словарю.
_TYPES = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "boolean": lambda value: isinstance(value, bool),
    "integer": _is_integer,
    "number": _is_number,
    "null": _is_null,
}


def _type_ok(value, expected):
    """Тип значения по имени или по union-списку; неизвестный тип — отказ."""
    if isinstance(expected, (list, tuple)):
        return any(_type_ok(value, item) for item in expected)
    if not isinstance(expected, str):
        return False
    checker = _TYPES.get(expected)
    if checker is None:
        return False
    return checker(value)


def validate(instance, schema):
    """Список человеческих проблем; пустой список — вход валиден."""
    problems = []
    _check(instance, schema, "(аргументы)", problems)
    return problems


def unknown_schema_types(schema, path="(аргументы)"):
    """Места схемы с неизвестным типом: `["<путь>: неизвестный тип 'date'"]`.

    Обход идёт по тому, что реально читает `_check`: `type` (имя или union),
    `items` и `properties`. Мусор вместо схемы пропускается так же, как в
    валидаторе: функция не бросает исключений и ничего не проверяет по данным.
    """
    found = []
    _walk_types(schema, path, found)
    return found


def _walk_types(schema, path, found):
    if not isinstance(schema, dict):
        return
    expected = schema.get("type")
    if isinstance(expected, (list, tuple)):
        for item in expected:
            _name_unknown_type(item, path, found)
    elif expected is not None:
        _name_unknown_type(expected, path, found)
    items = schema.get("items")
    if isinstance(items, dict):
        _walk_types(items, path + "[]", found)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for key, item in properties.items():
            _walk_types(item, "%s.%s" % (path, key), found)


def _name_unknown_type(expected, path, found):
    if isinstance(expected, str) and expected in _TYPES:
        return
    found.append("%s: неизвестный тип %r" % (path, expected))


def _check(value, schema, path, problems):
    if not isinstance(schema, dict):
        return
    expected = schema.get("type")
    if expected is not None and not _type_ok(value, expected):
        problems.append("%s: ожидался %s" % (path, expected))
        return
    if "enum" in schema and value not in schema["enum"]:
        problems.append("%s: допустимые значения %s" % (path, schema["enum"]))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            problems.append("%s: короче %d символов" % (path, schema["minLength"]))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append("%s: длиннее %d символов" % (path, schema["maxLength"]))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append("%s: меньше %s" % (path, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            problems.append("%s: больше %s" % (path, schema["maximum"]))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append("%s: меньше %d элементов" % (path, schema["minItems"]))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append("%s: больше %d элементов" % (path, schema["maxItems"]))
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                _check(item, items, "%s[%d]" % (path, index), problems)
    if isinstance(value, dict):
        declared = schema.get("properties")
        properties = declared if isinstance(declared, dict) else {}
        required = schema.get("required")
        for key in required if isinstance(required, (list, tuple)) else ():
            if key not in value:
                problems.append("%s: нет обязательного поля %r" % (path, key))
        for key, item in value.items():
            if key in properties:
                _check(item, properties[key], "%s.%s" % (path, key), problems)
            elif schema.get("additionalProperties") is False:
                problems.append("%s: неизвестное поле %r" % (path, key))


