"""tests/py/contract/test_context_contract.py - контракт механики context.gather.

Проверяется то, что видит клиент (R-15, ADR-0006): имя и эффекты, схемы входа и
выхода, объявленные `kind`, отказ по неизвестной секции, синхронность артефакта
`contract/capabilities/context.json` и манифест владельца инструмента.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from python.kernel.errors import KINDS, AppError
from python.kernel.paths import PathPolicy
from python.kernel.tool_spec import ToolSpec
from python.modules.context.gather import app as gather_app
from python.modules.context.gather import module as gather_module
from python.modules.context.gather import tools as gather_tools
from python.protocol.validation import validate_args

ROOT = Path(__file__).resolve().parents[3]
SPEC = gather_tools.CONTEXT
ABS_PATH = re.compile(r"[A-Za-z]:[\\/]")


def _context():
    """Контекст вызова без портов и реестра: отказ по входу обязан быть раньше."""
    return SimpleNamespace(profile="test", path_policy=PathPolicy(""),
                           registry=None)


def test_spec_pins_tool_contract():
    assert isinstance(SPEC, ToolSpec)
    assert SPEC.name == "context"
    assert SPEC.effects == "read"
    assert SPEC.idempotent is True
    assert SPEC.requires_preview is False
    assert SPEC.availability == "*"
    assert SPEC.cost == "light"
    assert set(SPEC.errors) <= set(KINDS)


def test_args_schema_bounds_sections():
    """Вход: 1…8 имён секций и необязательный путь, лишних ключей нет."""
    sections = SPEC.args["properties"]["sections"]
    assert sections["type"] == "array"
    assert sections["items"] == {"type": "string"}
    assert sections["minItems"] == 1
    assert sections["maxItems"] == 8
    assert SPEC.args["additionalProperties"] is False
    assert SPEC.args["properties"]["path"]["type"] == "string"


def test_result_schema_requires_all_four_parts():
    """Выход: всегда есть `sections`, `available`, `unavailable` и `cost`."""
    assert SPEC.result["additionalProperties"] is False
    assert sorted(SPEC.result["required"]) == ["available", "cost", "sections",
                                              "unavailable"]
    item = SPEC.result["properties"]["unavailable"]["items"]
    assert item["required"] == ["name", "reason"]
    assert item["additionalProperties"] is False


def test_generated_artifact_matches_spec():
    """`contract/capabilities/context.json` — ровно то, что диктует `ToolSpec`."""
    artifact = ROOT / "contract" / "capabilities" / "context.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text(encoding="utf-8"))
    assert data == SPEC.contract(gather_module.MODULE.id,
                                gather_module.MODULE.capabilities[0])


def test_manifest_publishes_one_tool_and_fs_port():
    assert gather_module.MODULE.id == "context.gather"
    assert tuple(gather_module.MODULE.provides_tools) == ("context",)
    assert tuple(gather_module.MODULE.requires_ports) == ("fs",)
    assert callable(gather_module.MODULE.entrypoints["call"])


@pytest.mark.parametrize("args", [
    {"sections": []},
    {"sections": "project"},
    {"sections": ["project"] * 9},
    {"sections": ["project"], "extra": True},
])
def test_invalid_args_refused_without_paths(args):
    """Схема ловит мусор до домена, в ответе нет абсолютных путей (R-15)."""
    with pytest.raises(AppError) as caught:
        validate_args(SPEC, args)
    assert caught.value.kind == "invalid_input"
    assert not ABS_PATH.search(json.dumps(caught.value.payload(),
                                          ensure_ascii=False))


def test_unknown_section_refuses_whole_call():
    """Неизвестная секция — отказ всего вызова, а не частичный ответ."""
    with pytest.raises(AppError) as caught:
        gather_app.call("context", {"sections": ["project", "secrets"]},
                        _context())
    assert caught.value.kind == "invalid_input"
    assert caught.value.details["reason"] == "unknown_section"


def test_foreign_tool_name_is_unknown_tool():
    """Инструмент чужого модуля владелец не обслуживает (R-03)."""
    with pytest.raises(AppError) as caught:
        gather_app.call("search", {}, _context())
    assert caught.value.kind == "unknown_tool"


def test_result_schema_accepts_answer_without_sections():
    """Ответ с недоступной секцией проходит схему: `unavailable` и есть форма."""
    from python.kernel.schema import validate

    answer = {"sections": {"project": {"root": "D:/p", "project_file": None,
                                       "engine": None, "source": "fs"}},
              "available": ["project"],
              "unavailable": [{"name": "editor", "reason": "no_module"}],
              "cost": "light"}
    assert validate(answer, SPEC.result) == []
