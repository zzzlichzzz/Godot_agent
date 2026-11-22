"""modules/context/gather/app.py - сценарий `context`: запрос → секции → ответ.

Владелец собирает только то, что знает сам (`project`, `tools`); остальные секции
приходят вкладами через реестр (ADR-0004). Отказ вклада — не ошибка вызова: он
попадает в `unavailable` с причиной, потому что «в этом окружении секции нет» —
это факт окружения, а не сбой запроса.
"""

from python.kernel.errors import AppError
from python.modules.context.shared.context_section import (is_unavailable,
                                                           reason_of,
                                                           unavailable)

from .domain import core

TOOL = "context"
SECTION = "context"


def call(tool, args, ctx):
    """Обработчик единственного инструмента фичи."""
    if tool != TOOL:
        raise AppError("unknown_tool",
                       "context.gather: чужой инструмент %r" % (tool,),
                       hint="владелец `context` отвечает только за %r" % (TOOL,))
    contributions = _contributions(ctx)
    request = core.build_request(args, ctx.path_policy, contributions)
    fragments, absent = {}, []
    for name in request["sections"]:
        fragment = _fragment(name, ctx, contributions, request["path"])
        if is_unavailable(fragment):
            absent.append({"name": name, "reason": reason_of(fragment)})
        else:
            fragments[name] = fragment
    return core.assemble(fragments, absent)


def _contributions(ctx):
    """Вклады в `context` из реестра: модуль может быть не загружен вовсе."""
    registry = getattr(ctx, "registry", None)
    return registry.contributions(SECTION) if registry is not None else ()


def _fragment(name, ctx, contributions, target):
    """Фрагмент секции: встроенная — здесь, остальная — у вклада."""
    if name == "project":
        return core.project_section(_root(ctx), _project_file(ctx.port("fs")))
    if name == "tools":
        return core.tools_section([(entry.spec.name, entry.spec.effects)
                                   for entry in ctx.registry.entries()])
    contribution = core.find_contribution(contributions, name)
    if contribution is None:
        return unavailable(core.NO_MODULE)
    try:
        fragment = contribution.fragment({"path": target})
    except AppError:
        raise
    except Exception:  # вклад — чужой код: его сбой не валит весь вызов
        return unavailable("failed")
    if not isinstance(fragment, dict):
        return unavailable("failed")
    return fragment


def _root(ctx):
    """Корень проекта берём у политики путей: она уже нормализовала его."""
    return str(getattr(ctx.path_policy, "project_root", "") or "")


def _project_file(fs):
    """`project.godot` есть? Одно чтение дешевле обхода всего проекта."""
    try:
        fs.read_text("project.godot")
    except OSError:
        return None
    return "res://project.godot"

