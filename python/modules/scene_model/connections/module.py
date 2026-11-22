# tool: connections
from python.kernel.module_spec import ModuleSpec
from .app import call

MODULE=ModuleSpec(id='scene_model.connections',description='Read-only signal connections',
                  provides_tools=('connections',),requires_ports=('fs',),
                  capabilities=('scene_model.connections',),entrypoints={'call':call},corpus='corpus')
