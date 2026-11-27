# tool: node_delete_preview
from python.kernel.module_spec import ModuleSpec
from .app import call

MODULE = ModuleSpec(id='scene_model.node_delete', provides_tools=('node_delete_preview',),
    requires=('scene_model.node_rename',), requires_ports=('fs', 'node_diff'),
    capabilities=('scene_model.node_delete',), entrypoints={'call': call}, corpus='corpus')
