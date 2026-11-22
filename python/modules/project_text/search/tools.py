"""modules/project_text/search/tools.py - дескриптор механики (R-05, ADR-0006).

Источник правды: `contract/capabilities/search.json` генерируется из этого файла
(`python tools/gen_contract.py`) и руками не правится.
"""

from python.kernel.tool_spec import ToolSpec

from .settings import SEARCH_MAX_CONTEXT_LINES, SEARCH_MAX_RESULTS

SEARCH = ToolSpec(
    name="search",
    description=(
        "Ищет литеральную подстроку по текстовым файлам проекта (.gd, .tscn, .tres, "
        ".cfg, .godot, .json, .txt, .md, .gdshader, .shader, .csv). Это не регулярное "
        "выражение: запрос 'func _ready' найдёт только это вхождение. Возвращает "
        "совпадения с путём res://, номером первой строки окна и сниппетом с "
        "контекстом. Аддоны и исходники самого агента скрыты политикой, шумовые "
        "каталоги (.godot, node_modules, __pycache__) не сканируются. Вызывать, когда "
        "нужно найти, где объявлен символ, кто вызывает функцию или где лежит значение."
    ),
    args={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Подстрока для поиска. Пустая строка даёт пустой результат.",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": SEARCH_MAX_RESULTS,
                "default": 30,
                "description": "Сколько совпадений вернуть максимум.",
            },
            "context_lines": {
                "type": "integer",
                "minimum": 0,
                "maximum": SEARCH_MAX_CONTEXT_LINES,
                "default": 2,
                "description": "Сколько строк до и после совпадения включить в сниппет.",
            },
            "exclude_rel_prefixes": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": ("Префиксы относительных путей (например 'addons/'), "
                                "которые пропускаются ДО набора квоты max_results."),
            },
            "case_insensitive": {
                "type": "boolean",
                "default": False,
                "description": "Сравнение без учёта регистра.",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    result={
        "type": "object",
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "res:// путь файла."},
                        "line": {"type": "integer", "description": "Номер первой строки окна (1-based)."},
                        "snippet": {"type": "string", "description": "Строки окна с номерами."},
                    },
                    "required": ["path", "line", "snippet"],
                    "additionalProperties": False,
                },
            },
            "truncated": {
                "type": "boolean",
                "description": "Квота max_results была набрана: список может быть неполным.",
            },
        },
        "required": ["matches", "truncated"],
        "additionalProperties": False,
    },
    effects="read",
    idempotent=True,
    errors=("invalid_input", "not_found", "denied"),
    availability="*",
    cost="cheap",
    limits={"max_results": SEARCH_MAX_RESULTS,
            "context_lines": SEARCH_MAX_CONTEXT_LINES},
)

TOOLS = (SEARCH,)

