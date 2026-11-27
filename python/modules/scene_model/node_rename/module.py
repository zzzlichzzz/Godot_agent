# tool: node_rename_preview
from python.kernel.module_spec import ModuleSpec
from .app import call
from . import preview_diff

MODULE = ModuleSpec(id='scene_model.node_rename', description='Read-only node rename plan',
                    provides_tools=('node_rename_preview',), requires_ports=('fs', 'gd_lint'),
                    requires=('verification.gd_lint',), port_factories={'node_diff': lambda _fs: preview_diff},
                    capabilities=('scene_model.node_rename',), entrypoints={'call': call}, corpus='corpus')
