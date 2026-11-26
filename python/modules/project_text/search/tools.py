"""modules/project_text/search/tools.py - дескриптор механики (R-05, ADR-0006).

Источник правды: `contract/capabilities/search.json` генерируется из этого файла
(`python tools/gen_contract.py`) и руками не правится.
"""

from python.kernel.tool_spec import ToolSpec

from .settings import SEARCH_MAX_CONTEXT_LINES, SEARCH_MAX_RESULTS

SEARCH = ToolSpec(
    name="search",
    description=(
        "Find a literal substring in permitted project text files. Results are grouped "
        "by nearby lines. Use include_rel_prefixes and only_exts to narrow the search; "
        "set offset=0 to page, then reuse next_offset and the same query/filters."
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
            "include_rel_prefixes": {"type": "array", "maxItems": 64,
                "items": {"type": "string", "maxLength": 1024},
                "description": "Directory prefixes, e.g. scripts/ or res://scripts. Empty means all."},
            "only_exts": {"type": "array", "maxItems": 64,
                "items": {"type": "string", "maxLength": 32},
                "description": "Restrict the permitted extensions, e.g. ['.gd', '.tscn']."},
            "offset": {"type": "integer", "minimum": 0,
                "description": "Number of matching groups to skip. Start at 0 for exact pagination."},
            "snippet_chars": {"type": "integer", "minimum": 64, "maximum": 16000,
                "description": "Optional character cap per snippet. If context crowds out the first hit, show the matching line first; omitted text may be marked with … ."},
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
                        "line": {"type": "integer", "description": "Номер первой строки с совпадением в группе (1-based)."},
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
            "next_offset": {"type": ["integer", "null"], "minimum": 0,
                            "description": "With offset: start of next page, or null."},
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
