"""C.20 strict ToolSpec for split_apply."""
import importlib

from python.kernel.errors import KINDS


def _spec():
    module = importlib.import_module(
        "python.modules.editing.split_py.tools")
    return module.APPLY


def test_split_apply_is_write_and_not_idempotent():
    spec = _spec()
    assert spec.name == "split_apply" and spec.effects == "write"
    assert spec.idempotent is False and spec.cost == "heavy"
    assert set(spec.errors) <= set(KINDS)


def test_args_are_path_and_accepted_public_plan_only():
    schema = _spec().args
    assert schema["required"] == ["path", "plan"]
    assert set(schema["properties"]) == {"path", "plan"}
    assert schema["properties"]["plan"]["additionalProperties"] is False
    assert schema["additionalProperties"] is False


def test_result_is_exact_native_shape_plus_receipts():
    schema = _spec().result
    expected = {"donor", "written", "moved", "facade_lines", "receipts"}
    assert set(schema["required"]) == expected
    assert set(schema["properties"]) == expected
    assert schema["additionalProperties"] is False
    assert schema["properties"]["receipts"]["items"]["additionalProperties"] is False
