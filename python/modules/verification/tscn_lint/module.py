"""C.8 owns read-only scene-text check; not the deferred check aggregator."""
from python.kernel.module_spec import ModuleSpec

from .app import call
from .tools import TOOLS

MODULE = ModuleSpec(
    id='verification.tscn_lint', version='0.1.0', kernel_api='^1',
    godot='^4.6', environment='*', provides_tools=('check',),
    requires_ports=('fs', 'api_cache'), capabilities=('verification.tscn_lint',),
    contributes_to=('verify',),
    entrypoints={'call': call}, corpus='corpus',
)
