"""Actual disk/WAL/common apply/rollback, new C24 cases only; selfcheck feature mask."""
import pytest

from python.kernel.errors import AppError
from tests.py.contract.test_resource_apply_cases import CASES, action, context, sha


@pytest.mark.parametrize("name,raw,operation,marker", CASES, ids=[c[0] for c in CASES])
def test_apply_and_raw_rollback(tmp_path, name, raw, operation, marker):
    from python.modules.editing.resource_ops import app
    project, ctx, agent = context(tmp_path, raw)
    prepared = app.prepare_write(action(operation), ctx)
    assert (project / "data.tres").read_bytes() == raw
    entries = ctx.port("journal").read(prepared["plan_id"])
    step = entries[0]["plan"]["steps"][0]
    assert step["op"] == "replace_raw" and step["expected_hash"] == sha(raw)
    done = app.apply(prepared, ctx)
    assert marker in (project / "data.tres").read_bytes()
    before_repeat = {p.name: p.read_bytes() for p in project.iterdir() if p.is_file()}
    with pytest.raises(AppError) as caught:
        app.apply(prepared, ctx)
    assert caught.value.kind == "stale_plan"
    assert before_repeat == {p.name: p.read_bytes() for p in project.iterdir() if p.is_file()}
    assert agent.call("write_rollback", {"entry_id": done["entry_id"]})["ok"]
    assert (project / "data.tres").read_bytes() == raw


def test_changed_after_plan_is_stale_without_effect(tmp_path):
    from python.modules.editing.resource_ops import app
    project, ctx, _ = context(tmp_path)
    prepared = app.prepare_write(action(CASES[0][2]), ctx)
    foreign = (project / "data.tres").read_bytes() + b"\n; foreign change\n"
    (project / "data.tres").write_bytes(foreign)
    with pytest.raises(AppError) as caught:
        app.apply(prepared, ctx)
    assert caught.value.kind == "stale_plan"
    assert (project / "data.tres").read_bytes() == foreign


def test_occupied_project_lock_conflict(tmp_path):
    from python.modules.editing.resource_ops import app
    project, ctx, _ = context(tmp_path)
    before = (project / "data.tres").read_bytes()
    assert ctx.port("lock").acquire()
    try:
        with pytest.raises(AppError) as caught:
            app.prepare_write(action(CASES[0][2]), ctx)
        assert caught.value.kind == "conflict"
    finally:
        ctx.port("lock").release()
    assert (project / "data.tres").read_bytes() == before
