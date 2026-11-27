"""Accepted C.14 scan plus C.15 read-only plan; porter cannot self-accept."""
# tools: split_gd_scan, split_gd_plan
from python.kernel.module_spec import ModuleSpec

from .app import call

MODULE = ModuleSpec(
    id='editing.split_gd', version='0.1.0', kernel_api='^1', godot='^4.6',
    environment='*', provides_tools=('split_gd_scan', 'split_gd_plan'), requires_ports=('fs', 'api_cache'),
    capabilities=('editing.split_gd',), entrypoints={'call': call}, corpus='corpus',
)
