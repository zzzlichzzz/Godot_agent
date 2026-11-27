"""modules/editing/shared/plan_log.py - чтение WAL плана (ADR-0005).

Обе механики воронки читают одни и те же записи (`PREPARED`, `APPLYING`,
`RECEIPT`, `COMMITTED`, `RESTORED`, `ROLLED_BACK`). Дублировать разбор нельзя:
разошедшееся чтение означает, что откат не видит квитанций применения.
Функции чистые: записи приходят списком, время — аргументом.
"""

from python.kernel.write_plan import CONFIRM_TTL, STATES


def state_of(entries):
    """Состояние плана: последняя запись из `STATES`.

    `RECEIPT` и `RESTORED` — учётные записи, а не состояния плана: если их
    считать, recovery увидит «RECEIPT» вместо `APPLYING` и ничего не откатит.
    """
    for record in reversed(list(entries or ())):
        state = record.get("state")
        if state in STATES:
            return str(state)
    return ""


def plan_of(entries):
    """План из записи `PREPARED`; без неё плана нет."""
    for record in entries or ():
        plan = record.get("plan")
        if record.get("state") == "PREPARED" and isinstance(plan, dict):
            return plan
    return None


def entry_id_of(plan_id, index):
    """`"<plan_id>#<n>"` — формат зафиксирован ADR-0005 и не меняется."""
    return "%s#%d" % (plan_id, int(index))


def next_index(entries):
    """Номер следующего `APPLYING`: 1 для первого применения."""
    return 1 + sum(1 for record in entries or ()
                   if record.get("state") == "APPLYING")


def receipts_of(entries, entry_id):
    """Квитанции одного применения по порядку шагов."""
    return [dict(record["receipt"]) for record in entries or ()
            if record.get("state") == "RECEIPT"
            and record.get("entry_id") == entry_id
            and isinstance(record.get("receipt"), dict)]


def committed_entry(entries):
    """Запись `COMMITTED`: идемпотентный повтор возвращает её результат."""
    for record in reversed(list(entries or ())):
        if record.get("state") == "COMMITTED":
            return record
    return None


def is_expired(created_at, now, ttl=CONFIRM_TTL):
    """План старше `confirm_ttl` секунд применять нельзя (ADR-0005)."""
    return bool(created_at) and float(now) - float(created_at) > float(ttl)
