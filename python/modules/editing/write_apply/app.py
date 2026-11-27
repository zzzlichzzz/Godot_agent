"""modules/editing/write_apply/app.py - применение плана под локом (ADR-0005).

Только оркестрация (≤ 80 строк): лок → проверки домена → на каждый шаг «бэкап,
правка, квитанция» → `COMMITTED`. Сбой шага откатывает уже применённое и
пробрасывает исходную ошибку: проект остаётся как до `apply` (ADR-0005).
"""

import time

from python.kernel.errors import AppError
from python.kernel.approval import require_explicit_confirmation
from python.modules.editing.shared import funnel, plan_log

from . import report
from .domain import core

TOOL = "write_apply"

def call(tool, args, ctx):
    """Применить `PREPARED`-план: повтор с тем же digest эффекта не даёт."""
    if tool != TOOL:
        raise AppError("unknown_tool", "модуль editing.write_apply не владеет %r"
                       % (tool,), hint="Список инструментов даёт tools/list")
    request = core.validate_request(args)
    lock = ctx.port("lock")
    if not lock.acquire():
        raise AppError("conflict", "проект занят другой записью",
                       details={"reason": "lock_busy"},
                       hint="Дождитесь завершения другого apply")
    try:
        return _apply(ctx, request)
    finally:
        lock.release()

def _apply(ctx, request):
    journal = ctx.port("journal")
    plan_id = request["plan_id"]
    entries = journal.read(plan_id)
    require_explicit_confirmation(entries, ctx.path_policy)
    created = journal.modified_at(plan_id) if entries else 0.0
    decision = core.decide_apply(entries, request["digest"], created, time.time())
    if "reuse" in decision:
        if any(step["op"] in ("move", "replace_raw", "dir_case")
               for step in plan_log.plan_of(entries)["steps"]):
            raise AppError("stale_plan", "план переноса уже применён")
        return decision["reuse"]["result"]
    return funnel.execute(ctx, decision["plan"], report.result)

