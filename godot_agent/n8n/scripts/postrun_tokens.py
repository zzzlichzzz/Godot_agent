# -*- coding: utf-8 -*-
"""Пост-прогонная токен-сводка цикла v3 (B2) — основа события «tokens».

Зачем. Живая токен-сводка внутри воркфлоу невозможна: usage моделей-суб-нод
попадает в базу n8n только ПОСЛЕ завершения исполнения, а каналы — вообще
отдельные исполнения (ядро их лишь запускает). Поэтому отчёт собирается
постфактум: сервер рук (:8010), получив событие kind=done c execution_id,
запускает этот скрипт фоном; скрипт ждёт завершения ядра, находит исполнения
волны (ядро + каналы), переиспользует scripts/token_report.py и печатает:
  - человекочитаемый отчёт (stdout);
  - финальную строку «TOKENS_JSON {...}» — компактную сводку для журнала
    моста «цикл → чат» (kind=tokens).

Запуск (из папки n8n; работает и вручную — fallback в духе token_report.py):
    python -B scripts/postrun_tokens.py 103 --workflow-id rIwvKxDNhOxodBCc
    python -B scripts/postrun_tokens.py 103 --wait-sec 0 --out tokens_103.json
"""

import argparse
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WF = "rIwvKxDNhOxodBCc"  # «Шаблон v3: Эконом + отказоустойчивость»
RUNNING_STATES = ("new", "running", "waiting")


def load_token_report():
    """Импортировать token_report.py из этой же папки (без пакета)."""
    path = os.path.join(HERE, "token_report.py")
    spec = importlib.util.spec_from_file_location("token_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def jnum(value):
    """Число с разделителями разрядов (1 234 567)."""
    return "{:,}".format(int(round(value))).replace(",", " ")


def wait_finished(invoke, workflow_id, execution_id, wait_sec):
    """Ждать, пока исполнение не в RUNNING_STATES (или истечёт wait_sec).

    Возвращает metadata исполнения ({id, status, startedAt, ...}).
    """
    deadline = time.time() + max(0, int(wait_sec))
    execution = {}
    while True:
        result = invoke.tool_result(invoke.call_tool(
            "get_workflow_execution", {
                "workflowId": workflow_id,
                "executionId": str(execution_id),
            })) or {}
        execution = result.get("execution") or execution
        status = str(execution.get("status") or "")
        if status and status not in RUNNING_STATES:
            return execution
        if time.time() >= deadline:
            return execution
        time.sleep(10)


def find_wave_executions(invoke, workflow_id, core):
    """Исполнения волны: каналы, стартовавшие после старта ядра (без ядра)."""
    result = invoke.tool_result(invoke.call_tool(
        "search_workflow_executions", {
            "workflowId": workflow_id,
            "startedAfter": str(core.get("startedAt") or ""),
            "limit": 20,
        })) or {}
    core_id = str(core.get("id") or "")
    ids = []
    for row in result.get("data") or []:
        rid = str(row.get("id") or "")
        if rid and rid != core_id:
            ids.append(rid)
    return ids


def aggregate(report):
    """Свод: вызовы, est prompt/completion и разбивка по моделям."""
    per_model = {}
    calls = 0
    prompt = 0.0
    completion = 0.0
    for item in report.values():
        for name, count in sorted((item.get("calls") or {}).items()):
            row = per_model.setdefault(
                name, {"calls": 0, "prompt": 0.0, "completion": 0.0, "sample": 0})
            row["calls"] += int(count or 0)
            calls += int(count or 0)
        for name, data in sorted((item.get("tokens") or {}).items()):
            row = per_model.setdefault(
                name, {"calls": 0, "prompt": 0.0, "completion": 0.0, "sample": 0})
            row["prompt"] += float(data.get("est_prompt_total") or 0)
            row["completion"] += float(data.get("est_completion_total") or 0)
            row["sample"] = int(data.get("sample") or 0)
            prompt += float(data.get("est_prompt_total") or 0)
            completion += float(data.get("est_completion_total") or 0)
    return {"calls": calls, "est_prompt": round(prompt),
            "est_completion": round(completion), "per_model": per_model}


def compact_text(summary, executions):
    """Компактная строка для события журнала (≤ ~900 символов)."""
    parts = ["вызовов %s" % jnum(summary["calls"]),
             "est prompt ~%s + completion ~%s" % (
                 jnum(summary["est_prompt"]), jnum(summary["est_completion"])),
             "исполнений волны: %d" % len(executions)]
    top = sorted(summary["per_model"].items(),
                 key=lambda kv: -(kv[1]["prompt"] + kv[1]["completion"]))[:5]
    for name, row in top:
        parts.append("%s: %s выз. (~%s+%s)"
                     % (name, jnum(row["calls"]), jnum(row["prompt"]),
                        jnum(row["completion"])))
    return (" | ".join(parts))[:900]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Токен-сводка прогона цикла v3")
    parser.add_argument("execution_id", help="id ядра прогона (execution_id финала)")
    parser.add_argument("--workflow-id", default=DEFAULT_WF)
    parser.add_argument("--wait-sec", type=int, default=600,
                        help="сколько ждать завершения ядра (0 — не ждать)")
    parser.add_argument("--sample", type=int, default=3,
                        help="подсказка MCP truncateData для запусков моделей")
    parser.add_argument("--out", default=None, help="сохранить полный отчёт в JSON")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    tr = load_token_report()
    invoke = tr.load_invoker()
    execution_id = str(args.execution_id).strip()
    core = wait_finished(invoke, args.workflow_id, execution_id, args.wait_sec)
    print("ядро %s: status=%s" % (execution_id, core.get("status") or "?"))
    wave = [execution_id] + find_wave_executions(invoke, args.workflow_id, core)
    print("исполнения волны: %s" % ", ".join(wave))

    model_names = tr.find_model_nodes(invoke, args.workflow_id)
    if not model_names:
        raise SystemExit("В схеме не найдено нод «Модель (…)»")
    report = {}
    for rid in wave:
        report[rid] = tr.show_execution(
            invoke, args.workflow_id, rid, model_names, args.sample)
    summary = aggregate(report)

    text = compact_text(summary, wave)
    print("СВОДКА: %s" % text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"core": execution_id, "wave": wave, "report": report,
                       "summary": summary, "text": text}, fh,
                      ensure_ascii=False, indent=1)
        print("WROTE %s" % args.out)
    print("TOKENS_JSON " + json.dumps(
        {"text": text, "calls": summary["calls"],
         "est_prompt": summary["est_prompt"],
         "est_completion": summary["est_completion"],
         "executions": wave},
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
