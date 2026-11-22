"""modules/context/gather/module.py - манифест владельца инструмента `context`.

Единственное, что общий код знает про эту фичу (R-05): имя инструмента, нужные
порты и точку входа. Секции других модулей приходят вкладом (ADR-0004), поэтому
`ctx.registry.contributions("context")` — единственный канал, которым владелец их
видит.
"""

from python.kernel.module_spec import ModuleSpec

from . import app, tools

MODULE = ModuleSpec(
    id="context.gather",
    description="Пакет контекста проекта: встроенные секции и вклады модулей.",
    provides_tools=(tools.CONTEXT.name,),
    requires_ports=("fs",),
    capabilities=("context.gather",),
    entrypoints={"call": app.call},
)

