# modules/editing/write_apply/module.py - манифест модуля editing.write_apply.
# tools: write_apply — единственная механика, которой разрешено менять проект
# (R-12). Требует план из editing.write_preview и порты writer/journal/backups/lock.
# Правила: R-02, R-05, R-12, ADR-0003 (порты), ADR-0005 (протокол).

from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(
    id="editing.write_apply",
    description=("Применение подтверждённого плана: WAL APPLYING/COMMITTED, "
                 "квитанции и entry_id для отката; stale-check по хешам байтов."),
    provides_tools=("write_apply",),
    requires_ports=("writer", "journal", "backups", "lock"),
    requires=("editing.write_preview", "editing.rollback"),
    capabilities=("editing.write_apply",),
    entrypoints={"call": app.call},
)
