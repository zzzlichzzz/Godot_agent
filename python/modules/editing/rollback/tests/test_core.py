"""Правила отката: порядок квитанций и запреты (ADR-0005, §6.6)."""

import pytest

from python.kernel.errors import AppError
from python.modules.editing.rollback.domain import core

PLAN = {"plan_id": "plan_x", "digest": "d1", "expected": {"res://a.gd": "ea",
                                                          "res://b.gd": "eb"}}


def prepared():
    return {"state": "PREPARED", "plan": dict(PLAN)}


def receipt(target, entry_id="plan_x#1"):
    return {"state": "RECEIPT", "entry_id": entry_id,
            "receipt": {"step_id": target, "applied_hash": "h" + target,
                        "undo_token": "plan_x/%s.bin" % target[-3]}}


def test_validate_request_parses_entry_id():
    assert core.validate_request({"entry_id": " plan_x#2 "}) == {
        "entry_id": "plan_x#2", "plan_id": "plan_x", "index": 2}


@pytest.mark.parametrize("args", [None, {}, {"entry_id": ""}, {"entry_id": "plan_x"},
                                  {"entry_id": "plan_x#0"}, {"entry_id": "#1"}])
def test_validate_request_rejects_bad_entry_id(args):
    with pytest.raises(AppError) as error:
        core.validate_request(args)
    assert error.value.kind == "invalid_input"


def test_missing_entry_is_not_found():
    with pytest.raises(AppError) as error:
        core.check_can_rollback([], "plan_x#1")
    assert error.value.kind == "not_found"


def test_already_rolled_back_is_conflict_not_silent_success():
    entries = [prepared(), {"state": "ROLLED_BACK", "entry_id": "plan_x#1"}]
    with pytest.raises(AppError) as error:
        core.check_can_rollback(entries, "plan_x#1")
    assert error.value.kind == "conflict"
    assert error.value.details["reason"] == "already_rolled_back"


def test_prepared_is_not_rollbackable():
    with pytest.raises(AppError) as error:
        core.check_can_rollback([prepared()], "plan_x#1")
    assert error.value.details["reason"] == "plan_state:PREPARED"


def test_without_receipts_rollback_refuses():
    entries = [prepared(), {"state": "COMMITTED", "entry_id": "plan_x#1"}]
    with pytest.raises(AppError) as error:
        core.check_can_rollback(entries, "plan_x#1")
    assert error.value.details["reason"] == "no_receipts"


def test_order_is_reversed_and_scoped_to_entry():
    entries = [prepared(), receipt("res://a.gd"), receipt("res://b.gd"),
               receipt("res://c.gd", entry_id="plan_x#2")]
    ordered = core.order(entries, "plan_x#1")
    assert [item["step_id"] for item in ordered] == ["res://b.gd", "res://a.gd"]


def test_restored_paths_let_repeat_continue():
    entries = [prepared(), {"state": "RESTORED", "entry_id": "plan_x#1",
                            "path": "res://a.gd"},
               {"state": "RESTORED", "entry_id": "plan_x#2", "path": "res://b.gd"}]
    assert core.restored_of(entries, "plan_x#1") == {"res://a.gd"}
    assert core.restored_of(entries, "plan_x#2") == {"res://b.gd"}
