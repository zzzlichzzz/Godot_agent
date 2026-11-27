"""Public read owner; import performs no IO."""
from python.kernel.module_spec import ModuleSpec
from .app import call
from ..shared.file_index import ProjectTextFileSystem

MODULE = ModuleSpec(id="project_text.read", description="Чтение файла проекта",
                    provides_tools=("read",), capabilities=("project_text.read",),
                    port_factories={"project_text_fs": ProjectTextFileSystem},
                    requires_ports=("project_text_fs",), entrypoints={"call": call})
