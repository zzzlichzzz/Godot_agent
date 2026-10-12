# -*- coding: utf-8 -*-
"""Отчёт по токенам прогона n8n: вызовы и usage каждой «Модель (…)».

Зачем. Ветка «Шаблон v3: Эконом + отказоустойчивость» оценивается числом
токенов, а не на глаз. n8n хранит usage каждого вызова AI-ноды
(runData[node].data.ai_languageModel[0][0].json.tokenUsage), а число вызовов
каждой «Модель (…)» — в executionData.metadata. Скрипт сводит это в таблицу:
вызовы (точно), токены (выборка первых запусков + экстраполяция) — «до» и
«после» правок схемы.

Запуск (из папки n8n):
    python -B scripts/token_report.py 95
    python -B scripts/token_report.py 92 93 94 95 --out tokens.json
    python -B scripts/token_report.py 95 --sample 5 --workflow-id <id>

--sample N — подсказка MCP truncateData (по умолчанию 3; больше — тяжелее
ответ). Для под-нод «Модель (…)» сервер обычно отдаёт ВСЕ запуски, и суммы
токенов получаются точными; «est» — сумма по полученным запускам (оценка
только если пришла выборка). В отчёт входят только ноды «Модель (…)».
"""

import argparse
import importlib.util
import json
import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WF = "v81fH05KY5uKUNK0"  # «Шаблон v2: Ядро + 4 канала»
MODEL_TYPE_MARK = "lmChatOpenAi"


def load_invoker():
    """Импортировать mcp_invoke.py из этой же папки (без пакета)."""
    path = os.path.join(HERE, "mcp_invoke.py")
    spec = importlib.util.spec_from_file_location("mcp_invoke", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_model_nodes(invoke, workflow_id):
    """Имена «Модель (…)»-нод из схемы воркфлоу (фильтр includeData)."""
    details = invoke.tool_result(invoke.call_tool("get_workflow_details", {
        "workflowId": workflow_id,
        "detailLevel": "full",
    })) or {}
    workflow = details.get("workflow") or details
    nodes = workflow.get("nodes") or []
    names = [n.get("name") for n in nodes
             if MODEL_TYPE_MARK in str(n.get("type", "")) and n.get("name")]
    return sorted(names)


def run_usage(run):
    """tokenUsage первого ответа модели в запуске ноды (или {})."""
    blocks = (run.get("data") or {}).get("ai_languageModel") or []
    for group in blocks:
        for item in (group or []):
            usage = (item.get("json") or {}).get("tokenUsage") or {}
            if usage:
                return usage
    return {}


def fnum(value):
    """Число с разделителями разрядов (1 234 567)."""
    return "{:,}".format(int(round(value))).replace(",", " ")


def show_execution(invoke, workflow_id, execution_id, model_names, sample):
    """Таблица «модель: вызовы/токены» одного исполнения; dict-итог."""
    full = invoke.tool_result(invoke.call_tool("get_workflow_execution", {
        "workflowId": workflow_id,
        "executionId": execution_id,
        "includeData": True,
        "truncateData": sample,
        "nodeNames": model_names,
    })) or {}
    data = full.get("data") or {}
    meta = ((data.get("executionData") or {}).get("metadata")) or {}
    run_data = ((data.get("resultData") or {}).get("runData")) or {}
    counts = {name: len(runs) for name, runs in meta.items()
              if isinstance(runs, list)}
    status = ((full.get("execution") or {}).get("status")) or "?"
    print("=== Прогон %s (%s) ===" % (execution_id, status))
    if not counts:
        print("  нет данных о вызовах моделей (модели не запускались?)")
        return {"calls": {}, "tokens": {}, "totals": {}}
    result = {"calls": counts, "tokens": {}, "totals": {}}
    tot_prompt = tot_completion = tot_calls = 0
    for name in sorted(counts, key=lambda key: -counts[key]):
        calls = counts[name]
        usages = [run_usage(run) for run in run_data.get(name) or []]
        usages = [item for item in usages if item]
        if usages:
            avg_prompt = sum(u.get("promptTokens", 0)
                             for u in usages) / len(usages)
            avg_completion = sum(u.get("completionTokens", 0)
                                 for u in usages) / len(usages)
            est_prompt = avg_prompt * calls
            est_completion = avg_completion * calls
            result["tokens"][name] = {
                "sample": len(usages),
                "avg_prompt": round(avg_prompt, 1),
                "avg_completion": round(avg_completion, 1),
                "est_prompt_total": round(est_prompt),
                "est_completion_total": round(est_completion),
            }
            print("  %-42s %4d выз.  выборка %d: prompt~%s + completion~%s"
                  " -> est prompt %s + completion %s"
                  % (name, calls, len(usages), fnum(avg_prompt),
                     fnum(avg_completion), fnum(est_prompt),
                     fnum(est_completion)))
            tot_prompt += est_prompt
            tot_completion += est_completion
        else:
            print("  %-42s %4d выз.  (токены: нет выборки)" % (name, calls))
        tot_calls += calls
    result["totals"] = {
        "calls": tot_calls,
        "est_prompt_total": round(tot_prompt),
        "est_completion_total": round(tot_completion),
    }
    print("  ИТОГО: %d вызовов; est prompt %s + completion %s (оценка ~)"
          % (tot_calls, fnum(tot_prompt), fnum(tot_completion)))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Токен-отчёт прогонов n8n")
    parser.add_argument("execution_id", nargs="+",
                        help="id исполнений (через пробел)")
    parser.add_argument("--workflow-id", default=DEFAULT_WF)
    parser.add_argument("--sample", type=int, default=3,
                        help="сколько первых запусков тянуть с токенами")
    parser.add_argument("--out", default=None,
                        help="сохранить отчёт JSON в файл")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    invoke = load_invoker()
    model_names = find_model_nodes(invoke, args.workflow_id)
    if not model_names:
        raise SystemExit("В схеме не найдено нод «Модель (…)»")
    print("Модельных нод в схеме: %d" % len(model_names))
    report = {}
    for execution_id in args.execution_id:
        report[execution_id] = show_execution(
            invoke, args.workflow_id, execution_id, model_names, args.sample)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        print("WROTE %s" % args.out)


if __name__ == "__main__":
    main()

