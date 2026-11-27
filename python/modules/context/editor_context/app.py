"""modules/context/editor_context/app.py - секция `editor`: мост → фрагмент.

Своего инструмента у модуля нет: секцию `editor` запрашивает владелец `context`
через реестр вкладов (ADR-0004). Порт `editor` связывает композиция:
`bind(ctx)` зовёт `runtime/bootstrap.py` при регистрации вклада, до этого секция
отвечает `no_bridge`, а не падает. Смысл ответа моста проверяет домен
(`domain/core.py`), транспорт схем не знает (R-14). Правила: R-04, R-11, R-15.
"""

from python.kernel.errors import AppError
from python.modules.context.shared.context_section import (ContextSection,
                                                           unavailable)

from .domain import core

#: Имя секции в пакете контекста (уже в `RESERVED_SECTIONS` владельца).
NAME = "editor"
#: Причины, которые видит потребитель; прочее - отказ инструмента, а не данные.
REASONS = ("no_bridge", "engine_down", "wrong_project", "verbs_mismatch")


class EditorSection(ContextSection):
    """Секция `editor`: без моста - `unavailable`, с мостом - снимок редактора."""

    __slots__ = ("_ctx",)

    def __init__(self):
        super().__init__(NAME, self._collect, cost="heavy")
        self._ctx = None

    def bind(self, ctx):
        """Композиция отдаёт контекст модуля: порт `editor` живёт в нём."""
        self._ctx = ctx

    def _collect(self, target=None):
        """Снимок редактора; недоступность моста - это данные, а не исключение."""
        if self._ctx is None:
            return unavailable("no_bridge")
        try:
            return core.collect(self._ctx.port("editor"))
        except AppError as exc:
            reason = str((exc.details or {}).get("reason") or "")
            if exc.kind not in ("engine_down", "unavailable"):
                raise
            return unavailable(reason if reason in REASONS else "engine_down")


#: Вклад в секцию `context`: один экземпляр на процесс (R-04).
SECTION = EditorSection()

