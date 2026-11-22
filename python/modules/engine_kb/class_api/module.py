"""C.11 owns api; existing read-only api_cache is its only port."""
# tool: api
from python.kernel.module_spec import ModuleSpec

from .app import call
from .tools import TOOLS

MODULE = ModuleSpec(
    id='engine_kb.class_api', version='0.1.0', kernel_api='^1', godot='^4.6',
    environment='*', provides_tools=('api',), requires_ports=('api_cache',),
    capabilities=('engine_kb.class_api',), entrypoints={'call': call}, corpus='corpus',
)
