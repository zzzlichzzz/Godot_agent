"""Машина состояний применения: чистые решения домена (ADR-0005)."""

import pytest

from python.kernel.errors import AppError
from python.modules.editing.shared import plan_log
from python.modules.editing.write_apply.domain import core

PLAN = {"plan_id": "plan_x", "digest": "d1",
        "steps": [{"target": "res://src/a.gd", "expected_hash": "h"}],
        "expected": {"res://src/a.gd": "e"}}


def prepared(plan=PLAN):
    return {"state": "PREPARED", "plan": dict(plan), "detail": {"tool": "write_preview"}}


def applying(entry_id="plan_x#1"):
    return {"state": "APPLYING", "entry_id": entry_id, "digest": "d1"}


def receipt(target="res://src/a.gd", entry_id="plan_x#1"):
    return {"state": "RECEIPT", "entry_id": entry_id,
            "receipt": {"step_id": target, "applied_hash": "a", "undo_token": "t"}}


def test_validate_request_accepts_strings():
    assert core.validate_request({"plan_id": " p ", "digest": " d "}) == {
        "plan_id": "p", "digest": "d"}


@pytest.mark.parametrize("args", [None, {}, {"plan_id": "p"}, {"plan_id": "", "digest": "d"},
                                  {"plan_id": "p", "digest": 5}])
def test_validate_request_rejects_bad_input(args):
    with pytest.raises(AppError) as error:
        core.validate_request(args)
    assert error.value.kind == "invalid_input"


def test_missing_plan_is_not_found():
    with pytest.raises(AppError) as error:
        core.decide_apply([], "d1", 0.0, 1.0)
    assert error.value.kind == "not_found"


def test_wrong_digest_is_stale_plan_and_names_both():
    with pytest.raises(AppError) as error:
        core.decide_apply([prepared()], "other", 0.0, 1.0)
    assert error.value.kind == "stale_plan"
    assert error.value.details == {"expected": "d1", "got": "other"}


def test_prepared_fresh_returns_plan():
    assert core.decide_apply([prepared()], "d1", 100.0, 200.0)["plan"]["plan_id"] == "plan_x"


def test_prepared_older_than_ttl_expires_without_effect():
    with pytest.raises(AppError) as error:
        core.decide_apply([prepared()], "d1", 1.0, 902.0)
    assert error.value.kind == "not_found"
    assert error.value.details["state"] == "EXPIRED"


def test_expired_record_is_not_found():
    with pytest.raises(AppError) as error:
        core.decide_apply([prepared(), {"state": "EXPIRED"}], "d1", 0.0, 1.0)
    assert error.value.kind == "not_found"


def test_committed_same_digest_is_reused_without_effect():
    record = dict(prepared(), state="COMMITTED", entry_id="plan_x#1",
                  result={"entry_id": "plan_x#1", "state": "COMMITTED"})
    decision = core.decide_apply([prepared(), record], "d1", 0.0, 1.0)
    assert decision["reuse"] is record


def test_committed_new_digest_still_stale():
    record = dict(prepared(), state="COMMITTED", result={"entry_id": "plan_x#1"})
    with pytest.raises(AppError) as error:
        core.decide_apply([prepared(), record], "d2", 0.0, 1.0)
    assert error.value.kind == "stale_plan"


def test_committed_without_result_is_internal():
    record = dict(prepared(), state="COMMITTED")
    with pytest.raises(AppError) as error:
        core.decide_apply([prepared(), record], "d1", 0.0, 1.0)
    assert error.value.kind == "internal"


@pytest.mark.parametrize("state,reason", [
    ("ROLLED_BACK", "already_rolled_back"),
    ("ROLLING_BACK", "already_rolled_back"),
    ("APPLYING", "plan_state:APPLYING"),
])
def test_busy_or_rolled_states_are_conflict(state, reason):
    entries = [prepared(), {"state": state, "entry_id": "plan_x#1"}]
    with pytest.raises(AppError) as error:
        core.decide_apply(entries, "d1", 0.0, 1.0)
    assert error.value.kind == "conflict"
    assert error.value.details["reason"] == reason


def test_entry_id_and_next_index_number_apply_attempts():
    assert plan_log.entry_id_of("plan_x", 1) == "plan_x#1"
    assert plan_log.next_index([prepared()]) == 1
    assert plan_log.next_index([prepared(), applying()]) == 2
