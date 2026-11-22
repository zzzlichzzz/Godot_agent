"""D20 public surface and strictly typed read-only projection."""
import pytest


def test_read_is_the_only_new_public_tool():
    from python.modules.project_text.read.module import MODULE
    from python.modules.project_text.read.tools import TOOLS
    from python.modules.project_text.tree.module import MODULE as TREE
    from python.modules.project_text.tree.tools import TOOLS as TREE_TOOLS
    assert MODULE.provides_tools == ("read",)
    assert len(TOOLS) == 1 and TOOLS[0].name == "read"
    assert TOOLS[0].effects == "read" and TOOLS[0].idempotent is True
    assert TREE_TOOLS == TREE.provides_tools == TREE.contributes_to == TREE.capabilities == ()
    assert TREE.internal_services == ("project_text.tree",)
    assert set(TREE.entrypoints) == {"build"}


@pytest.mark.parametrize("args", [{}, {"path": "res://x", "unknown": True},
    {"path": "res://x", "max_chars": 0}, {"path": "res://x", "max_chars": 200001},
    {"path": "res://x", "max_chars": True}, {"path": 9}, {"path": "C:/x"}])
def test_read_invalid_arguments_fail_closed(tmp_path, args):
    from python.runtime.bootstrap import build_agent
    answer = build_agent(tmp_path, "test", state_dir=str(tmp_path / "state")).call("read", args)
    assert answer["ok"] is False and answer["kind"] == "invalid_input"


def test_result_rejects_extra_missing_and_wrongly_typed_fields():
    from python.kernel.schema import validate
    from python.modules.project_text.read.tools import TOOLS
    good = {"path": "res://a", "content": "я", "chars": 1, "truncated": False}
    assert validate(good, TOOLS[0].result) == []
    for bad in [{**good, "path": 9}, {**good, "raw": "secret"},
                {key: value for key, value in good.items() if key != "chars"}]:
        assert validate(bad, TOOLS[0].result)


def test_read_root_is_a_directory_not_a_schema_error(tmp_path):
    from python.runtime.bootstrap import build_agent
    answer = build_agent(tmp_path, "test", state_dir=str(tmp_path / "state")).call("read", {"path": "res://"})
    assert not answer["ok"] and answer["kind"] == "not_found"
