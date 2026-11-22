"""protocol/registry.py - сборка реестра возможностей (R-05, R-03, ADR-0004).

Реестр не импортирует модули: вклады приносит композиционный корень (ADR-0003).
Дубль `tool_name` — конфликт: оба владельца отключаются, агент продолжает жить
и честно отвечает `unavailable` по инструментам отключённого модуля (R-03).

Кроме владельцев инструментов реестр помнит **вклады** (`contributes_to`): модуль
не публикует имя, а реализует часть чужого составного инструмента. Владелец
забирает их через `contributions("write_preview")` и не импортирует чужой модуль.
"""

from dataclasses import dataclass



@dataclass(frozen=True)
class ToolEntry:
    """Владелец инструмента: модуль, его дескриптор и обработчик."""

    module_id: str
    spec: object
    handler: object


class Registry:
    def __init__(self):
        self._entries = {}
        self._conflicts = []
        self._disabled = {}
        #: Кто объявлял имя, даже если модуль потом отключён: без этого
        #: инструмент выключенного модуля отвечал бы `unknown_tool` (R-03).
        self._owners = {}
        #: Имя чужого инструмента → вклады в порядке загрузки модулей.
        self._contributions = {}

    def add_module(self, module, tools, handlers, contributions=()):
        """Зарегистрировать вклады одного модуля. Конфликт отключает обоих."""
        if module.id in self._disabled:
            return
        self._add_contributions(module, contributions)

        for tool in tools:
            self._owners.setdefault(tool.name, [])
            if module.id not in self._owners[tool.name]:
                self._owners[tool.name].append(module.id)
            handler = handlers.get(tool.name)
            if handler is None:
                self._disable(module.id, "нет обработчика для %r" % (tool.name,))
                continue
            owner = self._entries.get(tool.name)
            if owner is not None:
                self._conflicts.append({"tool": tool.name,
                                        "owners": [owner.module_id, module.id]})
                self._disable(owner.module_id, "конфликт tool_name %r" % (tool.name,))
                self._disable(module.id, "конфликт tool_name %r" % (tool.name,))
                continue
            self._entries[tool.name] = ToolEntry(module.id, tool, handler)

    def mark_failures(self, failures):
        """Ошибки загрузки модулей: модуль disabled, причины сохранены (R-03)."""
        for item in failures:
            module_id = item.get("module", "?")
            for name in item.get("provides_tools", ()):
                owners = self._owners.setdefault(name, [])
                if module_id not in owners:
                    owners.append(module_id)
            self._disable(module_id,
                          item.get("reason", "ошибка загрузки"))

    def disabled_reason(self, tool_name):
        """`(module_id, причина)` для инструмента отключённого модуля, иначе None."""
        for module_id in self._owners.get(tool_name, ()):
            if module_id in self._disabled:
                return module_id, self._disabled[module_id]
        return None

    def get(self, name):
        return self._entries.get(name)

    def names(self):
        return sorted(self._entries)

    def entries(self):
        return [self._entries[name] for name in self.names()]

    def conflicts(self):
        return list(self._conflicts)

    def disabled(self):
        return dict(self._disabled)

    def contributions(self, tool_name):
        """Вклады в чужой инструмент: `(объект вклада, ...)` в порядке загрузки."""
        return tuple(self._contributions.get(tool_name, ()))

    def _add_contributions(self, module, contributions):
        """Вклад знает, в какие инструменты он входит; реестр раскладывает по именам."""
        targets = tuple(getattr(module, "contributes_to", ()) or ())
        for contribution in contributions or ():
            for tool_name in targets:
                bucket = self._contributions.setdefault(tool_name, [])
                if contribution not in bucket:
                    bucket.append(contribution)

    def _disable(self, module_id, reason):
        self._disabled[module_id] = reason
        for name in [key for key, entry in self._entries.items()
                     if entry.module_id == module_id]:
            del self._entries[name]
