# modules/verification/gd_lint/module.py — discovered read mechanic (R-03/R-05).
# tools: gd_lint
from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(
    id='verification.gd_lint',
    description='Консервативный текстовый линт GDScript без исполнения и записи.',
    provides_tools=('gd_lint',), requires_ports=('fs',),
    capabilities=('verification.gd_lint',),
    contributes_to=('verify',),
    entrypoints={'call': app.call}, corpus='corpus',
)
