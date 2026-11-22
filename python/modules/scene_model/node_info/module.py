# tool: node
from python.kernel.module_spec import ModuleSpec
from .app import call

MODULE = ModuleSpec(id='scene_model.node_info', description='Read-only scene node card',
                    provides_tools=('node',), requires_ports=('fs',),
                    capabilities=('scene_model.node_info',), entrypoints={'call':call},
                    corpus='corpus')
