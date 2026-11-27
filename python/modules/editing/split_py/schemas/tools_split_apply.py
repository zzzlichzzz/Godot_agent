"""C.20 strict write contract: accepted split_plan → transactional apply."""
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.tool_spec import ToolSpec

from .tools_split_plan import PLAN_RESULT

RECEIPT = {"type": "object", "required": ["step_id", "applied_hash", "undo_token"],
           "properties": {"step_id": {"type": "string", "minLength": 1},
                          "applied_hash": {"type": "string"},
                          "undo_token": {"type": "string"}},
           "additionalProperties": False}
APPLY_ARGS = {"type": "object", "required": ["path", "plan"],
              "properties": {"path": {"type": "string", "minLength": 1},
                             "plan": PLAN_RESULT},
              "additionalProperties": False}
APPLY_RESULT = {
    "type": "object",
    "required": ["donor", "written", "moved", "facade_lines", "receipts"],
    "properties": {
        "donor": {"type": "string", "minLength": 1},
        "written": {"type": "array", "items": {"type": "string"}},
        "moved": {"type": "array", "items": {"type": "string"}},
        "facade_lines": {"type": "integer"},
        "receipts": {"type": "array", "items": RECEIPT}},
    "additionalProperties": False}
APPLY = ToolSpec(
    name="split_apply",
    description="Применить подтверждённый split_plan через WAL с квитанциями.",
    args=APPLY_ARGS, result=APPLY_RESULT, effects="write", idempotent=False,
    errors=("invalid_input", "not_found", "denied", "stale_plan", "conflict", "internal"),
    availability="*", cost="heavy", requires_preview=True,
    limits={"max_file_bytes": READ_TEXT_MAX_BYTES})
