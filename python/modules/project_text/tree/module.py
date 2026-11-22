"""Private project tree; its first context consumer is a later slice."""
from python.kernel.module_spec import ModuleSpec
from .app import build

MODULE = ModuleSpec(id="project_text.tree", description="Внутреннее дерево проекта",
                    internal_services=("project_text.tree",), requires_ports=("project_text_fs",),
                    entrypoints={"build": build})
