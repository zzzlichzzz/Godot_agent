"""protocol/dispatch.py - вызов сценария по имени возможности (R-04, R-15).

Порядок один для всех каналов: найти владельца → проверить вход по схеме →
вызвать обработчик → классифицировать исключение. Канал только переводит ответ.
"""

import difflib

from python.kernel.errors import AppError

from .error_map import from_exception
from .validation import validate_args


class Dispatcher:
    def __init__(self, registry, roots=()):
        self._registry = registry
        self._roots = tuple(roots)

    def call(self, tool, args):
        if not isinstance(tool, str):
            raise AppError("unknown_tool", "имя инструмента должно быть строкой",
                           hint="Список инструментов даёт tools/list")
        entry = self._registry.get(tool)
        if entry is None:
            raise self._missing(tool)
        validate_args(entry.spec, args)
        try:
            return entry.handler(args)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001 - граница классификации (R-15)
            raise from_exception(exc, self._roots) from None

    def _missing(self, tool):
        """Инструмент отключённого модуля — `unavailable` с причиной (R-03)."""
        reason_of = getattr(self._registry, "disabled_reason", None)
        found = reason_of(tool) if reason_of else None
        if found:
            module_id, reason = found
            return AppError("unavailable",
                            "инструмент %r выключен: модуль %s не работает"
                            % (tool, module_id),
                            hint="Причина: %s" % reason)
        return AppError("unknown_tool", "инструмент %r не найден" % tool,
                        hint=self._hint(tool))

    def _hint(self, tool):
        names = self._registry.names()
        nearest = difflib.get_close_matches(tool, names, n=1, cutoff=0.6)
        if nearest:
            return "Возможно, вы имели в виду %r" % nearest[0]
        return "Список инструментов даёт tools/list"

