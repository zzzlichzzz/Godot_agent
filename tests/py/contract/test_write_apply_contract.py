"""tests/py/contract/test_write_apply_contract.py - контракт применения плана.

`write_apply` — единственное место, где агент меняет файлы проекта (R-12).
Проверяется клиентская поверхность: схемы, объявленные отказы, обязательный
`details.reason` у `conflict`, честные `stale_plan`, синхронность артефакта
`contract/capabilities/write_apply.json` и отсутствие абсолютных путей.
Эффекты выполняются на копии фикстуры в `tmp_path`, рабочее дерево не трогается.
"""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from python.kernel.errors import KINDS, AppError
from python.modules.editing.write_apply import module as apply_module
from python.modules.editing.write_apply import tools as apply_tools
from python.protocol.validation import validate_args
from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "projects" / "rename"
SPEC = apply_tools.WRITE_APPLY
CAPABILITY = ROOT / "contract" / "capabilities" / "write_apply.json"
ABS_PATH = re.compile(r"\b[A-Za-z]:[\\/]")
RENAME = {"kind": "function", "old_name": "strike", "new_name": "punch",
          "declaration": "res://src/hero.gd:10"}


def _agent(tmp_path, **extra):
    project = tmp_path / "project"
    if not project.exists():
        shutil.copytree(str(FIXTURE), str(project))
    if extra:
        RENAME.update(extra)
    return build_agent(project_root=str(project), profile="test",
                       state_dir=str(tmp_path / "state"))


def _prepared(tmp_path):
    agent = _agent(tmp_path)
    plan = agent.call("write_preview", dict(RENAME))["result"]
    return agent, plan


def _applied(tmp_path):
    agent, plan = _prepared(tmp_path)
    answer = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                        "digest": plan["digest"]})
    return agent, plan, answer


def test_tool_name_effects_and_idempotency():
    assert SPEC.name == "write_apply"
    assert SPEC.effects == "write", "единственная механика записи (R-12)"
    assert SPEC.idempotent is True, "ADR-0005: повтор с тем же digest без эффекта"
    assert SPEC.availability == "*"
    assert SPEC.cost == "heavy"


def test_declared_errors_are_stable_kinds():
    assert SPEC.errors == ("invalid_input", "not_found", "stale_plan", "conflict",
                           "denied", "internal")
    assert set(SPEC.errors) <= set(KINDS)


def test_args_schema_needs_plan_and_digest():
    schema = SPEC.args
    assert schema["required"] == ["plan_id", "digest"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"plan_id", "digest"}


def test_result_schema_pins_the_receipt():
    schema = SPEC.result
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "entry_id", "state", "plan_id", "digest", "applied", "receipts",
        "files_count", "started_at", "finished_at"}
    assert schema["properties"]["state"]["enum"] == ["COMMITTED"]
    assert schema["properties"]["applied"]["items"]["required"] == [
        "path", "applied_hash"]
    assert schema["properties"]["receipts"]["items"]["required"] == [
        "step_id", "applied_hash", "undo_token"]


def test_manifest_declares_the_tool_and_ports():
    manifest = apply_module.MODULE
    assert manifest.id == "editing.write_apply"
    assert tuple(manifest.provides_tools) == ("write_apply",)
    assert set(manifest.requires_ports) == {"writer", "journal", "backups", "lock"}
    assert "editing.write_preview" in tuple(manifest.requires)
    assert tuple(manifest.provides_tools) == tuple(
        tool.name for tool in apply_tools.TOOLS)


def test_apply_returns_a_clean_receipt(tmp_path):
    agent, plan, answer = _applied(tmp_path)
    assert answer["ok"], answer
    result = answer["result"]
    assert result["state"] == "COMMITTED"
    assert result["entry_id"] == plan["plan_id"] + "#1"
    assert result["digest"] == plan["digest"]
    assert [item["path"] for item in result["applied"]] == ["res://src/hero.gd"]
    hero = tmp_path / "project" / "src" / "hero.gd"
    assert result["applied"][0]["applied_hash"] == hashlib.sha256(
        hero.read_bytes()).hexdigest()
    assert len(result["receipts"]) == result["files_count"] == 1
    flat = json.dumps(result, ensure_ascii=False)
    assert "Traceback" not in flat
    assert not ABS_PATH.search(flat), "R-15: наружу не уходят абсолютные пути"


def test_empty_plan_id_is_invalid_input(tmp_path):
    agent, plan = _prepared(tmp_path)
    answer = agent.call("write_apply", {"plan_id": "", "digest": plan["digest"]})
    assert answer["ok"] is False and answer["kind"] == "invalid_input"


def test_unknown_plan_is_not_found(tmp_path):
    agent = _agent(tmp_path)
    answer = agent.call("write_apply", {"plan_id": "plan_nope", "digest": "d"})
    assert answer["ok"] is False and answer["kind"] == "not_found"
    assert "Traceback" not in json.dumps(answer, ensure_ascii=False)


def test_wrong_digest_is_stale_plan_without_effect(tmp_path):
    agent, plan = _prepared(tmp_path)
    hero = tmp_path / "project" / "src" / "hero.gd"
    before = hashlib.sha256(hero.read_bytes()).hexdigest()
    answer = agent.call("write_apply", {"plan_id": plan["plan_id"], "digest": "nope"})
    assert answer["kind"] == "stale_plan"
    assert answer["details"]["expected"] == plan["digest"]
    assert hashlib.sha256(hero.read_bytes()).hexdigest() == before


def test_repeat_apply_is_the_same_receipt(tmp_path):
    agent, plan = _prepared(tmp_path)
    args = {"plan_id": plan["plan_id"], "digest": plan["digest"]}
    first = agent.call("write_apply", args)["result"]
    second = agent.call("write_apply", args)["result"]
    assert second == first, "идентичность по ADR-0005: без нового эффекта"


def test_repeat_rollback_conflict_names_the_reason(tmp_path):
    agent, plan = _prepared(tmp_path)
    applied = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                         "digest": plan["digest"]})["result"]
    assert agent.call("write_rollback", {"entry_id": applied["entry_id"]})["ok"]
    again = agent.call("write_rollback", {"entry_id": applied["entry_id"]})
    assert again["ok"] is False and again["kind"] == "conflict"
    assert again["details"]["reason"] == "already_rolled_back"


def test_conflict_reasons_are_a_closed_set():
    """Причина `conflict` вне набора — дефект: шестая причина не появляется молча."""
    from python.modules.editing.shared import conflict_reasons

    with pytest.raises(AppError) as caught:
        validate_args(SPEC, {"plan_id": 1, "digest": "d"})
    assert caught.value.kind == "invalid_input"
    assert conflict_reasons.is_known("post_state_mismatch")
    assert conflict_reasons.is_known("plan_state:APPLYING")
    assert not conflict_reasons.is_known("plan_state:NOPE")
    assert not conflict_reasons.is_known("something_new")


def test_schema_rejects_empty_plan_id():
    with pytest.raises(AppError) as caught:
        validate_args(SPEC, {"plan_id": "", "digest": "d"})
    assert caught.value.kind == "invalid_input"
