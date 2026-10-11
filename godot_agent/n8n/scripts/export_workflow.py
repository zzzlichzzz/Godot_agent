# -*- coding: utf-8 -*-
"""Снимок воркфлоу n8n из локальной SQLite-базы — в n8n/schemas.

Зачем. Схема фабрики («Шаблон v2: Ядро + 4 канала») разрабатывается в
веб-редакторе n8n, а версионируется вместе с плагином в этом репозитории.
Скрипт снимает текущий черновик воркфлоу из базы n8n (те же nodes/
connections/settings/meta, что и у официального `n8n export:workflow`,
минус рантайм-поля вроде shared/triggerCount/versionCounter) — напрямую и
мгновенно (n8n CLI стартует десятки секунд, базе это не нужно).

Безопасность. База открывается ТОЛЬКО для чтения, и берётся одна строка
workflow_entity (nodes/connections/settings/pinData/meta/nodeGroups). Таблица
credentials не читается вовсе, так что в снимок попадают лишь ССЫЛКИ на
креденшелы (id + имя) — без ключей. Перед коммитом прогоняйте
check_no_secrets.py по папке n8n/.

Запуск (из папки n8n):
    python -B scripts/export_workflow.py               # схема по умолчанию
    python -B scripts/export_workflow.py --list        # что есть в базе n8n
    python -B scripts/export_workflow.py --workflow-id <ID> --out <файл.json>
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".n8n", "database.sqlite")
DEFAULT_ID = "v81fH05KY5uKUNK0"  # «Шаблон v2: Ядро + 4 канала»
DEFAULT_OUT = os.path.normpath(os.path.join(
    HERE, "..", "schemas", "template_v2_core_4_channels.json"))

TEXT_COLUMNS = ("nodes", "connections", "settings", "pinData", "meta",
                "nodeGroups")


def open_snapshot(db_path):
    """Открыть базу только для чтения; при отказе WAL — через копию.

    Инстанс n8n держит database.sqlite открытой на запись, поэтому основная
    попытка — mode=ro. Если SQLite не может открыть WAL-базу read-only,
    делаем временную копию db+wal+shm и читаем копию.

    Возвращает (connect, временная_папка_или_None).
    """
    uri = "file:%s?mode=ro" % db_path.replace("\\", "/")
    try:
        return sqlite3.connect(uri, uri=True), None
    except sqlite3.Error:
        pass
    tmp = tempfile.mkdtemp(prefix="n8n_snapshot_")
    base = os.path.basename(db_path)
    for suffix in ("", "-wal", "-shm"):
        src = db_path + suffix
        if os.path.isfile(src):
            try:
                shutil.copy(src, os.path.join(tmp, base + suffix))
            except OSError:
                pass
    return sqlite3.connect(os.path.join(tmp, base)), tmp


def find_table(con):
    """Имя таблицы воркфлоу: сначала workflow_entity, потом любая с nodes."""
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    if "workflow_entity" in tables:
        return "workflow_entity"
    for table in tables:
        cols = [r[1] for r in con.execute("PRAGMA table_info(%s)" % table)]
        if "nodes" in cols and "connections" in cols:
            return table
    raise SystemExit("В базе не найдена таблица воркфлоу (nodes/connections)")


def load_rows(con, table, workflow_id):
    con.row_factory = sqlite3.Row
    cols = [r[1] for r in con.execute("PRAGMA table_info(%s)" % table)]
    wanted = ("id", "name", "nodes", "connections", "settings", "pinData",
              "meta", "nodeGroups", "versionId", "active", "updatedAt")
    sel = ", ".join(c for c in wanted if c in cols)
    if workflow_id:
        return con.execute("SELECT %s FROM %s WHERE id=?" % (sel, table),
                           (workflow_id,)).fetchall()
    return con.execute("SELECT %s FROM %s" % (sel, table)).fetchall()


def compose(row):
    """Строка базы -> документ формата n8n-экспорта (ссылки, без секретов)."""
    keys = row.keys()
    doc = {"id": row["id"], "name": row["name"]}
    for col in TEXT_COLUMNS:
        if col not in keys:
            continue
        raw = row[col]
        value = json.loads(raw) if raw else None
        if col == "settings":
            doc[col] = value or {}
        elif value:
            doc[col] = value  # пустые pinData/meta — рантайм-состояние, не храним
    return doc


def node_count(row):
    if "nodes" not in row.keys() or not row["nodes"]:
        return 0
    try:
        return len(json.loads(row["nodes"]))
    except ValueError:
        return -1


def print_list(rows):
    for row in sorted(rows, key=lambda r: r["name"] or ""):
        marks = []
        if "active" in row.keys():
            marks.append("active" if row["active"] else "draft")
        if "versionId" in row.keys() and row["versionId"]:
            marks.append(str(row["versionId"])[:8])
        if "updatedAt" in row.keys() and row["updatedAt"]:
            marks.append(str(row["updatedAt"]))
        print("%s  %-42s  узлов: %-4s  %s" % (
            row["id"], row["name"], node_count(row), "  ".join(marks)))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Снимок воркфлоу n8n из локальной SQLite-базы в n8n/schemas")
    parser.add_argument("--db", default=os.environ.get("N8N_DB", DEFAULT_DB),
                        help="путь к database.sqlite (по умолчанию ~/.n8n)")
    parser.add_argument("--list", action="store_true",
                        help="показать воркфлоу, которые есть в базе")
    parser.add_argument("--workflow-id", default=DEFAULT_ID,
                        help="id воркфлоу для экспорта")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="файл-назначение (по умолчанию schemas/...)")
    args = parser.parse_args(argv)
    # Консоль Windows бывает в cp1251: редкие символы не должны ронять вывод.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

    if not os.path.isfile(args.db):
        raise SystemExit("База n8n не найдена: %s" % args.db)

    con, tmp = open_snapshot(args.db)
    try:
        table = find_table(con)
        if args.list:
            print_list(load_rows(con, table, None))
            return 0
        rows = load_rows(con, table, args.workflow_id)
        if not rows:
            raise SystemExit("Воркфлоу %s в базе не найден" % args.workflow_id)
        doc = compose(rows[0])
        version_id = (rows[0]["versionId"]
                      if "versionId" in rows[0].keys() else None)
    finally:
        con.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    types = Counter(node.get("type") for node in doc["nodes"])
    print("Записан снимок: %s" % out_path)
    print("  id:        %s" % doc["id"])
    print("  имя:       %s" % doc["name"])
    print("  узлов:     %d" % len(doc["nodes"]))
    print("  связок:    %d (источников в connections)" % len(doc["connections"]))
    print("  размер:    %.1f КБ" % (os.path.getsize(out_path) / 1024.0))
    if version_id:
        print("  versionId: %s" % version_id)
    print("  типы:      %s" % ", ".join(
        "%s: %d" % (t, c) for t, c in types.most_common(8)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
