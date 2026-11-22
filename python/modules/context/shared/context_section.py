"""modules/context/shared/context_section.py - интерфейс вклада в `context` (ADR-0004).

Секция — данные, а не код фичи: имя, стоимость и функция сборки. Владелец
инструмента (`context.gather`) собирает вклады через реестр
(`ctx.registry.contributions("context")`) и не импортирует чужой `domain/` (R-11).

Сборка (`collect`) получает `target` (`{"path": <относительный путь или None>}`) и
возвращает JSON-объект секции. Если секции нет в этом окружении, вклад возвращает
`unavailable("no_bridge")` — владелец положит её в `unavailable`, а не превратит
отказ окружения в ошибку всего вызова.

Здесь нет ни IO, ни знания о конкретных секциях: интерфейс импортируют и владелец,
и вклады, поэтому он обязан оставаться пустым по зависимостям.
"""

import re

#: Имя секции — как имя инструмента: строчные латинские, цифры, подчёркивание.
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: Стоимость сборки: `light` — только то, что уже под рукой; `heavy` — чтение файлов.
COSTS = ("light", "heavy")

#: Причина «секции нет в этом окружении» для вклада, который не может собраться.
NO_MODULE = "no_module"


def unavailable(reason):
    """Фрагмент «секции нет в этом окружении» — форма ответа вклада."""
    return {"available": False, "reason": str(reason or "unavailable")}


def is_unavailable(fragment):
    """Отличить отказ вклада от собранной секции: `{"available": false, ...}`."""
    return isinstance(fragment, dict) and fragment.get("available") is False


def reason_of(fragment):
    """Короткая машинная причина отказа вклада (для `unavailable[].reason`)."""
    if not is_unavailable(fragment):
        return ""
    return str(fragment.get("reason") or "unavailable")


class ContextSection:
    """Имя, стоимость и сборка одного фрагмента контекста."""

    __slots__ = ("name", "cost", "collect")

    def __init__(self, name, collect, cost="light"):
        if not NAME_RE.match(str(name or "")):
            raise ValueError("имя секции: ожидалось [a-z][a-z0-9_]*, получено %r"
                             % (name,))
        if not callable(collect):
            raise ValueError("collect секции %r должен быть вызываемым" % (name,))
        if cost not in COSTS:
            raise ValueError("стоимость секции %r: ожидалось одно из %s, получено %r"
                             % (name, ", ".join(COSTS), cost))
        self.name = str(name)
        self.cost = str(cost)
        self.collect = collect

    def fragment(self, target=None):
        """Собрать фрагмент: то же, что `collect(target)`, без обёрток."""
        return self.collect(target)

    def __repr__(self):
        return "ContextSection(name=%r, cost=%r)" % (self.name, self.cost)
