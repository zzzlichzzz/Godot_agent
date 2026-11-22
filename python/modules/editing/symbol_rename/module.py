"""modules/editing/symbol_rename/module.py - манифест модуля editing.symbol_rename.

Свой инструмент модулю не нужен: он вклад в чужие составные инструменты
(`editing.write_preview` применяет план, `code_intel.usages` доказывает ссылки).
Правила: R-02, R-03, R-05, R-12, ADR-0004.
"""

from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(
    id="editing.symbol_rename",
    description="Компилятор переименования символа: отчёт анализа → шаги плана "
                "(без своего инструмента и без записи).",
    provides_tools=(),
    contributes_to=("editing.write_preview", "code_intel.usages"),
    internal_services=("symbol_rename_compiler",),
    capabilities=("editing.symbol_rename",),
    entrypoints={"plan": app.build_plan},
)
