"""Public K1 read-only agent loop; discovery uses the ordinary module lane."""
from python.kernel.module_spec import ModuleSpec
from . import app

MODULE = ModuleSpec(id='assistant.chat', provides_tools=('chat',),
    capabilities=('assistant.chat',), requires_ports=('chat_gateway',),
    corpus='corpus', entrypoints={'call': app.call, 'setup': app.setup})
