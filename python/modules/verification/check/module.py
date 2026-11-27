"""C.9 owner of verify; check remains owned by verification.tscn_lint."""
from python.kernel.module_spec import ModuleSpec

from .app import call
from .tools import TOOLS

MODULE = ModuleSpec(
    id='verification.check', version='0.1.0', kernel_api='^1',
    godot='^4.6', environment='*', provides_tools=('verify',),
    requires_ports=('fs',), capabilities=('verification.check',),
    entrypoints={'call': call}, corpus='corpus',
)
