# modules/code_intel/functions/module.py - манифест модуля code_intel.functions.
# tools: functions
# Правила: R-02 (папка = фича), R-03 (подключение сканированием), R-05 (манифест),
# ADR-0003 (модуль объявляет порты, адаптеры приносит bootstrap).

from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(
    id="code_intel.functions",
    description="Список объявленных функций .gd и тела запрошенных имён.",
    provides_tools=("functions",),
    requires_ports=("fs",),
    capabilities=("code_intel.functions",),
    entrypoints={"call": app.call},
)

