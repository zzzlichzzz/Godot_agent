"""Validate and dispatch text search through the file system port."""

from dataclasses import replace

from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel

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
        include_prefixes=_include_prefixes(args.get("include_rel_prefixes", ())),
        only_exts=args.get("only_exts"),
        snippet_chars=args.get("snippet_chars"),
    )
    _check_ranges(query)
    offset = args.get("offset")
    scan = query if offset is None else replace(query, max_results=offset + query.max_results + 1)
    rows, truncated = _scan(ctx, scan, skip=offset or 0) if query.needles else ([], False)
    if offset is None:
        return {"matches": rows, "truncated": truncated}
    return {"matches": rows[:query.max_results], "truncated": truncated,
            "next_offset": offset + query.max_results if truncated else None}


def _include_prefixes(values):
    prefixes = []
    for value in values:
        rel = normalize_rel(value[6:] if value.startswith('res://') else value)
        if rel is None:
            raise AppError("invalid_input", "include_rel_prefixes must name project directories")
        prefixes.append(rel + '/')
    return tuple(prefixes)


def _check_ranges(query):
    if not 1 <= query.max_results <= SEARCH_MAX_RESULTS:
        raise AppError("invalid_input",
                       "max_results вне диапазона 1..%d" % SEARCH_MAX_RESULTS,
                       hint="Уменьшите квоту: большой поиск медленный и шумный")
    if not 0 <= query.context_lines <= SEARCH_MAX_CONTEXT_LINES:
        raise AppError("invalid_input",
                       "context_lines вне диапазона 0..%d" % SEARCH_MAX_CONTEXT_LINES,
                       hint="Контекст нужен для чтения, а не для обхода файла")


def _scan(ctx, query, *, skip):
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
        file_rows, stop, hit_quota = core.match_file(query, rel, text, counts, skip=skip)
        rows.extend(file_rows)
        truncated = truncated or hit_quota
        if stop:
            return rows, True
    return rows, truncated
