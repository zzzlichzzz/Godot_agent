"""modules/editing/shared/conflict_reasons.py - единый набор причин `conflict`.

Шестая причина не должна появляться молча: клиент, панель и тесты сверяются с
одним списком (ADR-0005). `plan_state:<STATE>` — параметрическая причина
(состояние плана в `details.reason`), её проверяет `is_known`.
"""

from python.kernel.write_plan import STATES

#: Причины отказа по существу, кроме `plan_state:<STATE>`.
REASONS = (
    "unverified_references",
    "dynamic_references",
    "all_usages_excluded",
    "name_conflict",
    "already_applied",
    "already_rolled_back",
    "lock_busy",
    "no_receipts",
    "backup_missing",
    "backup_mismatch",
    "post_state_mismatch",
)

STATE_PREFIX = "plan_state:"


def is_known(reason):
    """Причина из набора или `plan_state:<известное состояние>`."""
    text = str(reason or "")
    if text in REASONS:
        return True
    if not text.startswith(STATE_PREFIX):
        return False
    return text[len(STATE_PREFIX):] in STATES
