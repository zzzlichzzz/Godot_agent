"""modules/editing/scene_ops/app.py - сценарий `scene_ops`: аргументы → мост → ответ.

Сценарий тонкий: порт `editor`, окружение, вызов домена. Смысловые проверки —
в `domain/core.py`; транспорт схем словаря не знает (R-14). Ошибки домена
(`AppError`) идут наверх как есть: `revision_mismatch`/`stale_plan` — это данные
для клиента, а не сбой.
"""

from python.kernel.errors import AppError

from .domain import core

TOOL = "scene_ops"


def call(tool, args, ctx):
    """Обработчик единственного инструмента фичи: план или применение батча."""
    if tool != TOOL:
        raise AppError("unknown_tool",
                       "editing.scene_ops: чужой инструмент %r" % (tool,),
                       hint="владелец `scene_ops` отвечает только за %r" % (TOOL,))
    request = core.build_request(args)
    return core.perform(ctx.port("editor"), request)
# Бюджет: только оркестрация (<= 80 строк); правила - в domain/core.py.
