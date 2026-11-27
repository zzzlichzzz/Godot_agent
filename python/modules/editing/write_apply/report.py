"""modules/editing/write_apply/report.py - итог применения (ADR-0005).

`entry_id` и квитанции — то, по чему работает откат; `applied` — пары
«файл — хеш после правки», по ним `rollback` сверяет post-state.
"""


def result(plan, entry_id, receipts, started, finished):
    """Конверт `COMMITTED`: план, квитанции и хеши применённых файлов."""
    directories = {step["target"] for step in plan["steps"] if step["op"] == "mkdir"}
    receipts = [receipt for receipt in receipts if receipt["step_id"] not in directories]
    applied = [{"path": receipt["step_id"], "applied_hash": receipt["applied_hash"]}
               for receipt in receipts]
    return {
        "entry_id": entry_id,
        "state": "COMMITTED",
        "plan_id": plan["plan_id"],
        "digest": plan["digest"],
        "applied": applied,
        "receipts": [{"step_id": receipt["step_id"],
                      "applied_hash": receipt["applied_hash"],
                      "undo_token": receipt["undo_token"]} for receipt in receipts],
        "files_count": len(applied),
        "started_at": started,
        "finished_at": finished,
    }
