# tool: node_rename_preview
from python.kernel.module_spec import ModuleSpec
from .app import call

MODULE = ModuleSpec(id='scene_model.node_rename', description='Read-only node rename plan',
                    provides_tools=('node_rename_preview',), requires_ports=('fs', 'gd_lint'),
                    capabilities=('scene_model.node_rename',), entrypoints={'call': call}, corpus='corpus')
