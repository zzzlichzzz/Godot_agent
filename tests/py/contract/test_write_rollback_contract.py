"""tests/py/contract/test_write_rollback_contract.py - контракт отката.

`write_rollback` возвращает проект к байтам до применения по `entry_id`.
Проверяется поверхность (`entry_id` один и обязателен), объявленные отказы,
`conflict` с причиной на повторном откате и правке после применения,
побайтовое восстановление на копии фикстуры.
"""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from python.kernel.errors import KINDS
from python.modules.editing.rollback import module as rollback_module
from python.modules.editing.rollback import tools as rollback_tools
from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "projects" / "rename"
SPEC = rollback_tools.WRITE_ROLLBACK
CAPABILITY = ROOT / "contract" / "capabilities" / "write_rollback.json"
ABS_PATH = re.compile(r"\b[A-Za-z]:[\\/]")
RENAME = {"kind": "function", "old_name": "strike", "new_name": "punch",
          "declaration": "res://src/hero.gd:10"}


def _agent(tmp_path):
    project = tmp_path / "project"
    if not project.exists():
        shutil.copytree(str(FIXTURE), str(project))
    return build_agent(project_root=str(project), profile="test",
                       state_dir=str(tmp_path / "state"))


def _committed(tmp_path):
    agent = _agent(tmp_path)
    plan = agent.call("write_preview", dict(RENAME))["result"]
    applied = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                         "digest": plan["digest"]})["result"]
    return agent, applied


def test_tool_name_effects_and_idempotency():
    assert SPEC.name == "write_rollback"
    assert SPEC.effects == "write"
    assert SPEC.idempotent is True
    assert SPEC.cost == "heavy"


def test_declared_errors_are_stable_kinds():
    assert SPEC.errors == ("invalid_input", "not_found", "conflict", "denied",
                           "internal")
    assert set(SPEC.errors) <= set(KINDS)


def test_args_schema_needs_entry_id():
    schema = SPEC.args
    assert schema["required"] == ["entry_id"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["entry_id"]["minLength"] == 1


def test_result_schema_pins_the_report():
    schema = SPEC.result
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"entry_id", "state", "plan_id", "restored",
                                       "removed", "files_count"}
    assert schema["properties"]["state"]["enum"] == ["ROLLED_BACK"]
    assert schema["properties"]["restored"]["items"]["required"] == ["path", "hash"]


def test_manifest_declares_the_tool():
    manifest = rollback_module.MODULE
    assert manifest.id == "editing.rollback"
    assert tuple(manifest.provides_tools) == ("write_rollback",)
    assert set(manifest.requires_ports) == {"writer", "journal", "backups", "lock"}
    assert "editing.write_apply" in tuple(manifest.requires)
    assert tuple(manifest.provides_tools) == tuple(
        tool.name for tool in rollback_tools.TOOLS)


def test_generated_contract_matches_the_spec():
    assert CAPABILITY.is_file(), "python tools/gen_contract.py --write"
    artifact = json.loads(CAPABILITY.read_text(encoding="utf-8"))
    assert artifact["tool_name"] == SPEC.name
    assert artifact["effects"] == ["write"]
    assert artifact["input_schema"] == SPEC.args
    assert artifact["result_schema"] == SPEC.result

def test_rollback_restores_the_bytes_and_reports_hashes(tmp_path):
    agent, applied = _committed(tmp_path)
    hero = tmp_path / "project" / "src" / "hero.gd"
    answer = agent.call("write_rollback", {"entry_id": applied["entry_id"]})
    assert answer["ok"], answer
    result = answer["result"]
    assert result["state"] == "ROLLED_BACK"
    assert result["entry_id"] == applied["entry_id"]
    assert [item["path"] for item in result["restored"]] == ["res://src/hero.gd"]
    assert result["restored"][0]["hash"] == hashlib.sha256(
        hero.read_bytes()).hexdigest()
    assert result["files_count"] == 1 and result["removed"] == []
    assert b"func strike" in hero.read_bytes() and b"punch" not in hero.read_bytes()
    flat = json.dumps(result, ensure_ascii=False)
    assert "Traceback" not in flat and not ABS_PATH.search(flat)


@pytest.mark.parametrize("entry_id, kind", [
    ("", "invalid_input"),
    ("plan_nope#1", "not_found"),
    ("plan#0", "invalid_input"),
])
def test_refusals_keep_their_kind(tmp_path, entry_id, kind):
    agent = _agent(tmp_path)
    answer = agent.call("write_rollback", {"entry_id": entry_id})
    assert answer["ok"] is False and answer["kind"] == kind
    assert "Traceback" not in json.dumps(answer, ensure_ascii=False)


def test_edit_after_apply_blocks_rollback_without_restore(tmp_path):
    agent, applied = _committed(tmp_path)
    hero = tmp_path / "project" / "src" / "hero.gd"
    hero.write_bytes(hero.read_bytes() + b"\n# later\n")
    changed = hashlib.sha256(hero.read_bytes()).hexdigest()
    answer = agent.call("write_rollback", {"entry_id": applied["entry_id"]})
    assert answer["ok"] is False and answer["kind"] == "conflict"
    assert answer["details"]["reason"] == "post_state_mismatch"
    assert answer["details"]["path"] == "res://src/hero.gd"
    assert hashlib.sha256(hero.read_bytes()).hexdigest() == changed, "не восстанавливаем"