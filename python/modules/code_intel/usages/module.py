# modules/code_intel/usages/module.py - манифест модуля code_intel.usages.
# tools: usages (где символ используется) и analyze_rename (что изменится при
# переименовании) — оба read-only и оба поверх одного поиска (R-04, R-08).
# Правила: R-02 (папка = фича), R-03 (подключение сканированием), R-05 (манифест),
# ADR-0003 (модуль объявляет порты, адаптеры приносит bootstrap).

from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(
    id="code_intel.usages",
    description=("Где объявлен символ, где он ещё используется и что изменится "
                 "при переименовании (только чтение)."),
    provides_tools=("usages", "analyze_rename"),
    requires_ports=("fs",),
    capabilities=("code_intel.usages",),
    entrypoints={"call": app.call},
)
