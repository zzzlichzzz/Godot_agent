"""modules/editing/write_apply/domain/core.py - правила применения плана (ADR-0005).

Чистый домен: только вход и решения по записям WAL. Разбор самих записей —
`editing/shared/plan_log.py` (его же читает откат). Переходы: `PREPARED →
APPLYING → COMMITTED`, `ROLLING_BACK → ROLLED_BACK`, `EXPIRED`.
"""

from python.kernel.errors import AppError
from python.kernel.write_plan import CONFIRM_TTL
from python.modules.editing.shared import plan_log


def validate_request(args):
    """`plan_id` и `digest` — обязательные непустые строки."""
    data = args if isinstance(args, dict) else {}
    result = {}
    for name in ("plan_id", "digest"):
        value = data.get(name)
        if not isinstance(value, str) or not value.strip():
            raise AppError("invalid_input", "%s обязателен: строка" % name,
                           hint="Возьмите plan_id и digest из ответа `write_preview`")
        result[name] = value.strip()
    return result


def decide_apply(entries, digest, created_at, now, ttl=CONFIRM_TTL):
    """Что делать с планом: `{"reuse": запись}` или `{"plan": план}`.

    Исключения: `not_found` — плана нет или истёк (`details.state`);
    `stale_plan` — digest не тот; `conflict` — отказ по состоянию
    (`details.reason`: `already_rolled_back`, `plan_state:<STATE>`).
    """
    plan = plan_log.plan_of(entries)
    if plan is None:
        raise AppError("not_found", "план не найден",
                       hint="Постройте план заново (`write_preview`)")
    state = plan_log.state_of(entries)
    if plan.get("digest") != digest:
        raise AppError("stale_plan", "digest не совпадает с планом",
                       details={"expected": plan.get("digest"), "got": digest},
                       hint="Подтверждайте ровно тот план, который показан")
    if state == "COMMITTED":
        record = plan_log.committed_entry(entries)
        if record is None or not isinstance(record.get("result"), dict):
            raise AppError("internal", "COMMITTED без результата")
        return {"reuse": record}
    if state in ("ROLLING_BACK", "ROLLED_BACK"):
        raise AppError("conflict", "план уже откатывается или откачен",
                       details={"reason": "already_rolled_back", "state": state})
    if state == "APPLYING":
        raise AppError("conflict", "план уже применяется",
                       details={"reason": "plan_state:%s" % state})
    if state == "EXPIRED":
        raise AppError("not_found", "срок подтверждения истёк",
                       details={"state": state}, hint="Постройте план заново")
    if plan_log.is_expired(created_at, now, ttl):
        raise AppError("not_found", "срок подтверждения истёк",
                       details={"state": "EXPIRED", "ttl": int(ttl)},
                       hint="Постройте план заново (`write_preview`)")
    return {"plan": plan}
