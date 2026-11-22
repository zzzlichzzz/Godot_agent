"""C.22 internal contributor; public contract27 and headless26 stay unchanged."""
from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(id="editing.file_refactor", description="Транзакционный перенос файлов и ссылок.",
                    provides_tools=(), contributes_to=("write_preview", "write_apply"),
                    internal_services=("file_refactor",), requires=("editing.paths_preview",),
                    requires_ports=("paths_fs", "writer", "node_diff", "gd_lint", "journal", "backups", "lock"),
                    entrypoints={"prepare": app.prepare, "apply": app.apply, "sync": app.sync})
