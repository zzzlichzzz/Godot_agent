"""modules/editing/rollback/domain/core.py - правила отката (ADR-0005, §6.6).

Чистый домен: порядок квитанций, что уже восстановлено, можно ли начинать.
Записи WAL читает `editing/shared/plan_log.py` — тот же разбор, что и у apply.
"""

from python.kernel.errors import AppError
from python.modules.editing.shared import plan_log


def validate_request(args):
    """`entry_id` — строка вида `<plan_id>#<n>`."""
    data = args if isinstance(args, dict) else {}
    value = data.get("entry_id")
    if not isinstance(value, str) or not value.strip():
        raise AppError("invalid_input", "entry_id обязателен: строка",
                       hint="Возьмите entry_id из ответа `write_apply`")
    value = value.strip()
    plan_id, _, index = value.rpartition("#")
    if not plan_id or not index.isdigit() or int(index) < 1:
        raise AppError("invalid_input", "entry_id должен быть '<plan_id>#<n>'",
                       hint="Формат фиксирован ADR-0005: plan_id#1")
    return {"entry_id": value, "plan_id": plan_id, "index": int(index)}


def restored_of(entries, entry_id):
    """Пути, уже восстановленные этим откатом (повтор его продолжает)."""
    return {record.get("path") for record in entries or ()
            if record.get("state") == "RESTORED"
            and record.get("entry_id") == entry_id}


def order(entries, entry_id):
    """Квитанции применения в порядке ОТКАТА (от последней к первой)."""
    receipts = plan_log.receipts_of(entries, entry_id)
    if not receipts:
        raise AppError("conflict", "у записи нет квитанций",
                       details={"reason": "no_receipts", "entry_id": entry_id})
    return list(reversed(receipts))


def check_can_rollback(entries, entry_id):
    """Отказ, если откатывать нечего или уже откачено (не тихий успех)."""
    if not entries or plan_log.plan_of(entries) is None:
        raise AppError("not_found", "запись не найдена",
                       hint="entry_id берётся из ответа `write_apply`")
    state = plan_log.state_of(entries)
    if state == "ROLLED_BACK":
        raise AppError("conflict", "запись уже откачена",
                       details={"reason": "already_rolled_back", "state": state},
                       hint="план уже откачен — сделай новый `write_preview`")
    if state not in ("COMMITTED", "ROLLING_BACK", "APPLYING"):
        raise AppError("conflict", "откат невозможен в состоянии %s" % (state or "?"),
                       details={"reason": "plan_state:%s" % state})
    if not plan_log.receipts_of(entries, entry_id):
        raise AppError("conflict", "у записи нет квитанций",
                       details={"reason": "no_receipts", "entry_id": entry_id})
    return state
