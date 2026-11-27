"""C.12 owns api_check; contribution to verify is intentionally C.13."""
from python.kernel.module_spec import ModuleSpec

from .app import call
from .tools import TOOLS

MODULE = ModuleSpec(
    id='verification.api_check', version='0.1.0', kernel_api='^1', godot='^4.6',
    environment='*', provides_tools=('api_check',), contributes_to=('verify',), requires_ports=('api_cache',),
    capabilities=('verification.api_check',), entrypoints={'call': call}, corpus='corpus',
)
