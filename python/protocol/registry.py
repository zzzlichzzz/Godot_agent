"""protocol/registry.py - сборка реестра возможностей (R-05, R-03, ADR-0004).

Реестр не импортирует модули: вклады приносит композиционный корень (ADR-0003).
Дубль `tool_name` — конфликт: оба владельца отключаются, агент продолжает жить
и честно отвечает `unavailable` по инструментам отключённого модуля (R-03).

Кроме владельцев инструментов реестр помнит **вклады** (`contributes_to`): модуль
не публикует имя, а реализует часть чужого составного инструмента. Владелец
забирает их через `contributions("write_preview")` и не импортирует чужой модуль.
"""

from dataclasses import dataclass


def target_alias(module_id, names):
    """Unambiguous historical module-ID target for a public tool."""
    short = module_id.rsplit('.', 1)[-1]
    return short if short in names else (next(iter(names)) if len(names) == 1 else None)

@dataclass(frozen=True)
class ToolEntry:
    """Владелец инструмента: модуль, его дескриптор и обработчик."""

    module_id: str
    spec: object
    handler: object


class Registry:
    def __init__(self):
        self._entries = {}
        self._conflicts = {}
        self._disabled = {}
        #: Кто объявлял имя, даже если модуль потом отключён: без этого
        #: инструмент выключенного модуля отвечал бы `unknown_tool` (R-03).
        self._owners = {}
        #: Имя чужого инструмента → вклады в порядке загрузки модулей.
        self._contributions = {}
        self._aliases = {}
        self._order = {}

    def declare(self, module_id, names):
        """Reserve names before activation, including names from shipped contracts."""
        self._order.setdefault(module_id, len(self._order))
        for name in names:
            owners = self._owners.setdefault(name, [])
            if module_id not in owners:
                owners.append(module_id)
            if len(owners) > 1:
                self._conflicts[name] = sorted(owners)
                for owner in owners:
                    self._disable(owner, 'конфликт tool_name %r' % name)

    def targets(self, module):
        names = tuple(getattr(module, 'provides_tools', ()))
        # Older manifests name the module (e.g. code_intel.usages → usages).
        target = target_alias(module.id, names)
        if target:
            self._aliases[module.id] = target

    def add_module(self, module, tools, handlers, contributions=()):
        """Зарегистрировать вклады одного модуля. Конфликт отключает обоих."""
        self.declare(module.id, [tool.name for tool in tools])
        if module.id in self._disabled:
            return
        for tool in tools:
            if handlers.get(tool.name) is None:
                self._disable(module.id, "нет обработчика для %r" % (tool.name,))
                return
        self.targets(module)
        self._add_contributions(module, contributions)
        for tool in tools:
            self._entries[tool.name] = ToolEntry(module.id, tool, handlers[tool.name])

    def mark_failures(self, failures):
        """Ошибки загрузки модулей: модуль disabled, причины сохранены (R-03)."""
        for item in failures:
            module_id = item.get("module", "?")
            self.declare(module_id, item.get('provides_tools', ()))
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
        return [{'tool': key, 'owners': owners[:]} for key, owners in sorted(self._conflicts.items())]

    def disabled(self):
        return dict(self._disabled)

    def contributions(self, tool_name):
        """Вклады в чужой инструмент: `(объект вклада, ...)` в порядке загрузки."""
        target = self._aliases.get(tool_name, tool_name)
        found = []
        for owner, targets, value in sorted(self._contributions.values(), key=lambda row: self._order[row[0]]):
            if any(self._aliases.get(t, t) == target for t in targets) and value not in found:
                found.append(value)
        return tuple(found)

    def _add_contributions(self, module, contributions):
        """Вклад знает, в какие инструменты он входит; реестр раскладывает по именам."""
        targets = tuple(getattr(module, "contributes_to", ()) or ())
        for contribution in contributions or ():
            self._contributions[module.id, id(contribution)] = (module.id, targets, contribution)

    def _disable(self, module_id, reason):
        self._disabled.setdefault(module_id, reason)
        for key in [k for k in self._contributions if k[0] == module_id]:
            del self._contributions[key]
        for name in [key for key, entry in self._entries.items()
                     if entry.module_id == module_id]:
            del self._entries[name]
