"""tests/py/contract/test_analyze_rename_contract.py - контракт предпросмотра.

`analyze_rename` — второй инструмент модуля `code_intel.usages` (parity строка
23). Проверяется клиентская поверхность: схемы, объявленные отказы, формат
строк `risks`, эхо `mode`/`allow_unverified` как в эталоне, read-only (SEC-11)
и синхронность `contract/capabilities/analyze_rename.json`.
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
SPEC = usages_tools.ANALYZE_RENAME
ABS_PATH = re.compile(r"\b[A-Za-z]:[\\/]")
RISK = re.compile(r"^res://[^:]+:\d+ \[(declaration|call|member|identifier|type|string), "
                  r"(proven|probable|dynamic)\]( — .+)?$")
ENTITY = "res://src/lab_entity.gd:12"
BASE = {"kind": "function", "old_name": "take_damage", "new_name": "apply_damage",
        "declaration": ENTITY}


def _agent():
    return build_agent(project_root=str(FIXTURE), profile="test")


def _flat(payload):
    return json.dumps(payload, ensure_ascii=False)


def _digest_tree():
    return {path.relative_to(FIXTURE).as_posix():
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(FIXTURE.rglob("*")) if path.is_file()}


def _preview(**extra):
    args = dict(BASE)
    args.update(extra)
    answer = _agent().call("analyze_rename", args)
    assert answer["ok"] is True, answer
    return answer["result"]


def test_tool_name_effects_and_cost():
    assert SPEC.name == "analyze_rename"
    assert SPEC.effects == "read"
    assert SPEC.idempotent is True
    assert SPEC.requires_preview is False
    assert SPEC.availability == "*"
    assert SPEC.cost == "heavy", "тот же полный обход проекта, что у usages"


def test_declared_errors_are_stable_kinds():
    assert SPEC.errors == ("invalid_input", "not_found", "denied")
    assert set(SPEC.errors) <= set(KINDS)


def test_args_schema_is_the_documented_surface():
    schema = SPEC.args
    assert schema["required"] == ["kind", "old_name", "new_name"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"kind", "old_name", "new_name", "declaration",
                                         "declaration_path", "mode", "allow_unverified"}
    assert schema["properties"]["kind"]["enum"] == [
        "class_name", "function", "signal", "variable", "const", "enum", "enum_member"]
    assert schema["properties"]["mode"]["enum"] == ["strict", "probable"]
    assert schema["properties"]["mode"]["default"] == "strict"
    assert schema["properties"]["allow_unverified"]["type"] == "boolean"
    assert schema["properties"]["allow_unverified"]["default"] is False


def test_result_schema_pins_preview_fields():
    schema = SPEC.result
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "kind", "old_name", "new_name", "declaration", "declaration_path",
        "declaration_line", "allow_unverified", "mode", "usages", "affected_paths",
        "risks", "by_link", "proven_count", "probable_count", "dynamic_count"}
    assert schema["properties"]["affected_paths"]["items"]["type"] == "string"
    assert schema["properties"]["risks"]["items"]["type"] == "string"


def test_manifest_declares_both_tools_of_the_module():
    manifest = usages_module.MODULE
    assert manifest.id == "code_intel.usages"
    assert tuple(manifest.provides_tools) == ("usages", "analyze_rename")
    assert tuple(manifest.provides_tools) == tuple(t.name for t in usages_tools.TOOLS)
    assert callable(manifest.entrypoints.get("call"))


def test_generated_contract_is_in_sync():
    artifact = ROOT / "contract" / "capabilities" / "analyze_rename.json"
    assert artifact.exists(), "нет contract/capabilities/analyze_rename.json"
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["schema_version"] == CONTRACT_SCHEMA_VERSION
    expected = SPEC.contract(usages_module.MODULE.id,
                             usages_module.MODULE.capabilities[0])
    assert saved == expected


@pytest.mark.parametrize("args", [
    {"kind": "function", "old_name": "take_damage", "declaration": ENTITY},
    {"kind": "function", "old_name": "take_damage", "new_name": "", "declaration": ENTITY},
    dict(BASE, mode="fast"),
    dict(BASE, allow_unverified="yes"),
    dict(BASE, card=True),
])
def test_invalid_input_is_typed_and_clean(args):
    with pytest.raises(AppError) as caught:
        validate_args(SPEC, args)
    error = caught.value
    assert error.kind == "invalid_input"
    assert not ABS_PATH.search(_flat(error.payload()))
    assert "Traceback" not in _flat(error.payload())


def test_missing_new_name_is_invalid_input_through_the_agent():
    """Эталонный мост отвечал RC_USAGE, когда new_name не передан."""
    answer = _agent().call("analyze_rename", {"kind": "function",
                                              "old_name": "take_damage",
                                              "declaration": ENTITY})
    assert answer["ok"] is False and answer["kind"] == "invalid_input"


@pytest.mark.parametrize("declaration,kind", [
    ("res://src/lab_entity.gd:abc", "invalid_input"),
    ("src/lab_entity.gd:12", "invalid_input"),
    ("res://src/lab_entity.gd:3", "not_found"),
])
def test_locator_errors_are_typed(declaration, kind):
    answer = _agent().call("analyze_rename", dict(BASE, declaration=declaration))
    assert answer["ok"] is False and answer["kind"] == kind
    assert not ABS_PATH.search(_flat(answer))


@pytest.mark.parametrize("declaration", ["res://../outside.gd:1",
                                         "res://addons/other/plugin.gd:4"])
def test_paths_outside_the_project_are_denied(declaration):
    answer = _agent().call("analyze_rename", dict(BASE, declaration=declaration))
    assert answer["ok"] is False and answer["kind"] == "denied"
    assert not ABS_PATH.search(_flat(answer))


def test_preview_reports_paths_risks_and_echoes_defaults():
    result = _preview()
    assert (result["declaration_path"], result["declaration_line"]) == (
        "res://src/lab_entity.gd", 12)
    assert result["declaration"] == ENTITY and result["new_name"] == "apply_damage"
    assert result["mode"] == "strict" and result["allow_unverified"] is False
    assert result["affected_paths"] == ["res://src/lab_entity.gd",
                                        "res://src/lab_turret.gd"]
    assert all(RISK.match(line) for line in result["risks"]), result["risks"]
    assert not any("[proven]" in line for line in result["risks"])
    assert result["proven_count"] + result["probable_count"] + \
        result["dynamic_count"] == len(result["usages"])


def test_mode_is_echoed_exactly_like_the_reference():
    """Эталон не меняет отчёт по mode: меняются только поле и решения записи."""
    strict = _preview(mode="strict")
    probable = _preview(mode="probable")
    assert (strict["mode"], probable["mode"]) == ("strict", "probable")
    for field in ("usages", "affected_paths", "risks", "by_link", "proven_count",
                  "probable_count", "dynamic_count"):
        assert strict[field] == probable[field], field


def test_allow_unverified_is_echoed_and_changes_nothing_else():
    plain = _preview()
    allowed = _preview(allow_unverified=True)
    assert allowed["allow_unverified"] is True
    for field in ("usages", "affected_paths", "risks", "mode"):
        assert plain[field] == allowed[field], field


def test_preview_does_not_touch_files():
    """SEC-11: предпросмотр ничего не пишет — хеши фикстуры до и после равны."""
    before = _digest_tree()
    result = _preview()
    assert result["risks"]
    assert _digest_tree() == before
