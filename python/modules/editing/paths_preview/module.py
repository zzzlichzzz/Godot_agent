"""Read-only paths preview; no dependency on the C.22 write refactor."""
from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(id="editing.paths_preview", description="Поиск ссылок и read-only проекция путей.",
                    provides_tools=("paths_preview",), requires_ports=("paths_fs",),
                    capabilities=("editing.paths_preview",), entrypoints={"call": app.call})
