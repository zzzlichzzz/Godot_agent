"""modules/code_intel/functions/tools.py - дескриптор механики (R-05, ADR-0006).

Имя плоское — `functions`: старые клиенты и промпты продолжают работать, хотя
модуль называется `code_intel.functions`. `card` в схему не входит: карточка
функции — отдельная механика `code_intel.function_card`.

Источник правды: `contract/capabilities/functions.json` генерируется из этого
файла (`python tools/gen_contract.py`) и руками не правится.
"""

from python.kernel.tool_spec import ToolSpec

FUNCTIONS = ToolSpec(
    name="functions",
    description=(
        "Показывает функции GDScript-файла (.gd). Без `names` — режим списка: "
        "имена всех объявленных функций в порядке объявления (включая `_ready`/"
        "`_process` и `static func`, дубли повторяются). С `names` — извлечение: "
        "тело каждой запрошенной функции дословно, с номерами строк (1-based) и "
        "прилегающими сверху `#`-комментариями и `@`-аннотациями; имена, которых "
        "нет, возвращаются в `missing`. Разбор индентационный, не AST: `func`, "
        "объявленный внутри тела другой функции, в `names` виден, но тело по "
        "запросу не извлекается. Файл не меняется. Вызывать, когда нужно понять, "
        "что делает конкретная функция или какие функции есть в скрипте."
    ),
    args={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": ("Путь к скрипту: `res://scripts/player.gd` или "
                                "относительный `scripts/player.gd`."),
            },
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": ("Имена функций для извлечения тел. Пустой список — "
                                "режим списка имён."),
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    result={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "res:// путь файла."},
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Режим списка: имена в порядке объявления.",
            },
            "functions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Имя функции."},
                        "snippet": {"type": "string",
                                    "description": "Строки функции дословно, с комментариями и аннотациями сверху."},
                        "start_line": {"type": "integer", "description": "Первая строка сниппета (1-based)."},
                        "end_line": {"type": "integer", "description": "Последняя непустая строка тела."},
                    },
                    "required": ["name", "start_line", "end_line", "snippet"],
                    "additionalProperties": False,
                },
                "description": "Режим извлечения: найденные функции в порядке запроса.",
            },
            "missing": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Режим извлечения: запрошенные имена, которых нет в файле.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    effects="read",
    idempotent=True,
    errors=("invalid_input", "not_found", "denied"),
    availability="*",
    cost="cheap",
)

TOOLS = (FUNCTIONS,)

