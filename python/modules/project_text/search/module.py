# modules/project_text/search/module.py - манифест модуля project_text.search.
# tools: search
# Правила: R-02 (папка = фича), R-03 (подключение сканированием), R-05 (манифест),
# ADR-0003 (модуль объявляет порты, адаптеры приносит bootstrap).

from python.kernel.module_spec import ModuleSpec

from . import app

MODULE = ModuleSpec(
    id="project_text.search",
    description="Поиск литеральной подстроки по текстовым файлам проекта.",
    provides_tools=("search",),
    requires_ports=("fs",),
    capabilities=("project_text.search",),
    entrypoints={"call": app.call},
)

