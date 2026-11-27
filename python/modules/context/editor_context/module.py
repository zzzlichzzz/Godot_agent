"""modules/context/editor_context/module.py - манифест модуля context.editor_context.

Секция `editor` пакета контекста: инструментов модуль не предоставляет
(`provides_tools=()`), поэтому `entrypoints` пуст - реестр принимает такой
манифест при непустом `contributes_to` (ADR-0004). Профиль `editor`: в headless
моста нет, секция отвечает `no_module` (ADR-0007). Порт `editor` есть во всех
профилях как ленивый клиент; отключение идёт по `environment`, а не по порту.
Правила: R-02 (папка = фича), R-03 (подключение сканированием), R-05 (манифест).
"""

from python.kernel.module_spec import ModuleSpec

MODULE = ModuleSpec(
    id="context.editor_context",
    description="Снимок редактора как секция контекста (мост, часть A: только чтение).",
    environment="editor",
    provides_tools=(),
    contributes_to=("context",),
    internal_services=("editor_bridge",),
    requires_ports=("editor",),
    capabilities=("context.editor_context",),
)
