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
from .domain.lookup import infer_locator

TOOL = "usages"
#: Второй инструмент модуля: предпросмотр переименования поверх того же поиска.
RENAME = "analyze_rename"
RES_PREFIX = "res://"


def call(tool, args, ctx):
    """Обработчики модуля: `usages` и его обёртка `analyze_rename` (R-04)."""
    if tool not in (TOOL, RENAME):
        raise AppError("unknown_tool", "модуль code_intel.usages не владеет %r" % (tool,),
                       hint="Список инструментов даёт tools/list")
    index = None
    if 'declaration' in args:
        if 'declaration_path' in args:
            raise AppError('invalid_input', 'укажите либо declaration, либо declaration_path')
        locator = args['declaration']
    else:
        kind, name = core.validate_symbol(args['kind'], args['old_name'])
        scope = args.get('declaration_path')
        if scope is not None:
            if not scope.startswith(RES_PREFIX) or not scope.endswith('.gd'):
                raise AppError('invalid_input', 'declaration_path должен иметь вид res://path.gd')
            scope = RES_PREFIX + _check_policy(scope, ctx)
        index = symbol_index.build(ctx.port('fs'), ctx.path_policy)
        locator = infer_locator(index, kind, name, scope, ctx.path_policy)
    if tool == RENAME:
        query = core.build_rename_query(
            args.get("kind"), args.get("old_name"), args.get("new_name"),
            locator, args.get("mode"), args.get("allow_unverified"))
    else:
        query = core.build_query(args.get("kind"), args.get("old_name"), args.get("new_name"), locator)
    _check_policy(query.path, ctx)
    if index is None:
        index = symbol_index.build(ctx.port("fs"), ctx.path_policy)
    if tool == RENAME:
        return core.analyze(index, query)
    return core.find(index, query)


def _check_policy(path, ctx):
    """Путь объявления проверяется до чтения — как `_resolve_safe_path` эталона."""
    rel = normalize_rel(path[len(RES_PREFIX):])
    if rel is None:
        raise AppError("denied", "путь вне проекта",
                       hint="declaration задаётся как res://файл.gd:строка")
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError("denied", reason,
                       hint="Аддоны и исходники агента закрыты политикой путей")
    return rel
