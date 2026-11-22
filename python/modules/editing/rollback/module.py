# modules/editing/rollback/module.py - манифест модуля editing.rollback.
# tools: write_rollback — откат по квитанциям write_apply и recovery WAL при
# старте (ADR-0005). Порты те же: writer/journal/backups/lock.

from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(
    id="editing.rollback",
    description=("Откат применённой записи по квитанциям: post-state check, "
                 "восстановление байтов, WAL ROLLING_BACK/ROLLED_BACK; "
                 "recovery недоделанных планов при старте."),
    provides_tools=("write_rollback",),
    requires_ports=("writer", "journal", "backups", "lock"),
    requires=("editing.write_apply",),
    capabilities=("editing.rollback",),
    entrypoints={"call": app.call},
)
