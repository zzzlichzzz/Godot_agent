"""modules/editing/rollback/app.py - откат по квитанциям (ADR-0005, §6.6).

Оркестрация (≤ 80 строк): лок → проверки домена → обратный проход по
квитанциям: сверить post-state с `applied_hash`, восстановить бэкап, записать
`RESTORED`. Чужая правка после `apply` → `conflict`, файл не трогаем.
"""

from python.kernel.errors import AppError
from python.modules.editing.shared import funnel, plan_log, script_edits

from . import report
from .domain import core

TOOL = "write_rollback"


def call(tool, args, ctx):
    """Вернуть байты квитанций: повтор уже откаченного — `conflict`."""
    if tool != TOOL:
        raise AppError("unknown_tool", "модуль editing.rollback не владеет %r"
                       % (tool,), hint="Список инструментов даёт tools/list")
    request = core.validate_request(args)
    lock = ctx.port("lock")
    if not lock.acquire():
        raise AppError("conflict", "проект занят другой записью",
                       details={"reason": "lock_busy"},
                       hint="Дождитесь завершения другой записи")
    try:
        return _rollback(ctx, request)
    finally:
        lock.release()


def _rollback(ctx, request):
    journal = ctx.port("journal")
    plan_id, entry_id = request["plan_id"], request["entry_id"]
    entries = journal.read(plan_id)
    core.check_can_rollback(entries, entry_id)
    plan = plan_log.plan_of(entries)
    if plan_log.state_of(entries) != "ROLLING_BACK":
        journal.append(plan_id, {"state": "ROLLING_BACK", "entry_id": entry_id})
    done = core.restored_of(entries, entry_id)
    restored = []
    for receipt in core.order(entries, entry_id):
        target = receipt["step_id"]
        if target in done:
            restored.append({"path": target, "hash": funnel.restore_expected(plan, target)})
            continue
        restored.append(_restore(ctx, plan, plan_id, entry_id, receipt))
    directories = {step["target"] for step in plan["steps"] if step["op"] == "mkdir"}
    result = report.result(entry_id, plan_id, [row for row in restored if row["path"] not in directories])
    journal.append(plan_id, {"state": "ROLLED_BACK", "entry_id": entry_id,
                             "result": result})
    return result


def _restore(ctx, plan, plan_id, entry_id, receipt):
    """All operation-specific pre/post checks and inverses belong to the funnel."""
    target = receipt["step_id"]
    step = next(item for item in plan["steps"] if item["target"] == target)
    rel = script_edits.rel_of(target)
    if step["op"] in ("move", "dir_case"):
        funnel.guard_transfer(ctx, rel, script_edits.rel_of(step["payload"]["dest"]))
    else:
        funnel.guard_path(ctx, rel)
    writer = ctx.port("writer")
    if step["op"] != "mkdir" and funnel.intent_unstarted(writer, plan, target):
        return {"path": target, "hash": funnel.restore_expected(plan, target)}
    restored = funnel.restore(writer, ctx.port("backups"), plan, target,
                              receipt["undo_token"], receipt["applied_hash"],ctx.port("journal").read(plan_id),entry_id)
    ctx.port("journal").append(plan_id, {"state": "RESTORED", "entry_id": entry_id,
                                        "path": target, "hash": restored})
    return {"path": target, "hash": restored}
