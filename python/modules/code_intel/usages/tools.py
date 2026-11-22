"""modules/code_intel/usages/tools.py - дескрипторы двух механик (R-05, ADR-0006).

`usages` — где символ объявлен и где используется. `analyze_rename` — тот же
поиск плюс затронутые файлы и риски переименования. Оба read-only и оба в одном
модуле: второй — обёртка над первым (`docs/parity.md`, строка 23).

Источник правды: `contract/capabilities/<tool>.json` генерируется из этого
файла (`python tools/gen_contract.py --write`), руками не правится.
"""

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
    "description": "locator объявления: `res://path.gd:line` или `res://path.gd:line:column`.",
}
USAGE_ITEM = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "res:// путь файла."},
        "line": {"type": "integer", "description": "Строка (1-based)."},
        "column": {"type": "integer", "description": "Колонка (1-based)."},
        "link": {"type": "string",
                 "description": "declaration | call | member | identifier | type | string"},
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
                    "description": "locator как его передал клиент."},
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
        "Ищет, где объявлен символ и где он ещё используется. Вход — locator "
        "объявления `res://scripts/player.gd:14` (строка, по желанию колонка), "
        "вид символа (`function`, `signal`, `variable`, `const`, `enum`, "
        "`enum_member`, `class_name`) и его имя. Отдаёт места с координатами, "
        "типом связи (`declaration`, `call`, `member`, `identifier`, `type`, "
        "`string`) и уверенностью: `proven` — связь доказана, `probable` — "
        "вероятна (в `note` причина, чего не хватает, чаще всего аннотации "
        "типа), `dynamic` — ссылка по строковому литералу. Ничего не меняет: "
        "переименование — отдельный инструмент analyze_rename."
    ),
    args={
        "type": "object",
        "properties": {
            "kind": KIND_ARG,
            "old_name": OLD_NAME_ARG,
            "declaration": DECLARATION_ARG,
            "new_name": {
                "type": "string",
                "description": ("Необязательное новое имя: эталон принимает его и "
                                "возвращает эхом, поиск от него не зависит."),
            },
        },
        "required": ["kind", "old_name", "declaration"],
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
                       "description": "Файлы с доказанными ссылками: sorted, без дублей."},
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
        "Предпросмотр переименования: что и где изменится. Вход — те же locator "
        "объявления, вид символа, старое и НОВОЕ имя, плюс `mode` (`strict` по "
        "умолчанию) и `allow_unverified`. Отдаёт тот же список мест, что "
        "`usages`, и дополнительно `affected_paths` (файлы с доказанными "
        "ссылками), `risks` (строки `path:line [link, confidence] — причина` для "
        "вероятных и динамических ссылок) и разобранный locator. Ничего не пишет "
        "и ничего не применяет: это ответ на вопрос «что затронет правка». Строки "
        "в risks — места, которые переименование само не покроет."
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
            "mode": {
                "type": "string", "enum": ["strict", "probable"], "default": "strict",
                "description": "Стратегия эталона: в предпросмотре — эхо запроса.",
            },
            "allow_unverified": {
                "type": "boolean", "default": False,
                "description": "В предпросмотре — эхо и флаг отчёта.",
            },
        },
        "required": ["kind", "old_name", "new_name", "declaration"],
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

