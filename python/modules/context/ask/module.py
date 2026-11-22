"""Auto-discovered owner of the public, read-only ask capability."""
from python.kernel.module_spec import ModuleSpec

from . import app, tools

MODULE = ModuleSpec(
    id="context.ask", description="Компактная карта кода и фрагменты проекта.",
    provides_tools=(tools.ASK.name,), requires_ports=("librarian",),
    capabilities=("context.ask",), corpus="corpus", entrypoints={"call": app.call},
)
