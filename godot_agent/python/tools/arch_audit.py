# -*- coding: utf-8 -*-
"""arch_audit.py — сводка архитектуры агента по docs/architecture_map.json.

Зачем. Гейт моста (agent_bridge, режим agent-dev) видит только НОВЫЕ файлы;
уже накопленные дубли имён он не замечает. Этот скрипт — периодическая
проверка всего дерева: где публичное имя встречается и в ядре, и вне ядра;
где одно имя живёт у двух и более файлов-потребителей; какие .py не покрыты
картой архитектуры (файл не на своём месте); какие .py/.gd переросли лимит
строк (чистота проекта). Отчёт читает человек; ничего не меняется.

Запуск из python/ (или откуда угодно — аддон берётся от самого файла,
можно переопределить --addon):
    python -B tools/arch_audit.py
    python -B tools/arch_audit.py --addon <путь к аддону>

Код возврата: 0 — чисто; 2 — найдены замечания (это ОТЧЁТ, не сбой);
3 — карта недоступна или ошибка чтения.
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PYTHON_DIR = os.path.dirname(_HERE)
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)
import _bootstrap  # noqa: E402,F401

RC_OK = 0
RC_FINDINGS = 2
RC_ERROR = 3

MAX_ROWS = 60


def _print_section(title, rows):
    print("== %s (%d) ==" % (title, len(rows)))
    for row in rows[:MAX_ROWS]:
        print("  %s" % row)
    if len(rows) > MAX_ROWS:
        print("  … ещё %d" % (len(rows) - MAX_ROWS))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Сводка архитектуры агента (только чтение).")
    parser.add_argument("--addon", default="",
                        help="каталог аддона (по умолчанию — родитель python/)")
    parser.add_argument("--json", default="",
                        help="сохранить отчёт в JSON-файл")
    args = parser.parse_args(argv)

    addon = str(args.addon or os.path.dirname(_PYTHON_DIR))
    import arch_map

    map_data = arch_map.load_map(addon)
    if map_data is None:
        print("arch_audit: карта не найдена или битая: %s"
              % os.path.join(addon, "docs", "architecture_map.json"))
        return RC_ERROR
    print("map: %s (зон: %d, ядро: %s)"
          % (os.path.join(addon, "docs", "architecture_map.json"),
             len(map_data.get("zones") or []), arch_map.core_dir_of(map_data).rstrip("/")))
    report = arch_map.audit(addon, map_data=map_data)
    print("файлов .py в индексе: %d; публичных имён: %d"
          % (len(arch_map._py_signature(addon)), report["count"]))

    core_rows = ["%s: ядро [%s]; вне ядра [%s]"
                 % (item["name"], ", ".join(item["core"]),
                    ", ".join(item["outside"]))
                 for item in report["core_duplicates"]]
    consumer_rows = ["%s: %s" % (item["name"], ", ".join(item["files"]))
                     for item in report["consumer_duplicates"]]
    unknown_rows = list(report["unknown_files"])
    policy = report.get("line_policy") or {}
    large_rows = ["%s: %d строк%s"
                  % (item["rel"], item["lines"],
                     " — БОЛЬШЕ ЛИМИТА, раздели на модули"
                     if item.get("over_max") else "")
                  for item in report.get("large_files") or []]
    _print_section("дубли «ядро ↔ потребители»", core_rows)
    _print_section("одно имя у нескольких файлов вне ядра", consumer_rows)
    _print_section("файлы вне зон карты (не на своём месте)", unknown_rows)
    _print_section("крупные файлы (>= %s строк; лимит %s)"
                   % (policy.get("warn", "?"), policy.get("max", "?")),
                   large_rows)

    if args.json:
        try:
            with open(args.json, "w", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
            print("json: %s" % args.json)
        except OSError as exc:
            print("arch_audit: не смог записать json: %s" % exc)
            return RC_ERROR

    findings = (len(core_rows) + len(consumer_rows) + len(unknown_rows)
                + len(large_rows))
    if findings:
        print("итог: %d замечание(й) — решай по каждой: слить в ядро, "
              "переименовать, разбить крупный файл на модули или внести "
              "осознанное исключение в карту" % findings)
        return RC_FINDINGS
    print("итог: чисто — дублей имён, файлов вне зон и крупных файлов нет")
    return RC_OK


if __name__ == "__main__":
    sys.exit(main())
