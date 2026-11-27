"""C24 genuine WAL: dependency/target staleness, conflict, failure compensation."""
import pytest

from tests.py.contract.test_resource_apply_cases import CASES, TEXTURE, action, context


def tree(project):
    return {p.relative_to(project).as_posix(): p.read_bytes() for p in project.rglob("*") if p.is_file()}


def test_multiple_operations_one_target_step(tmp_path):
    from python.modules.editing.resource_ops import app
    project, ctx, agent = context(tmp_path)
    request = action(CASES[0][2])
    request["operations"].append(CASES[2][2])
    before = tree(project)
    prepared = app.prepare_write(request, ctx)
    plan = ctx.port("journal").read(prepared["plan_id"])[0]["plan"]
    assert len(plan["steps"]) == 1 and plan["steps"][0]["op"] == "replace_raw"
    done = app.apply(prepared, ctx)
    assert b"length = 2.0" in (project / "data.tres").read_bytes()
    assert b"tracks/0/type" in (project / "data.tres").read_bytes()
    assert agent.call("write_rollback", {"entry_id": done["entry_id"]})["ok"]
    assert tree(project) == before


def test_dependency_change_before_apply_no_effect(tmp_path):
    from python.modules.editing.resource_ops import app
    project, ctx, _ = context(tmp_path, CASES[1][1])
    prepared = app.prepare_write(action(CASES[1][2]), ctx)
    (project / "new.tres").write_bytes(TEXTURE + b"; foreign dependency\n")
    before = tree(project)
    from python.kernel.errors import AppError
    with pytest.raises(AppError) as caught:
        app.apply(prepared, ctx)
    assert caught.value.kind == "stale_plan" and tree(project) == before


def test_expected_raw_hash_refusal_before_wal(tmp_path):
    from python.modules.editing.resource_ops import app
    from python.kernel.errors import AppError
    project, ctx, _ = context(tmp_path)
    before = tree(project)
    with pytest.raises(AppError) as caught:
        app.prepare_write(action(CASES[0][2]), ctx, expected_hash="0" * 64)
    assert caught.value.kind == "stale_plan" and tree(project) == before
    assert ctx.port("journal").plan_ids() == []


def test_rollback_preserves_foreign_poststate(tmp_path):
    from python.modules.editing.resource_ops import app
    project, ctx, agent = context(tmp_path)
    done = app.apply(app.prepare_write(action(CASES[0][2]), ctx), ctx)
    (project / "data.tres").write_bytes(b"foreign poststate\r\n")
    before = tree(project)
    answer = agent.call("write_rollback", {"entry_id": done["entry_id"]})
    assert answer["ok"] is False and answer["kind"] == "conflict" and tree(project) == before


def test_receipt_failure_compensates_raw_bytes(tmp_path, monkeypatch):
    from python.modules.editing.resource_ops import app
    from python.kernel.errors import AppError
    project, ctx, _ = context(tmp_path)
    prepared = app.prepare_write(action(CASES[0][2]), ctx)
    journal, before = ctx.port("journal"), tree(project)
    original = journal.append

    def fail_receipt(plan_id, record):
        if record["state"] == "RECEIPT":
            raise OSError("witnessed receipt failure")
        return original(plan_id, record)

    monkeypatch.setattr(journal, "append", fail_receipt)
    with pytest.raises(AppError) as caught:
        app.apply(prepared, ctx)
    assert caught.value.kind == "internal" and tree(project) == before
    assert [r["state"] for r in journal.read(prepared["plan_id"])] == [
        "PREPARED", "APPLYING", "EFFECT_INTENT", "ROLLING_BACK", "RESTORED", "ROLLED_BACK"]


def test_funnel_apply_preserves_exact_lone_cr_bytes(tmp_path):
    from python.modules.editing.resource_ops import app
    raw = CASES[0][1].replace(b"; input comment must not be mistaken for an operation\n", b"").replace(b"\n", b"\r")
    project, ctx, _ = context(tmp_path, raw)
    app.apply(app.prepare_write(action(CASES[0][2]), ctx), ctx)
    assert (project / "data.tres").read_bytes() == raw.replace(b"length = 1.0", b"length = 2.0")


def test_funnel_apply_preserves_exact_mixed_eol_bytes(tmp_path):
    from python.modules.editing.resource_ops import app
    raw = CASES[0][1].replace(b"\n", b"\r\n", 2)
    project, ctx, _ = context(tmp_path, raw)
    app.apply(app.prepare_write(action(CASES[0][2]), ctx), ctx)
    assert (project / "data.tres").read_bytes() == raw.replace(b"length = 1.0", b"length = 2.0")
