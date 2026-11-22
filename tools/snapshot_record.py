#!/usr/bin/env python
"""tools/snapshot_record.py - снятие эталона со старого агента (R-07).

Читает кейсы корпуса (`fixtures/corpus/<область>/<фича>/*.json`, в каждом уже
записаны `fixture` и `args`), вызывает ЭТАЛОН отдельным процессом с `-B` и
дописывает в кейс `expect` — наблюдаемый результат старого агента.

    python tools/snapshot_record.py \
        --corpus fixtures/corpus/project_text/search \
        --reference D:\\...\\Godot_agent\\godot_agent\\python

Нормализация обязательна (R-07, SEC-13): корень проекта заменяется на
`<PROJECT>`, любой оставшийся абсолютный путь — ошибка записи, а не «мелочь».
Манифест фиксирует дату, хеш кейсов и хеш эталонного файла: без этого
`snapshot_diff` не знает, с чем сравнивает.

Код возврата: 0 - корпус снят, 1 - ошибка записи/вызова, 2 - нечего снимать.
Последняя строка stdout - JSON вердикта (контракт R-18).
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "_reference_runner.py"
MANIFEST = "manifest.json"
ABS_PATH = re.compile(r"(?<![<\w])[A-Za-z]:[\\/]")


def verdict(status, detail):
    print(json.dumps({"status": status, "detail": detail}, ensure_ascii=False))
    return 0 if status == "ok" else 1


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def case_files(corpus):
    return [p for p in sorted(corpus.glob("*.json")) if p.name != MANIFEST]


def pycache_snapshot(base):
    base = Path(base)
    return {str(p.relative_to(base)) for p in base.rglob("__pycache__")}


def normalise(value, project_root):
    """Абсолютные пути -> `<PROJECT>`; другие абсолютные пути недопустимы."""
    variants = {str(project_root), str(project_root).replace("\\", "/"),
                str(project_root).replace("/", "\\"), os.path.realpath(project_root)}
    if isinstance(value, str):
        for item in variants:
            value = value.replace(item, "<PROJECT>")
            value = value.replace(item.replace("\\", "/"), "<PROJECT>")
        if ABS_PATH.search(value):
            raise ValueError("абсолютный путь в корпусе: %r" % value)
        return value
    if isinstance(value, list):
        return [normalise(item, project_root) for item in value]
    if isinstance(value, dict):
        return {key: normalise(item, project_root) for key, item in value.items()}
    return value


def run_reference(reference, tool, args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    argv = [sys.executable, "-B", str(RUNNER), str(reference), tool,
            json.dumps(args, ensure_ascii=False)]
    done = subprocess.run(argv, capture_output=True, timeout=300,
                          encoding="utf-8", errors="replace", env=env)
    if done.returncode != 0:
        raise RuntimeError("эталон вернул %d: %s"
                           % (done.returncode, (done.stderr or "").strip()[-400:]))
    return json.loads(done.stdout.strip().splitlines()[-1])


def expect_of(raw, project_root):
    """Ответ эталона -> `expect`.

    Отказ (`{"ok": false, "kind": ...}`) записывается без текста ошибки: тексты
    старого агента не переносятся, переносится класс отказа (R-15).
    """
    if isinstance(raw, dict) and raw.get("ok") is False:
        return {"ok": False, "kind": str(raw.get("kind") or "internal")}
    return {"ok": True, "result": normalise(raw, project_root)}


#: Какой эталонный код отвечает за механику: `tool` в кейсе -> (что вызвано, файл для sha256).
REFERENCES = {
    "search": ("godot_tools/project_tools.py:search_project_text",
               "godot_tools/project_tools.py"),
    "functions": ("godot_tools/gd_functions.py:list_functions/extract_functions",
                  "godot_tools/gd_functions.py"),
    "usages": ("godot_tools/symbol_refactor.py:find_references",
               "godot_tools/symbol_refactor_part2.py"),
    "analyze_rename": ("godot_tools/symbol_refactor.py:analyze_rename",
                       "godot_tools/symbol_refactor_part2.py"),
    "write_preview": ("godot_tools/symbol_refactor.py:prepare_rename",
                      "godot_tools/symbol_refactor_part3.py"),
    "write_apply": ("godot_tools/symbol_refactor.py:prepare_rename+apply_prepared_rename",
                    "godot_tools/symbol_refactor_part3.py"),
    "write_rollback": ("godot_tools/symbol_refactor.py:prepare_rename (before_bytes)",
                       "godot_tools/symbol_refactor_part3.py"),
}


def reference_block(tools, reference):
    """Манифест: один инструмент — один `source`; несколько — список `sources`."""
    unknown = sorted(tools - set(REFERENCES))
    if unknown:
        raise ValueError("нет эталона для механики: %s" % ", ".join(unknown))
    if len(tools) == 1:
        source, file_name = REFERENCES[sorted(tools)[0]]
        return {"source": source, "sha256": sha256_file(reference / file_name)}
    return {"sources": [{"tool": tool, "source": REFERENCES[tool][0],
                         "sha256": sha256_file(reference / REFERENCES[tool][1])}
                        for tool in sorted(tools)]}

def main(argv):
    parser = argparse.ArgumentParser(description="снять эталон корпуса (R-07)")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--reference", required=True,
                        help="путь к старому python/ (только чтение, R-08)")
    parser.add_argument("--fixture-root", default="fixtures/projects")
    parser.add_argument("--date", default=None, help="дата съёмки (по умолчанию сегодня)")
    options = parser.parse_args(argv)

    corpus = Path(options.corpus)
    if not corpus.is_absolute():
        corpus = ROOT / corpus
    reference = Path(options.reference)
    fixture_root = Path(options.fixture_root)
    if not fixture_root.is_absolute():
        fixture_root = ROOT / fixture_root

    files = case_files(corpus)
    if not files:
        sys.stderr.write("нет файлов кейсов в %s\n" % corpus)
        return verdict("not_implemented", "корпус пуст: %s" % options.corpus)

    before = pycache_snapshot(reference)
    entries = []
    failures = []
    tools_used = set()
    for path in files:
        record = json.loads(path.read_text(encoding="utf-8"))
        fixture = record.get("fixture") or "minimal"
        project_root = fixture_root / fixture
        if not (project_root / "project.godot").is_file():
            failures.append("%s: нет проекта %s" % (path.name, project_root))
            continue
        call_args = dict(record.get("args") or {})
        call_args["project_root"] = str(project_root)
        tool = record.get("tool") or "search"
        try:
            raw = run_reference(reference, tool, call_args)
            expect = expect_of(raw, project_root)
        except (RuntimeError, ValueError) as exc:
            failures.append("%s: %s" % (path.name, exc))
            continue
        record["expect"] = expect
        record["tool"] = tool
        record["fixture"] = fixture
        tools_used.add(tool)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        entries.append({"id": record.get("id") or path.stem,
                        "file": path.name,
                        "fixture": fixture,
                        "sha256": sha256_file(path)})

    after = pycache_snapshot(reference)
    leaked = sorted(after - before)
    if leaked:
        failures.append("эталон получил __pycache__: %s" % ", ".join(leaked))

    manifest = {
        "schema_version": 1,
        "corpus": _rel(corpus),
        "captured_at": options.date or datetime.now(timezone.utc).date().isoformat(),
        "reference": reference_block(tools_used, reference),
        "fixture_root": _rel(fixture_root),
        "cases": entries,
    }
    (corpus / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if failures:
        for line in failures:
            print("  " + line)
        return verdict("fail", "%d кейсов не сняты" % len(failures))
    print("  кейсов: %d" % len(entries))
    return verdict("ok", "корпус снят: %d кейсов" % len(entries))


def _rel(path):
    try:
        return str(Path(path).relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

