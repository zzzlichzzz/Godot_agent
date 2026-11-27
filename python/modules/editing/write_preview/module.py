# modules/editing/write_preview/module.py - манифест модуля editing.write_preview.
# tools: write_preview — план переименования с диффами и WAL PREPARED. В проект
# не пишет: применение плана — editing.write_apply (часть 2, ADR-0005).
# Правила: R-02 (папка = фича), R-03 (подключение сканированием), R-05 (манифест),
# R-12 (запись только через воронку), ADR-0003 (порты), ADR-0005 (протокол).

from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(
    id="editing.write_preview",
    description=("Предпросмотр записи: план переименования символа, диффы, "
                 "затронутые файлы и WAL PREPARED. Проект не меняется."),
    provides_tools=("write_preview",),
    requires_ports=("fs", "journal"),
    requires=("code_intel.usages", "editing.symbol_rename"),
    capabilities=("editing.write_preview",),
    entrypoints={"call": app.call},
)
