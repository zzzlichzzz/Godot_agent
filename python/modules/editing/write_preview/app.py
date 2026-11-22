"""modules/editing/write_preview/app.py - запрос → поиск → план → WAL (ADR-0005).

Только оркестрация (≤ 80 строк). Поиск — чужой инструмент `analyze_rename`
(один экземпляр, R-04), шаги — `editing.symbol_rename`, диффы и запись
`PREPARED` в журнал — `report.py`. В проект не пишется ничего (R-12, SEC-11).
"""

from python.kernel.errors import AppError
from python.modules.editing import symbol_rename

from . import report
from .domain import core

TOOL = "write_preview"


def call(tool, args, ctx):
    """Предпросмотр переименования: план `PREPARED`, проект не тронут."""
    if tool != TOOL:
        raise AppError("unknown_tool", "модуль editing.write_preview не владеет %r"
                       % (tool,), hint="Список инструментов даёт tools/list")
    request = core.build_request(args)
    analysis = ctx.call_tool("analyze_rename", core.analysis_args(request))
    texts, newlines, expected = report.read_texts(ctx, analysis)
    compiled = symbol_rename.compile_plan(
        analysis, texts, request["mode"], request["allow_unverified"],
        request["exclude"], newlines)
    return report.save(ctx, request, compiled, texts, expected)
