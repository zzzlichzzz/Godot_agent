"""tests/py/contract/test_usages_contract.py - контракт механики code_intel.usages.

Проверяется клиентская поверхность (R-15, ADR-0006): плоское имя `usages`,
эффекты только чтение, схемы, объявленные `kind`, отказы политики и locator'а,
синхронность `contract/capabilities/usages.json` и SEC-11: вызов не меняет ни
один файл проекта (хеши до и после).
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

from python.kernel.errors import KINDS, AppError
from python.kernel.tool_spec import CONTRACT_SCHEMA_VERSION
from python.modules.code_intel.usages import module as usages_module
from python.modules.code_intel.usages import tools as usages_tools
from python.protocol.validation import validate_args
from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "projects" / "usages"
SPEC = usages_tools.USAGES
ABS_PATH = re.compile(r"\b[A-Za-z]:[\\/]")
KINDS_IN_SCHEMA = ["class_name", "function", "signal", "variable", "const",
                   "enum", "enum_member"]


def _agent():
    return build_agent(project_root=str(FIXTURE), profile="test")


def _flat(payload):
    return json.dumps(payload, ensure_ascii=False)


def _digest_tree():
    return {path.relative_to(FIXTURE).as_posix():
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(FIXTURE.rglob("*")) if path.is_file()}


def test_tool_name_effects_and_cost():
    assert SPEC.name == "usages"
    assert SPEC.effects == "read"
    assert SPEC.idempotent is True
    assert SPEC.requires_preview is False
    assert SPEC.availability == "*"
    assert SPEC.cost != "cheap", "обход всего проекта не может стоить дёшево"


def test_declared_errors_are_stable_kinds():
    assert SPEC.errors == ("invalid_input", "not_found", "denied")
    assert set(SPEC.errors) <= set(KINDS)


def test_args_schema_is_the_documented_surface():
    schema = SPEC.args
    assert schema["required"] == ["kind", "old_name", "declaration"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"kind", "old_name", "declaration", "new_name"}
    assert schema["properties"]["kind"]["enum"] == KINDS_IN_SCHEMA


def test_result_schema_pins_usages_and_counters():
    schema = SPEC.result
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"kind", "old_name", "new_name", "declaration",
                                       "usages", "by_link", "proven_count",
                                       "probable_count", "dynamic_count"}
    item = schema["properties"]["usages"]["items"]
    assert item["required"] == ["path", "line", "column", "link", "confidence", "note"]
    assert item["additionalProperties"] is False


def test_manifest_declares_the_same_tool():
    manifest = usages_module.MODULE
    assert manifest.id == "code_intel.usages"
    assert tuple(manifest.provides_tools) == tuple(tool.name for tool in usages_tools.TOOLS)
    assert tuple(manifest.requires_ports) == ("fs",)
    assert callable(manifest.entrypoints.get("call"))


def test_generated_contract_is_in_sync():
    artifact = ROOT / "contract" / "capabilities" / "usages.json"
    assert artifact.exists(), "нет contract/capabilities/usages.json (tools/gen_contract.py)"
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["schema_version"] == CONTRACT_SCHEMA_VERSION
    expected = SPEC.contract(usages_module.MODULE.id,
                             usages_module.MODULE.capabilities[0])
    assert saved == expected


@pytest.mark.parametrize("args", [
    {"kind": "method", "old_name": "x", "declaration": "res://src/lab_entity.gd:12"},
    {"kind": "function", "old_name": "x"},
    {"kind": "function", "declaration": "res://src/lab_entity.gd:12"},
    {"kind": "function", "old_name": "x", "declaration": "res://src/lab_entity.gd:12",
     "card": True},
    {"kind": "function", "old_name": 5, "declaration": "res://src/lab_entity.gd:12"},
])
def test_invalid_input_is_typed_and_clean(args):
    with pytest.raises(AppError) as caught:
        validate_args(SPEC, args)
    error = caught.value
    assert error.kind == "invalid_input"
    assert not ABS_PATH.search(_flat(error.payload()))
    assert "Traceback" not in _flat(error.payload())


@pytest.mark.parametrize("declaration", [
    "res://src/lab_entity.gd:abc",
    "res://src/lab_entity.gd:0",
    "src/lab_entity.gd:12",
])
def test_bad_locator_is_invalid_input_through_the_agent(declaration):
    answer = _agent().call("usages", {"kind": "function", "old_name": "take_damage",
                                      "declaration": declaration})
    assert answer["ok"] is False and answer["kind"] == "invalid_input"


@pytest.mark.parametrize("declaration", ["res://src/lab_entity.gd:3",
                                         "res://missing.gd:1"])
def test_missing_declaration_is_not_found(declaration):
    answer = _agent().call("usages", {"kind": "function", "old_name": "take_damage",
                                      "declaration": declaration})
    assert answer["ok"] is False and answer["kind"] == "not_found"
    payload = _flat(answer)
    assert "take_damage" in payload and not ABS_PATH.search(payload)


@pytest.mark.parametrize("declaration", ["res://../outside.gd:1",
                                         "res://addons/other/plugin.gd:4"])
def test_paths_outside_the_project_are_denied(declaration):
    answer = _agent().call("usages", {"kind": "function", "old_name": "plugin_ready",
                                      "declaration": declaration})
    assert answer["ok"] is False and answer["kind"] == "denied"
    assert not ABS_PATH.search(_flat(answer))


def test_usages_call_does_not_touch_files():
    """SEC-11: read-only проверяется хешами до и после вызова, а не словами."""
    before = _digest_tree()
    answer = _agent().call("usages", {"kind": "function", "old_name": "take_damage",
                                      "declaration": "res://src/lab_entity.gd:12"})
    assert answer["ok"] is True
    assert _digest_tree() == before


def test_tools_register_without_conflicts():
    agent = _agent()
    assert agent.conflicts() == []
    names = [tool["name"] for tool in agent.tools()]
    # Имена — инвентарь headless-профиля: новая механика добавляет своё имя.
    assert sorted(names) == ["analyze_rename", "api", "api_check", "ask", "assistant_confirm", "assistant_plan", "assistant_rollback", "assistant_turn", "chat", "check", "connections", "context", "functions", "gd_lint", "judge", "node", "node_delete_preview", "node_rename_preview", "node_reparent_preview", "paths_preview", "read", "scene", "scene_deps", "search",
                                 "split_apply", "split_gd_plan", "split_gd_scan", "split_plan", "split_scan", "usages", "verify", "write_apply", "write_preview",
                             "write_rollback"]
    assert names.count("usages") == 1
    assert names.count("analyze_rename") == 1
    assert "code_intel.usages" not in agent.disabled()
