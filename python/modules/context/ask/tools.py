"""ToolSpec is the public contract; its generated artifact is never hand-edited."""
from python.kernel.tool_spec import ToolSpec

from .domain.core import DEFAULT_BUDGET, LIMITS

ASK = ToolSpec(
    name="ask",
    description=("Компактная справка о проекте: релевантная карта кода, структура, "
                 "точные фрагменты, вызовы и сигналы. Запрос — английские имена "
                 "и термины кода; файлы проекта только читаются."),
    args={"type": "object", "properties": {
        "query": {"type": "string", "minLength": 1,
                  "description": "Непустой запрос об именах, терминах или пути проекта."},
        "budget_chars": {"type": "integer", "default": DEFAULT_BUDGET,
                         "description": "Бюджет символов; нативный нижний порог 400."}},
        "required": ["query"], "additionalProperties": False},
    result={"type": "string"},
    effects="read", idempotent=True,
    errors=("invalid_input", "not_found", "denied"), availability="*",
    cost="bounded", limits=LIMITS,
)
TOOLS = (ASK,)
