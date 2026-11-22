# tool: node_reparent_preview
from python.kernel.module_spec import ModuleSpec
from .app import call

MODULE = ModuleSpec(id='scene_model.node_reparent', provides_tools=('node_reparent_preview',),
    requires=('scene_model.node_rename', 'verification.gd_lint'),
    requires_ports=('fs', 'gd_lint', 'node_diff'), capabilities=('scene_model.node_reparent',),
    entrypoints={'call': call}, corpus='corpus')
