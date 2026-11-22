"""modules/editing/rollback/recovery.py - восстановление после падения (ADR-0005).

Единственная точка входа — `recover(ports)`: её вызывается из
`runtime/bootstrap.py` на старте. Правила:

| Найдено | Действие |
|---|---|
| `PREPARED` старше `confirm_ttl` | `EXPIRED`, файлы не трогаем |
| `APPLYING` с квитанциями | обратный проход по квитанциям → `ROLLED_BACK` |
| `APPLYING` с intent без receipt | доказать pre/post-state и откатить |
| legacy `APPLYING` без intent/receipt | `left_prepared`, эффект не угадываем |
| `ROLLING_BACK` | продолжить обратный проход с невосстановленных |
"""

import time

from python.kernel.errors import AppError
from python.modules.editing.shared import funnel, plan_log, script_edits

from .domain import core


def recover(ports, logger=None):
    """Пройти по WAL и привести недоделанные планы в согласованное состояние."""
    journal, writer = ports.get("journal"), ports.get("writer")
    backups, lock = ports.get("backups"), ports.get("lock")
    if not (journal and writer and backups):
        return []
    report = []
    for plan_id in journal.plan_ids():
        entries = journal.read(plan_id)
        plan = plan_log.plan_of(entries)
        if plan is None:
            continue
        state = plan_log.state_of(entries)
        if state == "PREPARED" and plan_log.is_expired(journal.modified_at(plan_id),
                                                       time.time()):
            journal.append(plan_id, {"state": "EXPIRED", "reason": "ttl"})
            report.append({"plan_id": plan_id, "action": "expired"})
        elif state in ("APPLYING", "ROLLING_BACK") and lock is not None:
            report.append(_rollback_applying(journal, writer, backups, lock,
                                             plan_id, entries, plan, state))
    for item in report:
        if logger is not None:
            logger.warning("recovery: plan=%s action=%s", item.get("plan_id"),
                           item.get("action"))
    return [item for item in report if item]


def _rollback_applying(journal, writer, backups, lock, plan_id, entries, plan, state):
    entry_id = next((r["entry_id"] for r in reversed(entries)
                     if r.get("state") == "APPLYING" and r.get("entry_id")), plan_id + "#1")
    if not funnel.effects_of(entries, entry_id) and state == "APPLYING":
        return {"plan_id": plan_id, "action": "left_prepared"}
    if not lock.acquire():
        return {"plan_id": plan_id, "action": "lock_busy"}
    try:
        entries = journal.read(plan_id)
        plan = plan_log.plan_of(entries)
        state = plan_log.state_of(entries)
        done = core.restored_of(entries, entry_id)
        if state == "APPLYING":
            journal.append(plan_id, {"state": "ROLLING_BACK", "entry_id": entry_id,
                                     "reason": "recovery"})
        for receipt, pending in reversed(funnel.effects_of(entries, entry_id)):
            target = receipt["step_id"]
            if target in done:
                continue
            try:
                if pending and funnel.intent_unstarted(writer, plan, target):
                    continue
                restored = funnel.restore(writer, backups, plan, target,
                                          receipt["undo_token"], receipt["applied_hash"],journal.read(plan_id),entry_id)
            except (AppError, OSError) as exc:
                reason = exc.kind if isinstance(exc, AppError) else "conflict"
                journal.append(plan_id, {"state": "RECOVERY_FAILED",
                                         "entry_id": entry_id, "path": target,
                                          "reason": reason})
                return {"plan_id": plan_id, "action": "failed", "path": target,
                        "reason": reason}
            journal.append(plan_id, {"state": "RESTORED", "entry_id": entry_id,
                                     "path": target,
                                      "hash": restored})
        journal.append(plan_id, {"state": "ROLLED_BACK", "entry_id": entry_id,
                                 "reason": "recovery"})
        return {"plan_id": plan_id, "action": "rolled_back"}
    finally:
        lock.release()


def rel_of(target):
    return script_edits.rel_of(target)
