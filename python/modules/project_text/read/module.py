"""Public read owner; import performs no IO."""
from python.kernel.module_spec import ModuleSpec
from .app import call

MODULE = ModuleSpec(id="project_text.read", description="Чтение файла проекта",
                    provides_tools=("read",), capabilities=("project_text.read",),
                    requires_ports=("project_text_fs",), entrypoints={"call": call})
