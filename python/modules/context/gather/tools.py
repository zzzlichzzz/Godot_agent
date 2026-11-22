"""modules/context/gather/tools.py - дескриптор инструмента `context` (R-05, ADR-0006).

Источник правды: `contract/capabilities/context.json` генерируется из этого файла
(`python tools/gen_contract.py`) и руками не правится.
"""

from python.kernel.tool_spec import ToolSpec

from .domain.core import MAX_SECTIONS

CONTEXT = ToolSpec(
    name="context",
    description=(
        "Один read-only вызов вместо пяти: отдаёт пакет контекста проекта — корень и "
        "project.godot, список инструментов агента с их эффектами, а также секции, "
        "которые собирают другие модули (состояние редактора, рантайм). Секции "
        "запрашиваются по имени; секция, которой нет в этом окружении, попадает в "
        "unavailable с причиной, а не валит вызов. Вызывать в начале работы, когда "
        "неясно, где мы находимся и что уже доступно."
    ),
    args={
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": MAX_SECTIONS,
                "description": ("Имена секций в порядке выдачи; по умолчанию — все "
                                "известные. Неизвестное имя отказывает весь вызов."),
            },
            "path": {
                "type": "string",
                "description": ("Цель для секций, которые её читают (res://-путь). "
                                "Вне проекта — отказ denied."),
            },
        },
        "required": [],
        "additionalProperties": False,
    },
    result={
        "type": "object",
        "properties": {
            "sections": {
                "type": "object",
                "description": "Собранные секции: имя → фрагмент (форма у каждого своя).",
            },
            "available": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Имена собранных секций, по алфавиту.",
            },
            "unavailable": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Имя секции."},
                        "reason": {
                            "type": "string",
                            "description": ("Почему секции нет: no_module, no_bridge, "
                                            "failed."),
                        },
                    },
                    "required": ["name", "reason"],
                    "additionalProperties": False,
                },
                "description": "Секции, которых нет в этом окружении, по алфавиту.",
            },
            "cost": {
                "type": "string",
                "description": "Стоимость сборки: light — без живого движка.",
            },
        },
        "required": ["sections", "available", "unavailable", "cost"],
        "additionalProperties": False,
    },
    effects="read",
    idempotent=True,
    errors=("invalid_input", "not_found", "denied"),
    availability="*",
    cost="light",
    limits={"sections": MAX_SECTIONS},
)

TOOLS = (CONTEXT,)

