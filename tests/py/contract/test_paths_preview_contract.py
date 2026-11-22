"""C.21 single read tool, strict D1/D4 schemas and no helper tools."""
import importlib

import pytest

from python.kernel.schema import validate


def spec():
    return importlib.import_module("python.modules.editing.paths_preview.tools").TOOLS[0]


def test_single_native_public_tool():
    tools = importlib.import_module("python.modules.editing.paths_preview.tools").TOOLS
    module = importlib.import_module("python.modules.editing.paths_preview.module").MODULE
    assert len(tools) == 1 and module.provides_tools == ("paths_preview",)
    assert module.requires_ports == ("paths_fs",)
    assert tools[0].effects == "read" and tools[0].idempotent is True
    assert tools[0].requires_preview is False and tools[0].availability == "*"
    assert tools[0].limits["max_file_bytes"] == 5 * 1024 * 1024


def test_exact_result_schema_without_machine_paths_bytes_or_candidate_text():
    schema = spec().result
    fields = {"old_path", "new_path", "is_directory", "file_count", "reference_count", "files", "source_text"}
    assert set(schema["properties"]) == set(schema["required"]) == fields
    assert schema["additionalProperties"] is False
    row = schema["properties"]["files"]["items"]
    assert set(row["properties"]) == {"path", "occurrences", "exact_matches", "rel_matches", "bom"}
    assert row["additionalProperties"] is False
    assert schema["properties"]["source_text"]["type"] == ["string", "null"]


@pytest.mark.parametrize("args", [{}, {"old_path": "res://a"},
    {"old_path": 1, "new_path": "res://b"}, {"old_path": "res://a", "new_path": "res://b", "op": "find"},
    {"old_path": "res://a", "new_path": "res://b", "allow_addons": True}])
def test_rejects_missing_types_and_invented_public_parameters(args):
    assert validate(args, spec().args)
