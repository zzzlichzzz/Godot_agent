"""tests/py/integration/test_write_preview_flow.py - воронка на поддельных портах.

Проверяется последовательность «поиск → компилятор → WAL»: план строится из
отчёта `analyze_rename` (его подменяет `call_tool`), журнал получает ровно одну
запись `PREPARED`, а файлы в памяти остаются прежними. Диск и Godot не нужны:
порты приносит тот, кто собирает контекст (ADR-0003).
"""

import json

import pytest

from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.modules.editing.write_preview import app
from python.runtime.context import ModuleContext
from python.substrate.fs.memory_fs import MemoryFileSystem

HERO = "res://src/hero.gd"
OTHER = "res://src/other.gd"
FILES = {
    "src/hero.gd": "func take_damage(x):\n\treturn x\n",
    "src/other.gd": "extends LabHero\n\nfunc hit(target) -> void:\n"
                    "\ttarget.take_damage(1)\n",
}
ANALYSIS = {
    "kind": "function", "old_name": "take_damage", "new_name": "apply_damage",
    "declaration": HERO + ":1", "declaration_path": HERO, "declaration_line": 1,
    "mode": "strict", "allow_unverified": False, "risks": [],
    "usages": [
        {"path": HERO, "line": 1, "column": 6, "link": "declaration",
         "confidence": "proven", "note": None},
        {"path": OTHER, "line": 4, "column": 9, "link": "member",
         "confidence": "probable", "note": "тип не доказан"},
    ],
}


class _Journal(object):
    """Поддельный WAL: помнит записи и путь, как `FileJournal`."""

    def __init__(self):
        self.records = {}

    def write_prepared(self, plan, detail=None):
        self.records[plan["plan_id"]] = {"state": "PREPARED", "plan": plan,
                                         "detail": dict(detail or {})}
        return "<fake>/%s.jsonl" % plan["plan_id"]

    def read(self, plan_id):
        record = self.records.get(plan_id)
        return [record] if record else []


def _context(journal, answer=ANALYSIS):
    calls = []

    def call_tool(name, args):
        calls.append((name, dict(args)))
        return dict(answer)

    ctx = ModuleContext(profile="test", ports={"fs": MemoryFileSystem(FILES),
                                               "journal": journal},
                        path_policy=PathPolicy(""), call_tool=call_tool)
    ctx.calls = calls
    return ctx


def _run(ctx, **extra):
    args = {"kind": "function", "old_name": "take_damage",
            "new_name": "apply_damage", "declaration": HERO + ":1"}
    args.update(extra)
    return app.call("write_preview", args, ctx)


def test_plan_is_built_from_the_existing_search():
    journal = _Journal()
    ctx = _context(journal)
    result = _run(ctx, allow_unverified=True)
    assert ctx.calls and ctx.calls[0][0] == "analyze_rename", "R-04: не свой поиск"
    assert result["steps_count"] == 2
    assert result["affected_paths"] == [HERO, OTHER]


def test_journal_gets_exactly_one_prepared_record():
    journal = _Journal()
    result = _run(_context(journal), allow_unverified=True)
    record = journal.records[result["plan_id"]]
    assert record["state"] == "PREPARED"
    plan = record["plan"]
    assert plan["digest"] == result["digest"]
    assert plan["state"] == "PREPARED"
    assert sorted(plan["expected"]) == [HERO, OTHER]
    assert [step["target"] for step in plan["steps"]] == [HERO, OTHER]
    assert json.loads(json.dumps(plan, ensure_ascii=False)) == plan


def test_project_files_are_not_touched():
    fs = MemoryFileSystem(FILES)
    ctx = ModuleContext(profile="test", ports={"fs": fs, "journal": _Journal()},
                        path_policy=PathPolicy(""), call_tool=lambda n, a: ANALYSIS)
    _run(ctx, allow_unverified=True)
    assert {path: fs.read_text(path) for path in fs.list_files()} == FILES


def test_refusal_writes_no_journal_record():
    journal = _Journal()
    with pytest.raises(AppError) as caught:
        _run(_context(journal))
    assert caught.value.kind == "conflict"
    assert journal.records == {}, "кейс 4: при отказе WAL не создаётся"


def test_foreign_tool_is_rejected():
    with pytest.raises(AppError) as caught:
        app.call("usages", {}, _context(_Journal()))
    assert caught.value.kind == "unknown_tool"
