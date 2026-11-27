"""Internal contributor contract; no generated resource ToolSpec/capability."""
import hashlib
import json
from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parents[3] / "fixtures/corpus/editing/resource_ops"
HELPERS = [r for p in sorted(CORPUS.glob("[0-9]*.json")) for r in [json.loads(p.read_text(encoding="utf-8"))]
           if r["internal_call"]["entrypoint"] in ("canonical_digest", "operation_summary", "public_prepared")]


@pytest.mark.parametrize("record", HELPERS, ids=lambda r: r["id"])
def test_native_internal_helper_projection(record):
    from python.kernel.errors import AppError
    from python.modules.editing.resource_ops.domain import core
    try:
        answer = {"ok": True, "result": getattr(core, record["internal_call"]["entrypoint"])(record["input"])}
    except AppError as error:
        answer = dict(error.payload(), ok=False)
    assert answer == record["expect"]


def test_tool_less_manifest_and_fixed_entrypoints():
    from python.modules.editing.resource_ops.module import MODULE
    from python.modules.editing.resource_ops.tools import TOOLS
    assert TOOLS == MODULE.provides_tools == ()
    assert MODULE.contributes_to == ("write_preview",)
    assert MODULE.requires_ports == ("resource_read", "journal", "lock", "writer", "backups")
    assert MODULE.internal_services == ("resource_ops",)
    assert set(MODULE.entrypoints) == {"prepare", "normalize_action", "file_sha256", "canonical_digest",
                                       "public_prepared", "operation_summary", "prepare_write", "apply", "transform_summary"}


@pytest.mark.parametrize("operation", ["replace_raw", "arbitrary.module.function"])
def test_internal_client_refuses_effect_dispatch(tmp_path, operation):
    from tools.probe import resource_client
    assert resource_client(tmp_path, {}, operation) == {
        "ok": False, "kind": "invalid_input", "message": "неизвестная внутренняя операция", "hint": ""}
    assert list(tmp_path.iterdir()) == []


def test_digest_order_and_uuid_independent():
    from python.modules.editing.resource_ops.domain import core
    a = {"x": "текст", "operations": [{"op": "a"}, {"op": "b"}]}
    assert core.canonical_digest(a) == hashlib.sha256(
        b'{"operations":[{"op":"a"},{"op":"b"}],"x":"' + "текст".encode() + b'"}').hexdigest()
    assert core.canonical_digest(a) == core.canonical_digest(dict(reversed(list(a.items()))))
    assert core.canonical_digest(a) != core.canonical_digest(dict(a, operations=list(reversed(a["operations"]))))


@pytest.mark.parametrize("value", [False, True, float("nan"), float("inf"), "1", None])
def test_number_refuses_nonfinite_and_bool(value):
    from python.kernel.errors import AppError
    from python.modules.editing.resource_ops.domain import core
    with pytest.raises(AppError, match="time должен быть конечным числом"):
        core._number(value, "time")
