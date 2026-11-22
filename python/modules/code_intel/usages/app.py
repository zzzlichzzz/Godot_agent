"""modules/code_intel/usages/app.py - сценарий: запрос → политика → индекс → домен.

Только оркестрация (≤ 80 строк): правила поиска — в `domain/core.py`, обход и
разбор — `shared/symbol_index.py`, ошибки — `AppError` с типом (R-04, R-15).
Инструмент ничего не пишет (SEC-11): индекс собирается в памяти на один вызов,
на диск не кэшируется.
"""

from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel
from python.modules.code_intel.shared import symbol_index

from .domain import core

TOOL = "usages"
#: Второй инструмент модуля: предпросмотр переименования поверх того же поиска.
RENAME = "analyze_rename"
RES_PREFIX = "res://"


def call(tool, args, ctx):
    """Обработчики модуля: `usages` и его обёртка `analyze_rename` (R-04)."""
    if tool == RENAME:
        query = core.build_rename_query(
            args.get("kind"), args.get("old_name"), args.get("new_name"),
            args.get("declaration"), args.get("mode"), args.get("allow_unverified"))
    elif tool == TOOL:
        query = core.build_query(args.get("kind"), args.get("old_name"),
                                 args.get("new_name"), args.get("declaration"))
    else:
        raise AppError("unknown_tool", "модуль code_intel.usages не владеет %r" % (tool,),
                       hint="Список инструментов даёт tools/list")
    _check_policy(query, ctx)
    index = symbol_index.build(ctx.port("fs"), ctx.path_policy)
    if tool == RENAME:
        return core.analyze(index, query)
    return core.find(index, query)


def _check_policy(query, ctx):
    """Путь объявления проверяется до чтения — как `_resolve_safe_path` эталона."""
    rel = normalize_rel(query.path[len(RES_PREFIX):])
    if rel is None:
        raise AppError("denied", "путь вне проекта",
                       hint="declaration задаётся как res://файл.gd:строка")
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError("denied", reason,
                       hint="Аддоны и исходники агента закрыты политикой путей")
