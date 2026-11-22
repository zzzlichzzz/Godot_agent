"""Confirmed write loop; ordinary K1 chat remains read-only."""
from python.kernel.module_spec import ModuleSpec
from . import app
from .tools import TOOLS
MODULE=ModuleSpec(id='assistant.write',description='Нативный preview/confirm/apply/rollback.',
    provides_tools=tuple(t.name for t in TOOLS),requires_ports=('native_planner','journal','lock','chat_gateway'),
    requires=('editing.write_apply','editing.rollback','assistant.judge'),entrypoints={'call':app.call})
