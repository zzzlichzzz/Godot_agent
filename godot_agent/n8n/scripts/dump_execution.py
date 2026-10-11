# -*- coding: utf-8 -*-
"""Дамп исполнения воркфлоу n8n через MCP: статус, ноды, ошибки, данные.

Зачем. После прогона фабрики нужно быстро увидеть, чем закончилось
исполнение: какие ноды отработали, где ошибки, что в ответах ключевых нод —
без браузера и без ручного разбора базы. Инструмент n8n MCP
`get_workflow_execution` (includeData) отдаёт уже разобранные данные
(flatted-формат SQLite разбирать не нужно).

Запуск (из папки n8n):
    python -B scripts/dump_execution.py 61
    python -B scripts/dump_execution.py 52 --out exec52.json
    python -B scripts/dump_execution.py 52 --nodes "Аудитор (ищет баги),Сборщик информации (4 канала)"

Печатает мету исполнения, lastNodeExecuted, ошибку верхнего уровня и список
нод (число запусков и статусы). С --nodes дополнительно печатает данные
указанных нод (первые 1500 символов JSON на запуск). С --out сохраняет
полный ответ MCP в файл.
"""

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WF = "v81fH05KY5uKUNK0"  # «Шаблон v2: Ядро + 4 канала»


def load_invoker():
    """Импортировать mcp_invoke.py из этой же папки (без пакета)."""
    path = os.path.join(HERE, "mcp_invoke.py")
    spec = importlib.util.spec_from_file_location("mcp_invoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    invoke = load_invoker()
    parser = argparse.ArgumentParser(description="Дамп исполнения n8n через MCP")
    parser.add_argument("execution_id")
    parser.add_argument("--workflow-id", default=DEFAULT_WF)
    parser.add_argument("--nodes", default="",
                        help="имена нод через запятую — печатать их данные")
    parser.add_argument("--out", default=None,
                        help="сохранить полный ответ MCP в файл")
    parser.add_argument("--meta", action="store_true",
                        help="только мета (без includeData) — быстро")
    parser.add_argument("--truncate", type=int, default=1,
                        help="truncateData для includeData (по умолчанию 1)")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    meta = invoke.tool_result(invoke.call_tool("get_workflow_execution", {
        "workflowId": args.workflow_id,
        "executionId": args.execution_id,
    }))
    if not meta or "execution" not in meta:
        raise SystemExit("Не удалось получить мету исполнения %s"
                         % args.execution_id)
    execution = meta["execution"]
    for key in ("status", "mode", "startedAt", "stoppedAt"):
        print("%s: %s" % (key, execution.get(key)))

    if args.meta:
        return

    full = invoke.tool_result(invoke.call_tool("get_workflow_execution", {
        "workflowId": args.workflow_id,
        "executionId": args.execution_id,
        "includeData": True,
        "truncateData": args.truncate,
    }))
    if not full or "data" not in full:
        raise SystemExit("Не удалось получить данные исполнения %s"
                         % args.execution_id)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(full, fh, ensure_ascii=False, indent=1)
        print("WROTE %s" % args.out)

    result = (full.get("data") or {}).get("resultData") or {}
    print("lastNodeExecuted: %s" % result.get("lastNodeExecuted"))
    if result.get("error"):
        print("ERROR: %s" % json.dumps(result["error"],
                                       ensure_ascii=False)[:600])
    run_data = result.get("runData") or {}
    print("nodes ran: %d" % len(run_data))
    for name, runs in run_data.items():
        marks = []
        for run in runs:
            status = run.get("executionStatus", "ok")
            err = run.get("error")
            if err:
                status += ":%s" % str(err.get("message", ""))[:80]
            marks.append(status)
        print(" - %s %d %s" % (name, len(runs), marks[:3]))

    wanted = [name.strip() for name in args.nodes.split(",") if name.strip()]
    for name in wanted:
        runs = run_data.get(name)
        if not runs:
            print("=== %s: запусков нет ===" % name)
            continue
        print("=== %s (%d запусков) ===" % (name, len(runs)))
        for index, run in enumerate(runs):
            print("--- run %d ---" % index)
            print(json.dumps(run.get("data", {}), ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
