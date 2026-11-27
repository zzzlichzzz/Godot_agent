"""D19 internal scenario field: exact effects and client route, no public tool."""
import base64

import pytest

from tests.py.contract.test_resource_apply_cases import ANIMATION, CASES, action


def test_write_scenario_routes_real_client_and_exact_rollback():
    from tools.probe import resource_corpus_answer
    after = ANIMATION.replace(b"length = 1.0", b"length = 2.0")
    record = {"internal_call": {"module_id": "editing.resource_ops", "entrypoint": "prepare_write"},
              "fixture": "schema", "input": action(CASES[0][2]),
              "resource_write_scenario": {"seed_bytes": {"data.tres": base64.b64encode(ANIMATION).decode()},
                                          "after_bytes_b64": base64.b64encode(after).decode(), "repeat": True}}
    answer = resource_corpus_answer(record)
    assert answer["ok"] and answer["result"]["rollback_exact"] is True
    assert answer["result"]["repeat_kind"] == "stale_plan" and answer["result"]["steps"] == 1


@pytest.mark.parametrize("member", ["../escape", "addons/x", "C:/absolute"])
def test_corpus_seed_is_data_not_unchecked_path(member):
    from tools.probe import resource_corpus_answer
    record = {"internal_call": {"module_id": "editing.resource_ops", "entrypoint": "prepare_write"},
              "fixture": "schema", "input": action(CASES[0][2]),
              "resource_write_scenario": {"seed_bytes": {member: "YQ=="}}}
    with pytest.raises(AssertionError):
        resource_corpus_answer(record)
