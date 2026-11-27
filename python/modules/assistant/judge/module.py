"""Auto-discovered assistant.judge owner; no registration outside this folder."""
from python.kernel.module_spec import ModuleSpec
from . import app, tools

MODULE = ModuleSpec(id='assistant.judge', description='Объяснимая проектная оценка ответа без записи.',
    provides_tools=('judge',), requires_ports=('fs', 'librarian'), capabilities=('assistant.judge',),
    corpus='corpus', entrypoints={'call': app.call})
