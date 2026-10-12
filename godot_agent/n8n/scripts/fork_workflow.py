# -*- coding: utf-8 -*-
"""Форк воркфлоу n8n: копия текущего черновика с новым id и именем.

Зачем. Основная схема («Шаблон v2: Ядро + 4 канала») остаётся рабочей —
её вебхуки активны. Новая ветка правок (например, v3: экономия и
отказоустойчивость) делается форком: копия получает собственный id и имя,
записывается в schemas/ и импортируется в тот же n8n
(`scripts\\import_workflow.cmd`). Импорт создаёт НОВЫЙ воркфлоу-черновик,
не активный; исходная схема не затрагивается.

Источник — живая база n8n (как в export_workflow.py): форк снимается с
текущего черновика, а не с файла, чтобы не разойтись с базой.

Безопасность. База читается ТОЛЬКО для чтения; ключей в снимке нет —
только ссылки на креденшелы. id копии генерируется и проверяется на
коллизию по всем воркфлоу базы.

Запуск (из папки n8n):
    python -B scripts/fork_workflow.py --name "Шаблон v3: ..." --out schemas/template_v3_....json
    python -B scripts/fork_workflow.py --id <источник> --name <имя> --out <файл>

Дальше:
    scripts\\import_workflow.cmd "<абс. путь к файлу копии>"
    python -B scripts/verify_snapshot.py --workflow-id <id копии> --file <файл копии>
"""

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import string
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ID_ALPHABET = string.ascii_letters + string.digits
ID_LEN = 16


def load_exporter():
    """Импортировать export_workflow.py из этой же папки (без пакета)."""
    path = os.path.join(HERE, "export_workflow.py")
    spec = importlib.util.spec_from_file_location("export_workflow", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_id(existing):
    """Случайный id в формате n8n (nanoid-подобный, 16 символов)."""
    while True:
        candidate = "".join(secrets.choice(ID_ALPHABET)
                            for _ in range(ID_LEN))
        if candidate not in existing:
            return candidate


def main(argv=None):
    ew = load_exporter()
    parser = argparse.ArgumentParser(
        description="Форк воркфлоу n8n: копия с новым id и именем")
    parser.add_argument("--db", default=os.environ.get("N8N_DB", ew.DEFAULT_DB),
                        help="путь к database.sqlite (по умолчанию ~/.n8n)")
    parser.add_argument("--id", dest="source_id", default=ew.DEFAULT_ID,
                        help="id воркфлоу-источника")
    parser.add_argument("--name", required=True, help="имя копии")
    parser.add_argument("--out", required=True, help="файл-назначение копии")
    parser.add_argument("--new-id", default=None,
                        help="id копии (по умолчанию генерируется)")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

    if not os.path.isfile(args.db):
        raise SystemExit("База n8n не найдена: %s" % args.db)

    con, tmp = ew.open_snapshot(args.db)
    try:
        table = ew.find_table(con)
        rows = ew.load_rows(con, table, args.source_id)
        if not rows:
            raise SystemExit("Воркфлоу %s в базе не найден" % args.source_id)
        doc = ew.compose(rows[0])
        existing = {row["id"] for row in ew.load_rows(con, table, None)}
    finally:
        con.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    source_name = doc.get("name")
    new_id = args.new_id or make_id(existing)
    if new_id in existing:
        raise SystemExit("id %s уже занят другим воркфлоу" % new_id)

    doc["id"] = new_id
    doc["name"] = args.name

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print("Записан форк: %s" % out_path)
    print("  источник: %s  («%s»)" % (args.source_id, source_name))
    print("  копия:    %s  («%s»)" % (new_id, args.name))
    print("  узлов:    %d" % len(doc["nodes"]))
    print("  связок:   %d" % len(doc.get("connections") or {}))
    print("Дальше: scripts\\import_workflow.cmd \"%s\"" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
