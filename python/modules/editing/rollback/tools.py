"""modules/editing/rollback/tools.py - дескриптор отката (R-05, ADR-0005).

`idempotent=True` с оговоркой: повторный откат уже откаченного — `conflict`
(`details.reason=already_rolled_back`), а не тихий успех.
"""

from python.kernel.tool_spec import ToolSpec

RESTORED_ITEM = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Файл: `res://path.gd`."},
        "hash": {"type": "string", "description": "sha256 восстановленных байтов."},
    },
    "required": ["path", "hash"],
    "additionalProperties": False,
}
RESULT_FIELDS = {
    "entry_id": {"type": "string"},
    "state": {"type": "string", "enum": ["ROLLED_BACK"]},
    "plan_id": {"type": "string"},
    "restored": {"type": "array", "items": RESTORED_ITEM},
    "removed": {"type": "array", "items": {"type": "string"}},
    "files_count": {"type": "integer"},
}
RESULT_REQUIRED = ["entry_id", "state", "plan_id", "restored", "removed",
                   "files_count"]

WRITE_ROLLBACK = ToolSpec(
    name="write_rollback",
    description=(
        "Откатить применённый план по `entry_id` из `write_apply`: каждый файл "
        "восстанавливается из бэкапа сырых байтов и сверяется с `expected` "
        "побайтово, квитанции идут от последней к первой. Если файл правили "
        "после `apply` — `conflict`, файл не трогается. Повторный откат — "
        "`conflict` (`already_rolled_back`)."
    ),
    args={
        "type": "object",
        "properties": {
            "entry_id": {"type": "string", "minLength": 1,
                         "description": "`<plan_id>#<n>` из ответа `write_apply`."},
        },
        "required": ["entry_id"],
        "additionalProperties": False,
    },
    result={"type": "object", "properties": RESULT_FIELDS,
            "required": RESULT_REQUIRED, "additionalProperties": False},
    effects="write",
    idempotent=True,
    errors=("invalid_input", "not_found", "conflict", "denied", "internal"),
    availability="*",
    cost="heavy",
)

TOOLS = (WRITE_ROLLBACK,)
