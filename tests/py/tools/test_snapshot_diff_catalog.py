"""D52: catalog entries use the existing structural comparison pipeline."""
import json

import pytest

from tools import snapshot_diff as snapshot


class Agent:
    def __init__(self):
        self.calls = []

    def call(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True, "result": args["value"]}


def record(case_id, value, expected=None):
    return {"id": case_id, "tool": "catalog_probe", "fixture": "minimal",
            "args": {"value": value}, "expect": {"ok": True,
                "result": value if expected is None else expected}}


def replay(tmp_path, payload):
    (tmp_path / "catalog.json").write_text(json.dumps(payload), encoding="utf-8")
    agent = Agent()
    cache = {str(snapshot.FIXTURES / "minimal"): agent}
    return snapshot.run_corpus(cache, tmp_path, {"catalog_probe"}), agent.calls


def test_single_object_retains_existing_pipeline(tmp_path):
    result, calls = replay(tmp_path, record("single", {"text": "unchanged"}))
    assert result == (1, 1, [])
    assert calls == [("catalog_probe", {"value": {"text": "unchanged"}})]


def test_list_catalog_records_reproduce_attribute_error_then_use_same_pipeline(tmp_path):
    result, calls = replay(tmp_path, [record("first", [1, True]), record("second", {"n": 2})])
    assert result == (2, 2, [])
    assert calls == [("catalog_probe", {"value": [1, True]}),
                     ("catalog_probe", {"value": {"n": 2}})]


@pytest.mark.parametrize("payload", [None, "unexpected", 17], ids=["null", "string", "integer"])
def test_unexpected_root_structure_is_an_explicit_error(tmp_path, payload):
    with pytest.raises(ValueError, match="corpus.*object.*list"):
        replay(tmp_path, payload)


@pytest.mark.parametrize("member", [None, [record("nested", 1)]], ids=["null-member", "nested-list"])
def test_invalid_catalog_member_is_not_silently_skipped(tmp_path, member):
    with pytest.raises(ValueError, match="catalog.*object"):
        replay(tmp_path, [record("first", 1), member])


def test_existing_structural_comparison_still_rejects_extra_fields(tmp_path):
    result, _calls = replay(tmp_path, record("extra", {"a": 1, "extra": 2}, {"a": 1}))
    assert result == (1, 0, ["extra: extra: лишнее поле"])


def test_existing_structural_comparison_distinguishes_bool_from_integer(tmp_path):
    result, _calls = replay(tmp_path, record("bool", True, 1))
    assert result[0:2] == (1, 0)
    assert len(result[2]) == 1 and result[2][0].startswith("bool:")
