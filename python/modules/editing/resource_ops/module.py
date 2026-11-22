"""D14 internal metadata contributor: no public ToolSpec or resource dispatch."""
from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(id="editing.resource_ops", description="Подготовка и byte-preserving правка .tres через общую воронку.",
                    provides_tools=(), contributes_to=("write_preview",), internal_services=("resource_ops",),
                    requires_ports=("resource_read", "journal", "lock", "writer", "backups"), requires=("editing.write_apply",),
                    entrypoints={"prepare_write": app.prepare_write, "apply": app.apply, "transform_summary": app.transform_summary, "prepare": app.prepare,
                    "normalize_action": app.normalize_action, "file_sha256": app.file_sha256,
                    "canonical_digest": app.canonical_digest, "public_prepared": app.public_prepared,
                    "operation_summary": app.operation_summary})
