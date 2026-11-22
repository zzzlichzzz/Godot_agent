# tool: scene
from python.kernel.module_spec import ModuleSpec
from .app import call

MODULE = ModuleSpec(id='scene_model.tree', description='Read-only file scene summary',
                    provides_tools=('scene',), requires_ports=('fs',),
                    capabilities=('scene_model.tree',), entrypoints={'call': call},
                    corpus='corpus')
