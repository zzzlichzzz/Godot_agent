"""Read-only usage and rename-analysis contracts (source for gen_contract.py)."""

from python.kernel.tool_spec import ToolSpec

KIND_ARG = {
    "type": "string",
    "enum": ["class_name", "function", "signal", "variable", "const", "enum",
             "enum_member"],
    "description": "Вид символа — как в объявлении.",
}
OLD_NAME_ARG = {"type": "string", "description": "Имя символа (идентификатор GDScript)."}
DECLARATION_ARG = {
    "type": "string",
    "description": "Точный locator `res://path.gd:line[:column]`. Без него требуется одно совпадение по виду и имени в видимых скриптах.",
}
DECLARATION_PATH_ARG = {"type": "string", "minLength": 7, "maxLength": 1024,
                        "description": "Ограничить поиск объявления одним res:// скриптом вместо точного locator."}
USAGE_ITEM = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "res:// путь файла."},
        "line": {"type": "integer", "description": "Строка (1-based)."},
        "column": {"type": "integer", "description": "Колонка (1-based)."},
        "link": {"type": "string",
                 "description": "declaration | call | member | identifier | type | string | callable | signal | scene_connection"},
        "confidence": {"type": "string", "description": "proven | probable | dynamic"},
        "note": {"type": ["string", "null"],
                 "description": "Причина для probable/dynamic; null для proven."},
    },
    "required": ["path", "line", "column", "link", "confidence", "note"],
    "additionalProperties": False,
}
USAGE_FIELDS = {
    "kind": {"type": "string"}, "old_name": {"type": "string"},
    "new_name": {"type": "string"},
    "declaration": {"type": "string",
                     "description": "Переданный или найденный точный locator."},
    "usages": {"type": "array", "items": USAGE_ITEM},
    "by_link": {"type": "object", "description": "Счётчик мест по типу связи."},
    "proven_count": {"type": "integer"}, "probable_count": {"type": "integer"},
    "dynamic_count": {"type": "integer"},
}
USAGE_REQUIRED = ["kind", "old_name", "new_name", "declaration", "usages",
                  "by_link", "proven_count", "probable_count", "dynamic_count"]

USAGES = ToolSpec(
    name="usages",
    description=(
        "Ищет, где объявлен символ и где он используется. Вход — вид символа "
        "(`function`, `signal`, `variable`, `const`, `enum`, "
        "`enum_member`, `class_name`) и его имя. Отдаёт места с координатами, "
        "типом связи (`declaration`, `call`, `member`, `identifier`, `type`, "
        "`string`, `callable`, `signal`, `scene_connection`) и уверенностью: `proven` — связь доказана, `probable` — "
        "вероятна (в `note` причина, чего не хватает, чаще всего аннотации "
        "типа), `dynamic` — ссылка по строковому литералу. Ничего не меняет: "
        "можно уточнить объявление через declaration или declaration_path."
    ),
    args={
        "type": "object",
        "properties": {
            "kind": KIND_ARG,
            "old_name": OLD_NAME_ARG,
            "declaration": DECLARATION_ARG,
            "declaration_path": DECLARATION_PATH_ARG,
            "new_name": {
                "type": "string",
                "description": ("Необязательное новое имя: эталон принимает его и "
                                "возвращает эхом, поиск от него не зависит."),
            },
        },
        "required": ["kind", "old_name"],
        "additionalProperties": False,
    },
    result={"type": "object", "properties": USAGE_FIELDS,
            "required": USAGE_REQUIRED, "additionalProperties": False},
    effects="read",
    idempotent=True,
    errors=("invalid_input", "not_found", "denied"),
    availability="*",
    cost="heavy",
)

RENAME_FIELDS = dict(USAGE_FIELDS)
RENAME_FIELDS.update({
    "declaration_path": {"type": "string", "description": "Файл объявления из locator'а."},
    "declaration_line": {"type": "integer", "description": "Строка объявления из locator'а."},
    "allow_unverified": {"type": "boolean"},
    "mode": {"type": "string", "description": "strict | probable (эхо запроса)."},
    "affected_paths": {"type": "array", "items": {"type": "string"},
                       "description": "Файлы с доказанными ссылками и, при allow_unverified, с вероятными: sorted, без дублей."},
    "risks": {"type": "array", "items": {"type": "string"},
              "description": "Строки `path:line [link, confidence] — note`."},
})
RENAME_REQUIRED = ["kind", "old_name", "new_name", "declaration",
                   "allow_unverified", "mode", "usages", "affected_paths",
                   "risks", "by_link", "proven_count", "probable_count",
                   "dynamic_count", "declaration_path", "declaration_line"]

ANALYZE_RENAME = ToolSpec(
    name="analyze_rename",
    description=(
        "Предпросмотр переименования: что и где изменится. Вход — вид символа, "
        "старое и НОВОЕ имя, необязательный locator, плюс `mode` (`strict` по "
        "умолчанию) и `allow_unverified`. Отдаёт тот же список мест, что "
        "`usages`, и дополнительно `affected_paths` (доказанные места и, при "
        "allow_unverified, вероятные), `risks` (строки `path:line [link, confidence] — причина` для "
        "вероятных и динамических ссылок) и разобранный locator. Ничего не пишет "
        "и ничего не применяет. Риски требуют проверки, даже если место включено в план."
    ),
    args={
        "type": "object",
        "properties": {
            "kind": KIND_ARG,
            "old_name": OLD_NAME_ARG,
            "new_name": {
                "type": "string",
                "minLength": 1,
                "description": "Новое имя символа (идентификатор GDScript), обязательно.",
            },
            "declaration": DECLARATION_ARG,
            "declaration_path": DECLARATION_PATH_ARG,
            "mode": {
                "type": "string", "enum": ["strict", "probable"], "default": "strict",
                "description": "Стратегия эталона: в предпросмотре — эхо запроса.",
            },
            "allow_unverified": {
                "type": "boolean", "default": False,
                "description": "Включить файлы с вероятными ссылками в affected_paths, сохранив исходную уверенность.",
            },
        },
        "required": ["kind", "old_name", "new_name"],
        "additionalProperties": False,
    },
    result={"type": "object", "properties": RENAME_FIELDS,
            "required": RENAME_REQUIRED, "additionalProperties": False},
    effects="read",
    idempotent=True,
    errors=("invalid_input", "not_found", "denied"),
    availability="*",
    cost="heavy",
)

TOOLS = (USAGES, ANALYZE_RENAME)

