"""tests/py/contract/test_functions_contract.py - контракт механики code_intel.functions.

Проверяется то, что видит клиент (R-15, ADR-0006): плоское имя `functions`,
эффекты, схемы входа/выхода, объявленные `kind`, отказ политики на `..` и
абсолютный путь, синхронность `contract/capabilities/functions.json` и правило
«дубль tool_name отключает обоих» с честным `unavailable` (долг R-03).
"""

import errno
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from python.kernel.errors import KINDS, AppError
from python.kernel.paths import PathPolicy
from python.kernel.tool_spec import CONTRACT_SCHEMA_VERSION, ToolSpec
from python.modules.code_intel.functions import app as functions_app
from python.modules.code_intel.functions import module as functions_module
from python.modules.code_intel.functions import tools as functions_tools
from python.protocol.dispatch import Dispatcher
from python.protocol.registry import Registry
from python.protocol.validation import validate_args
from python.runtime.bootstrap import build_agent
from python.runtime.context import ModuleContext

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "projects" / "minimal"
SPEC = functions_tools.FUNCTIONS
ABS_PATH = re.compile(r"\b[A-Za-z]:[\\/]")


def _flat(payload):
    return json.dumps(payload, ensure_ascii=False)


def _agent():
    return build_agent(project_root=str(FIXTURE), profile="test")


def test_tool_name_is_flat_and_read_only():
    assert SPEC.name == "functions"
    assert SPEC.effects == "read"
    assert SPEC.idempotent is True
    assert SPEC.requires_preview is False
    assert SPEC.availability == "*"
    assert SPEC.cost == "cheap"


def test_declared_errors_are_stable_kinds():
    assert SPEC.errors == ("invalid_input", "not_found", "denied")
    assert set(SPEC.errors) <= set(KINDS)


def test_args_schema_is_the_documented_surface():
    schema = SPEC.args
    assert schema["required"] == ["path"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"path", "names"}
    assert schema["properties"]["names"]["items"] == {"type": "string"}
    assert schema["properties"]["names"]["default"] == []


def test_result_schema_pins_both_modes():
    schema = SPEC.result
    assert schema["required"] == ["path"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"path", "names", "functions", "missing"}
    item = schema["properties"]["functions"]["items"]
    assert item["required"] == ["name", "start_line", "end_line", "snippet"]
    assert item["additionalProperties"] is False
    assert schema["properties"]["missing"]["items"] == {"type": "string"}


def test_manifest_declares_the_same_tool():
    manifest = functions_module.MODULE
    assert manifest.id == "code_intel.functions"
    assert tuple(manifest.provides_tools) == tuple(tool.name for tool in functions_tools.TOOLS)
    assert tuple(manifest.requires_ports) == ("fs",)
    assert callable(manifest.entrypoints.get("call"))


def test_generated_contract_is_in_sync():
    artifact = ROOT / "contract" / "capabilities" / "functions.json"
    assert artifact.exists(), "нет contract/capabilities/functions.json (tools/gen_contract.py)"
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["schema_version"] == CONTRACT_SCHEMA_VERSION
    expected = SPEC.contract(functions_module.MODULE.id,
                              functions_module.MODULE.capabilities[0])
    assert saved == expected


@pytest.mark.parametrize("args", [
    {"path": 5},
    {},
    {"path": "res://scripts/player.gd", "names": "take_damage"},
    {"path": "res://scripts/player.gd", "names": [1]},
    {"path": "res://scripts/player.gd", "card": True},
])
def test_invalid_input_is_typed_and_clean(args):
    with pytest.raises(AppError) as caught:
        validate_args(SPEC, args)
    error = caught.value
    assert error.kind == "invalid_input"
    payload = _flat(error.payload())
    assert "Traceback" not in payload
    assert not ABS_PATH.search(payload)


@pytest.mark.parametrize("path", ["../outside.gd", "/etc/absolute.gd",
                                  "res://addons/other_plugin/plugin.gd"])
def test_paths_outside_the_project_are_denied(path):
    answer = _agent().call("functions", {"path": path})
    assert answer["ok"] is False
    assert answer["kind"] == "denied"
    payload = _flat(answer)
    assert not ABS_PATH.search(payload)
    assert "Traceback" not in payload


def test_not_gd_path_is_invalid_input():
    answer = _agent().call("functions", {"path": "res://scenes/player.tscn"})
    assert answer["ok"] is False
    assert answer["kind"] == "invalid_input"


def test_stranger_mechanics_tool_name_is_unknown():
    with pytest.raises(AppError) as caught:
        Dispatcher(Registry()).call("functins", {"path": "res://scripts/player.gd"})
    assert caught.value.kind == "unknown_tool"


def test_two_modules_register_without_conflicts():
    agent = _agent()
    assert agent.conflicts() == []
    # Остальные 42 механики ещё стабы и падают в disabled — это ожидаемо;
    # важно, что два перенесённых модуля живы и не конфликтуют.
    assert set(agent.disabled()) & {"code_intel.functions", "project_text.search"} == set()
    names = [tool["name"] for tool in agent.tools()]
    # Имена — инвентарь headless-профиля: новая механика добавляет своё имя.
    assert sorted(names) == ["analyze_rename", "api", "api_check", "ask", "assistant_confirm", "assistant_plan", "assistant_rollback", "assistant_turn", "chat", "check", "connections", "context", "functions", "gd_lint", "judge", "node", "node_delete_preview", "node_rename_preview", "node_reparent_preview", "paths_preview", "read", "scene", "scene_deps", "search",
                                 "split_apply", "split_gd_plan", "split_gd_scan", "split_plan", "split_scan", "usages", "verify", "write_apply", "write_preview",
                             "write_rollback"]
    assert names.count("functions") == 1


def test_disabled_module_answers_unavailable_with_reason():
    registry = Registry()
    spec = SimpleNamespace(id="code_intel.functions")
    registry.add_module(spec, (SPEC,), {"functions": lambda args: {}})
    registry.mark_failures([{"module": "code_intel.functions",
                             "reason": "ImportError: boom"}])
    with pytest.raises(AppError) as caught:
        Dispatcher(registry).call("functions", {"path": "res://scripts/player.gd"})
    error = caught.value
    assert error.kind == "unavailable"
    assert "code_intel.functions" in error.message
    assert "boom" in error.hint


class _BoomPort:
    """Поддельный порт `fs`: чтение падает заданным классом ошибки."""

    def __init__(self, error):
        self.error = error

    def read_text(self, rel):
        raise self.error


def _ctx_with(error):
    return ModuleContext(profile="test",
                         ports={"fs": _BoomPort(error)},
                         path_policy=PathPolicy(str(FIXTURE)))


def test_permission_error_from_port_is_denied():
    ctx = _ctx_with(PermissionError(errno.EACCES, "Permission denied"))
    with pytest.raises(AppError) as caught:
        functions_app.call("functions", {"path": "res://scripts/player.gd"}, ctx)
    error = caught.value
    assert error.kind == "denied"
    assert "res://scripts/player.gd" in error.message
    assert not ABS_PATH.search(_flat(error.payload()))


def test_oversized_file_is_not_found_like_the_reference():
    """Файл существует, но больше лимита чтения — эталон отказывал `file too large`.

    Класс отказа берём у эталона (`read_project_file` → OSError), поэтому здесь
    `not_found`, а не `unavailable`: это перенос поведения, а не удобство.
    """
    ctx = _ctx_with(OSError(errno.EFBIG, "File too large"))
    with pytest.raises(AppError) as caught:
        functions_app.call("functions", {"path": "res://scripts/player.gd"}, ctx)
    error = caught.value
    assert error.kind == "not_found"
    assert "лимит" in error.message
    assert not ABS_PATH.search(_flat(error.payload()))
