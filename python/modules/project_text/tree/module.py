"""Project tree with a public view and a stable internal entry point."""
from python.kernel.module_spec import ModuleSpec
from .app import build, call

MODULE = ModuleSpec(id="project_text.tree", description="Дерево файлов проекта",
                    provides_tools=("tree",),
                    internal_services=("project_text.tree",), requires_ports=("project_text_fs",),
                    entrypoints={"build": build, "call": call})
