# -*- coding: utf-8 -*-
"""Сверка снимка в schemas/ с текущим состоянием базы n8n.

Зачем. schemas/template_v2_core_4_channels.json — источник схемы фабрики для
выпусков. Скрипт подтверждает, что файл в репозитории совпадает с тем, что
сейчас лежит в локальной базе n8n (снимок не отстал от правок в редакторе).

Запуск (из папки n8n):
    python -B scripts/verify_snapshot.py

Код возврата: 0 — совпадает, 1 — расходится (или ошибка).
"""

import argparse
import importlib.util
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_exporter():
    """Импортировать export_workflow.py из этой же папки (без пакета)."""
    path = os.path.join(HERE, "export_workflow.py")
    spec = importlib.util.spec_from_file_location("export_workflow", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    ew = load_exporter()
    parser = argparse.ArgumentParser(
        description="Сверка снимка schemas/ с текущей базой n8n")
    parser.add_argument("--db", default=os.environ.get("N8N_DB", ew.DEFAULT_DB))
    parser.add_argument("--workflow-id", default=ew.DEFAULT_ID)
    parser.add_argument("--file", default=ew.DEFAULT_OUT)
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

    if not os.path.isfile(args.db):
        raise SystemExit("База n8n не найдена: %s" % args.db)
    if not os.path.isfile(args.file):
        raise SystemExit("Снимок не найден: %s" % args.file)

    con, tmp = ew.open_snapshot(args.db)
    try:
        table = ew.find_table(con)
        rows = ew.load_rows(con, table, args.workflow_id)
        if not rows:
            raise SystemExit("Воркфлоу %s в базе не найден" % args.workflow_id)
        doc = ew.compose(rows[0])
        version_id = (rows[0]["versionId"]
                      if "versionId" in rows[0].keys() else None)
    finally:
        con.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    with open(args.file, encoding="utf-8") as fh:
        snapshot = json.load(fh)

    if snapshot == doc:
        print("Совпадает: %s == текущая база n8n" % args.file)
        print("  узлов: %d | versionId: %s" % (len(doc["nodes"]), version_id))
        return 0

    print("РАСХОЖДЕНИЕ: %s != текущая база n8n" % args.file)
    for key in sorted(set(list(snapshot) + list(doc))):
        if snapshot.get(key) != doc.get(key):
            print("  отличается ключ: %s" % key)
    print("Обновите снимок: python -B scripts/export_workflow.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
