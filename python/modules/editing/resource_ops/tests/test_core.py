"""Independent native-derived cases; pure domain receives filesystem facts only."""
import json
from pathlib import Path

import pytest

from python.kernel.errors import AppError
from python.modules.editing.resource_ops.domain import core

CORPUS = Path(__file__).resolve().parents[5] / "fixtures/corpus/editing/resource_ops"
RECORDS = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CORPUS.glob("[0-9]*.json"))]
PURE = [r for r in RECORDS if r["internal_call"]["entrypoint"] == "normalize_action"]


def facts(record):
    project = CORPUS / "projects" / record["fixture"]
    paths = {"res://" + p.relative_to(project).as_posix(): {
        "relative": p.relative_to(project).as_posix(), "contained": True,
        "is_file": p.is_file()} for p in project.rglob("*")}
    paths["res://"] = {"relative": ".", "contained": True, "is_file": False}
    if "res://old.tres" in paths:
        paths["res://unused/../old.tres"] = paths["res://old.tres"]
    for key, value in list(paths.items()):
        paths["res://./" + key[6:]] = value
    for prefix in ("addons/tool/private.tres", "addons/godot_agent/private.tres",
                   ".agent_history/data.tres", "project.godot"):
        paths["res://" + prefix.upper()] = paths.get("res://" + prefix, {
            "relative": prefix, "contained": True, "is_file": False})
    return paths


@pytest.mark.parametrize("record", PURE, ids=lambda r: r["id"])
def test_native_pure(record):
    try:
        normalized, rel = core.normalize_action(facts(record), record["input"], **record["kwargs"])
        answer = {"ok": True, "result": {"action": normalized, "target": "res://" + rel}}
    except AppError as exc:
        answer = dict(exc.payload(), ok=False)
    assert answer == record["expect"]
