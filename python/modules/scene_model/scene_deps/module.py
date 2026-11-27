# tool: scene_deps
from python.kernel.module_spec import ModuleSpec
from .app import call

MODULE=ModuleSpec(id='scene_model.scene_deps',description='Read-only scene/script handler analysis',
                  provides_tools=('scene_deps',),requires_ports=('fs',),
                  capabilities=('scene_model.scene_deps',),entrypoints={'call':call},corpus='corpus')
