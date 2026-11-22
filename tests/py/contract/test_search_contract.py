"""tests/py/contract/test_search_contract.py - контракт механики project_text.search.

Проверяется то, что видит клиент (R-15, ADR-0006): имя и эффекты инструмента,
схема входа/выхода, объявленные `kind`, отсутствие путей и стектрейсов в ошибках,
синхронность сгенерированного артефакта `contract/capabilities/search.json`
и правило «дубль tool_name отключает обоих» (R-03).
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from python.kernel.errors import KINDS, AppError
from python.kernel.tool_spec import CONTRACT_SCHEMA_VERSION, ToolSpec
from python.modules.project_text.search import module as search_module
from python.modules.project_text.search import tools as search_tools
from python.protocol.dispatch import Dispatcher
from python.protocol.error_map import from_exception
from python.protocol.registry import Registry
from python.protocol.validation import validate_args

ROOT = Path(__file__).resolve().parents[3]
SPEC = search_tools.SEARCH
ABS_PATH = re.compile(r"[A-Za-z]:[\\/]")


def _flat(payload):
    return json.dumps(payload, ensure_ascii=False)


def test_tool_name_effects_and_availability():
    assert SPEC.name == "search"
    assert SPEC.effects == "read"
    assert SPEC.idempotent is True
    assert SPEC.requires_preview is False
    assert SPEC.availability == "*"


def test_declared_errors_are_stable_kinds():
    assert SPEC.errors == ("invalid_input", "not_found", "denied")
    assert set(SPEC.errors) <= set(KINDS)


def test_args_schema_is_the_documented_surface():
    schema = SPEC.args
    assert schema["required"] == ["query"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"query", "max_results", "context_lines",
                                         "exclude_rel_prefixes", "case_insensitive"}
    assert schema["properties"]["max_results"]["minimum"] == 1
    assert schema["properties"]["context_lines"]["minimum"] == 0
    assert schema["properties"]["exclude_rel_prefixes"]["items"] == {"type": "string"}


def test_result_schema_pins_matches_and_truncated():
    schema = SPEC.result
    assert schema["required"] == ["matches", "truncated"]
    assert schema["additionalProperties"] is False
    item = schema["properties"]["matches"]["items"]
    assert item["required"] == ["path", "line", "snippet"]
    assert item["additionalProperties"] is False


def test_manifest_declares_the_same_tool():
    manifest = search_module.MODULE
    assert manifest.id == "project_text.search"
    assert tuple(manifest.provides_tools) == tuple(tool.name for tool in search_tools.TOOLS)
    assert tuple(manifest.requires_ports) == ("fs",)
    assert callable(manifest.entrypoints.get("call"))


def test_generated_contract_is_in_sync():
    artifact = ROOT / "contract" / "capabilities" / "search.json"
    assert artifact.exists(), "нет contract/capabilities/search.json (tools/gen_contract.py)"
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["schema_version"] == CONTRACT_SCHEMA_VERSION
    expected = SPEC.contract(search_module.MODULE.id, search_module.MODULE.capabilities[0])
    assert saved == expected


@pytest.mark.parametrize("args", [
    {"query": 5},
    {"query": "x", "max_results": 0},
    {"query": "x", "context_lines": -1},
    {"query": "x", "unknown": True},
    {},
])
def test_invalid_input_is_typed_and_clean(args):
    with pytest.raises(AppError) as caught:
        validate_args(SPEC, args)
    error = caught.value
    assert error.kind == "invalid_input"
    payload = _flat(error.payload())
    assert "Traceback" not in payload
    assert not ABS_PATH.search(payload)


def test_os_error_is_redacted_to_kind_and_no_path():
    leaked = FileNotFoundError(2, "No such file or directory", r"D:\proj\scenes\player.tscn")
    error = from_exception(leaked, (r"D:\proj",))
    assert error.kind == "not_found"
    payload = _flat(error.payload())
    assert not ABS_PATH.search(payload)
    assert "<PROJECT>" in payload
    assert "Traceback" not in payload


def test_unknown_tool_is_typed():
    with pytest.raises(AppError) as caught:
        Dispatcher(Registry()).call("serch", {"query": "x"})
    assert caught.value.kind == "unknown_tool"


def test_duplicate_tool_name_disables_both_owners():
    registry = Registry()
    tool = ToolSpec(name="dup", description="второй владелец того же имени",
                    args={"type": "object"}, result={"type": "object"})
    first = SimpleNamespace(id="area_one.feature_one")
    second = SimpleNamespace(id="area_two.feature_two")
    registry.add_module(first, (tool,), {"dup": lambda args: {}})
    registry.add_module(second, (tool,), {"dup": lambda args: {}})
    assert registry.get("dup") is None
    assert registry.names() == []
    assert registry.conflicts() == [{"tool": "dup",
                                     "owners": ["area_one.feature_one",
                                                "area_two.feature_two"]}]
    assert set(registry.disabled()) == {"area_one.feature_one", "area_two.feature_two"}
