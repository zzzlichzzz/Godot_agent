# modules/context/runtime_snapshot/module.py - манифест модуля context.runtime_snapshot.
# tool: - (HTTP-канал)

# Правила: R-02, R-03, R-05.
# Read-only инспектор рантайма: секции снапшота (tree/properties/errors/
# metrics/events), выбор сессии, форматирование для промпта.
# Старый код: godot_tools/runtime_debug.py. Инструмента MCP нет - только HTTP.

# TODO: ModuleSpec(id="context.runtime_snapshot", ...)

# contributes: context (секция рантайма)