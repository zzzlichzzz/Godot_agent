"""tests/py/contract/test_write_preview_contract.py - контракт воронки записи.

`write_preview` — первая механика с `effects="write"` (R-12, R-20): она обязана
вернуть план, digest и диффы, но не тронуть ни байта проекта. Проверяется
клиентская поверхность: схемы, объявленные отказы, обязательный
`details.reason` у `conflict`, отсутствие абсолютных путей и стектрейсов,
синхронность `contract/capabilities/write_preview.json`.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

from python.kernel.errors import KINDS, AppError
from python.modules.editing.write_preview import module as preview_module
from python.modules.editing.write_preview import tools as preview_tools
from python.protocol.validation import validate_args
from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "projects" / "rename"
SPEC = preview_tools.WRITE_PREVIEW
CAPABILITY = ROOT / "contract" / "capabilities" / "write_preview.json"
ABS_PATH = re.compile(r"\b[A-Za-z]:[\\/]")
BASE = {"kind": "function", "old_name": "take_damage",
        "new_name": "apply_damage", "declaration": "res://src/hero.gd:6"}
KINDS7 = ["class_name", "function", "signal", "variable", "const", "enum",
          "enum_member"]


def _agent():
    return build_agent(project_root=str(FIXTURE), profile="test")


def _call(**extra):
    args = dict(BASE)
    args.update(extra)
    return _agent().call("write_preview", args)


def _tree():
    return {path.relative_to(FIXTURE).as_posix():
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(FIXTURE.rglob("*")) if path.is_file()}


def test_tool_name_effects_and_receipt_shape():
    assert SPEC.name == "write_preview"
    assert SPEC.effects == "write", "первая механика записи: R-20"
    assert SPEC.idempotent is False, "plan_id новый на каждый вызов"
    assert SPEC.availability == "*"
    assert SPEC.cost == "heavy"


def test_declared_errors_are_stable_kinds():
    assert SPEC.errors == ("invalid_input", "not_found", "denied", "conflict")
    assert set(SPEC.errors) <= set(KINDS)


def test_args_schema_is_the_documented_surface():
    schema = SPEC.args
    assert schema["required"] == ["kind", "old_name", "new_name", "declaration"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"kind", "declaration", "old_name",
                                         "new_name", "mode", "allow_unverified",
                                         "exclude"}
    assert schema["properties"]["kind"]["enum"] == KINDS7
    assert schema["properties"]["new_name"]["minLength"] == 1
    assert schema["properties"]["mode"]["enum"] == ["strict", "probable"]
    assert schema["properties"]["mode"]["default"] == "strict"
    assert schema["properties"]["allow_unverified"]["default"] is False
    assert schema["properties"]["exclude"]["items"]["type"] == "string"


def test_result_schema_pins_the_receipt():
    schema = SPEC.result
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "plan_id", "digest", "state", "kind", "old_name", "new_name",
        "declaration", "mode", "allow_unverified", "steps", "steps_count",
        "affected_paths", "skipped_usages", "risks", "diffs", "stats",
        "confirm_ttl"}
    assert schema["properties"]["state"]["enum"] == ["PREPARED"]
    assert schema["properties"]["steps"]["items"]["required"] == [
        "op", "target", "payload", "expected_hash"]
    assert schema["properties"]["stats"]["required"] == [
        "files", "edits", "proven", "probable", "dynamic", "skipped"]


def test_manifest_declares_the_tool():
    manifest = preview_module.MODULE
    assert manifest.id == "editing.write_preview"
    assert tuple(manifest.provides_tools) == ("write_preview",)
    assert tuple(manifest.provides_tools) == tuple(t.name for t in preview_tools.TOOLS)
    assert "journal" in tuple(manifest.requires_ports)


def test_generated_contract_matches_the_spec():
    assert CAPABILITY.is_file(), "python tools/gen_contract.py --write"
    artifact = json.loads(CAPABILITY.read_text(encoding="utf-8"))
    assert artifact["tool_name"] == SPEC.name
    assert artifact["effects"] == ["write"]
    assert artifact["input_schema"] == SPEC.args
    assert artifact["result_schema"] == SPEC.result

def test_preview_builds_a_plan_and_never_touches_the_project():
    before = _tree()
    result = _call(mode="probable", allow_unverified=True)["result"]
    assert _tree() == before, "предпросмотр не пишет в проект (R-12)"
    assert result["state"] == "PREPARED"
    assert result["kind"] == "function" and result["new_name"] == "apply_damage"
    assert result["steps_count"] == len(result["steps"]) == 3
    assert result["affected_paths"] == ["res://src/enemy.gd", "res://src/hero.gd",
                                        "res://src/party.gd"]
    assert result["confirm_ttl"] == 900
    assert result["stats"]["files"] == 3 and result["stats"]["edits"] == 6


def test_payload_is_clean_json_without_absolute_paths():
    result = _call(mode="probable", allow_unverified=True)["result"]
    flat = json.dumps(result, ensure_ascii=False)
    assert "Traceback" not in flat
    assert not ABS_PATH.search(flat), "R-15: наружу не уходят абсолютные пути"
    for diff in result["diffs"]:
        assert diff["patch"].startswith("--- a/")
        assert "+++ b/" in diff["patch"]


def test_steps_point_at_our_offsets_in_the_normalised_text():
    result = _call(mode="probable", allow_unverified=True)["result"]
    for step in result["steps"]:
        text = (FIXTURE / step["target"][len("res://"):]).read_text(encoding="utf-8")
        text = text.replace("\r\n", "\n")
        assert step["expected_hash"] == hashlib.sha256(
            text.encode("utf-8")).hexdigest()
        for edit in step["payload"]["edits"]:
            assert text[edit["start"]:edit["end"]] == "take_damage"
            assert edit["replacement"] == "apply_damage"


@pytest.mark.parametrize("extra, reason", [
    ({}, "unverified_references"),
    ({"allow_unverified": True}, "dynamic_references"),
    ({"new_name": "strike", "mode": "probable", "allow_unverified": True},
     "name_conflict"),
    ({"mode": "probable", "allow_unverified": True,
      "exclude": ["res://src/enemy.gd:4", "res://src/enemy.gd:7",
                  "res://src/enemy.gd:10", "res://src/hero.gd:11",
                  "res://src/party.gd:6", "res://src/party.gd:9"]},
     "all_usages_excluded"),
])
def test_conflict_always_explains_itself(extra, reason):
    answer = _call(**extra)
    assert answer["ok"] is False and answer["kind"] == "conflict"
    assert answer["details"]["reason"] == reason
    assert answer["message"].strip() and "Traceback" not in answer["message"]


@pytest.mark.parametrize("extra, kind", [
    ({"old_name": "func"}, "invalid_input"),
    ({"new_name": "2x y"}, "invalid_input"),
    ({"declaration": "res://src/hero.gd:7"}, "not_found"),
    ({"declaration": "res://addons/other/plugin.gd:5"}, "denied"),
])
def test_declared_refusals_keep_their_kind(extra, kind):
    answer = _call(**extra)
    assert answer["ok"] is False and answer["kind"] == kind


def test_same_input_gives_same_digest_but_new_plan_id():
    first = _call(mode="probable", allow_unverified=True)["result"]
    second = _call(mode="probable", allow_unverified=True)["result"]
    assert first["digest"] == second["digest"]
    assert first["plan_id"] != second["plan_id"]


def test_schema_rejects_empty_new_name_and_unknown_kind():
    for broken in ({"new_name": ""}, {"kind": "method"}):
        args = dict(BASE, **broken)
        with pytest.raises(AppError) as caught:
            validate_args(SPEC, args)
        assert caught.value.kind == "invalid_input"
