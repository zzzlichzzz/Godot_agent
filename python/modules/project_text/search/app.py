"""modules/project_text/search/app.py - сценарий: валидация → домен → результат.

Только оркестрация (≤ 80 строк): правила — в `domain/core.py`, доступ к диску —
в порту `fs`, ошибки — `AppError` с типом (R-04, R-15).
"""

from python.kernel.errors import AppError

from .domain import core
from .settings import SEARCH_MAX_CONTEXT_LINES, SEARCH_MAX_RESULTS

TOOL = "search"


def call(tool, args, ctx):
    """Обработчик инструмента `search` для этого модуля."""
    if tool != TOOL:
        raise AppError("unknown_tool", "модуль project_text.search не владеет %r" % (tool,),
                       hint="Список инструментов даёт tools/list")
    query = core.build_query(
        args.get("query"),
        max_results=args.get("max_results", 30),
        context_lines=args.get("context_lines", 2),
        exclude_rel_prefixes=args.get("exclude_rel_prefixes") or (),
        case_insensitive=bool(args.get("case_insensitive", False)),
        agent_py_allowed=ctx.path_policy.agent_py_allowed,
    )
    _check_ranges(query)
    if not query.needles:
        return {"matches": [], "truncated": False}
    return _scan(ctx, query)


def _check_ranges(query):
    if not 1 <= query.max_results <= SEARCH_MAX_RESULTS:
        raise AppError("invalid_input",
                       "max_results вне диапазона 1..%d" % SEARCH_MAX_RESULTS,
                       hint="Уменьшите квоту: большой поиск медленный и шумный")
    if not 0 <= query.context_lines <= SEARCH_MAX_CONTEXT_LINES:
        raise AppError("invalid_input",
                       "context_lines вне диапазона 0..%d" % SEARCH_MAX_CONTEXT_LINES,
                       hint="Контекст нужен для чтения, а не для обхода файла")


def _scan(ctx, query):
    fs = ctx.port("fs")
    policy = ctx.path_policy
    counts = [0] * len(query.needles)
    rows = []
    truncated = False
    for rel in fs.list_files():
        if not policy.can_read(rel) or not core.is_candidate(query, rel):
            continue
        try:
            text = fs.read_text(rel)
        except OSError:
            # Нечитаемый файл не ломает выдачу: эталон его просто пропускает.
            continue
        file_rows, stop, hit_quota = core.match_file(query, rel, text, counts)
        rows.extend(file_rows)
        truncated = truncated or hit_quota
        if stop:
            return {"matches": rows, "truncated": True}
    return {"matches": rows, "truncated": truncated}

