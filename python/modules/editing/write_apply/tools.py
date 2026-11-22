"""modules/editing/write_apply/tools.py - дескриптор применения плана (R-05).

`idempotent=True` по контракту ADR-0005: повтор с тем же `digest` возвращает ту
же квитанцию и не даёт эффекта. Источник правды для
`contract/capabilities/write_apply.json` — этот файл (`gen_contract.py --write`).
"""

from python.kernel.tool_spec import ToolSpec

APPLIED_ITEM = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "applied_hash": {"type": "string", "description": "sha256 сырых байтов после правки."},
    },
    "required": ["path", "applied_hash"],
    "additionalProperties": False,
}
RECEIPT_ITEM = {
    "type": "object",
    "properties": {
        "step_id": {"type": "string", "description": "Цель шага: `res://path.gd`."},
        "applied_hash": {"type": "string"},
        "undo_token": {"type": "string", "description": "Бэкап байтов для отката."},
    },
    "required": ["step_id", "applied_hash", "undo_token"],
    "additionalProperties": False,
}

RESULT_FIELDS = {
    "entry_id": {"type": "string", "description": "`<plan_id>#<n>` — адрес для rollback."},
    "state": {"type": "string", "enum": ["COMMITTED"]},
    "plan_id": {"type": "string"},
    "digest": {"type": "string"},
    "applied": {"type": "array", "items": APPLIED_ITEM,
                "description": "Файлы и хеши ПОСЛЕ правки."},
    "receipts": {"type": "array", "items": RECEIPT_ITEM,
                 "description": "Квитанции шагов: ими откатывается план."},
    "files_count": {"type": "integer"},
    "started_at": {"type": "string"},
    "finished_at": {"type": "string"},
}
RESULT_REQUIRED = ["entry_id", "state", "plan_id", "digest", "applied", "receipts",
                   "files_count", "started_at", "finished_at"]

WRITE_APPLY = ToolSpec(
    name="write_apply",
    description=(
        "Применить подтверждённый план `write_preview` (`plan_id` + `digest`). "
        "Перед первой записью пишет `APPLYING` в WAL, на каждый файл — бэкап "
        "сырых байтов и квитанцию, в конце `COMMITTED` и `entry_id` для отката. "
        "Файл, изменившийся после предпросмотра, даёт `stale_plan` без записи. "
        "Повтор с тем же digest возвращает тот же результат без эффекта."
    ),
    args={
        "type": "object",
        "properties": {
            "plan_id": {"type": "string", "minLength": 1,
                        "description": "Из ответа `write_preview`."},
            "digest": {"type": "string", "minLength": 1,
                       "description": "Подтверждение привязано к плану и digest."},
        },
        "required": ["plan_id", "digest"],
        "additionalProperties": False,
    },
    result={"type": "object", "properties": RESULT_FIELDS,
            "required": RESULT_REQUIRED, "additionalProperties": False},
    effects="write",
    idempotent=True,
    errors=("invalid_input", "not_found", "stale_plan", "conflict", "denied",
            "internal"),
    availability="*",
    cost="heavy",
)

TOOLS = (WRITE_APPLY,)
