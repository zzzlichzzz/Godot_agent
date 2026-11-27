"""C.22 cross-module ADR-0016 boundaries for accepted file operations.

These are new C.22 safety cases, not copies of the frozen test suite. All IO
uses isolated projects; the receipt-gap injection is explicitly controlled.
"""
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from python.kernel.paths import PathPolicy
from python.kernel.write_plan import Step, WritePlan
from python.modules.editing.rollback import recover
from python.modules.editing.shared import funnel, script_edits
from python.runtime.bootstrap import default_ports

RAW = b"\xef\xbb\xbfbefore\r\n"
TARGET = "res://item.gd"
OPS = ("create", "delete", "script_edit")
SAFETY_CASE = Path(__file__).resolve().parents[3] / (
    "fixtures/corpus/editing/file_refactor/cases/safety-create-receipt-gap.json")


class Crash(BaseException):
    """A persisted process-interruption boundary, not a regular apply error."""


def setup(tmp_path, op):
    project = tmp_path / "project"
    project.mkdir()
    expected = "" if op == "create" else script_edits.sha256(RAW)
    if op != "create":
        (project / "item.gd").write_bytes(RAW)
    if op == "create":
        case = json.loads(SAFETY_CASE.read_bytes())
        step = Step(op, case["target"], case["payload"], "", "delete")
    elif op == "delete":
        step = Step(op, TARGET, {}, expected, "create")
    else:
        step = Step(op, TARGET, {"edits": [{"start": 0, "end": 6,
                    "replacement": "after"}]}, script_edits.sha256_text("before\n"))
    ports = default_ports(project, "test", tmp_path / "state")
    plan = WritePlan("plan_intent", "digest_intent", (step,), {TARGET: expected}).as_dict()
    journal = ports["journal"]
    journal.write_prepared(plan, {"tool": "file_refactor"})
    journal.append(plan["plan_id"], {"state": "APPLYING", "entry_id": "plan_intent#1"})
    ctx = SimpleNamespace(path_policy=PathPolicy(str(project)), port=ports.__getitem__)
    return project, ports, plan, ctx


def execute(ctx, plan):
    return funnel.apply_file_step(ctx, plan, plan["plan_id"], "plan_intent#1", 1,
                                  plan["steps"][0])


def content(project):
    return {p.relative_to(project).as_posix(): p.read_bytes()
            for p in project.rglob("*") if p.is_file()}


@pytest.mark.parametrize("op", OPS)
def test_intent_is_durable_before_every_accepted_file_effect(tmp_path, monkeypatch, op):
    project, ports, plan, ctx = setup(tmp_path, op)
    method = {"create": "create", "delete": "delete", "script_edit": "write_raw"}[op]
    original = getattr(ports["writer"], method)
    seen = []

    def effect(*args):
        entries = ports["journal"].read(plan["plan_id"])
        assert entries[-1]["state"] == "EFFECT_INTENT", entries
        intent = entries[-1]
        assert intent["entry_id"] == "plan_intent#1"
        assert intent["op"] == op and intent["target"] == TARGET
        assert intent["expected_hash"] == plan["expected"][TARGET]
        if op != "create":
            assert ports["backups"].get(intent["undo_token"]) == RAW
        seen.append(intent)
        return original(*args)

    monkeypatch.setattr(ports["writer"], method, effect)
    receipt = execute(ctx, plan)
    assert len(seen) == 1
    entries = ports["journal"].read(plan["plan_id"])
    assert entries[-1] == {"state": "RECEIPT", "entry_id": "plan_intent#1", "receipt": receipt}
    assert seen[0]["applied_hash"] == receipt["applied_hash"]


@pytest.mark.parametrize("op", OPS)
def test_failed_intent_append_leaves_project_unchanged(tmp_path, monkeypatch, op):
    project, ports, plan, ctx = setup(tmp_path, op)
    before = content(project)
    append = ports["journal"].append

    def fail_intent(plan_id, record):
        if record["state"] == "EFFECT_INTENT":
            raise OSError("injected durable intent failure")
        return append(plan_id, record)

    monkeypatch.setattr(ports["journal"], "append", fail_intent)
    with pytest.raises(OSError, match="durable intent"):
        execute(ctx, plan)
    assert content(project) == before
    assert not any(r["state"] == "RECEIPT" for r in ports["journal"].read(plan["plan_id"]))


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("foreign", [False, True])
def test_accepted_effect_without_receipt_is_recovered_or_conflicted(tmp_path, monkeypatch, op, foreign):
    project, ports, plan, ctx = setup(tmp_path, op)
    before = content(project)
    append = ports["journal"].append

    def crash_before_receipt(plan_id, record):
        if record["state"] == "RECEIPT":
            raise Crash("effect persisted, RECEIPT not appended")
        return append(plan_id, record)

    monkeypatch.setattr(ports["journal"], "append", crash_before_receipt)
    with pytest.raises(Crash):
        execute(ctx, plan)
    monkeypatch.setattr(ports["journal"], "append", append)
    records = ports["journal"].read(plan["plan_id"])
    assert records[-1]["state"] == "EFFECT_INTENT", records
    assert records[-1]["op"] == op and records[-1]["target"] == TARGET
    assert not any(r["state"] == "RECEIPT" for r in records)
    assert content(project) != before, "the effect must actually have persisted"
    if op == "create":
        case = json.loads(SAFETY_CASE.read_bytes())
        assert case["oracle"] == "our safety behaviour, not native parity"
        assert (project / "item.gd").read_bytes() == base64.b64decode(
            case["expect"]["effect_bytes_b64"], validate=True)
    if foreign:
        (project / "item.gd").write_bytes(b"foreign user change\r\n")
    post = content(project)
    report = recover(ports)
    assert report[0]["action"] == ("failed" if foreign else "rolled_back"), report
    if foreign:
        assert report[0]["reason"] == "conflict"
        assert content(project) == post
    else:
        assert content(project) == before
        assert recover(ports) == []


@pytest.mark.parametrize("op", OPS)
def test_intent_without_started_effect_restores_pre_state(tmp_path, monkeypatch, op):
    project, ports, plan, ctx = setup(tmp_path, op)
    before = content(project)
    method = {"create": "create", "delete": "delete", "script_edit": "write_raw"}[op]
    original = getattr(ports["writer"], method)

    def crash_before_effect(*args):
        raise Crash("intent persisted, effect not started")

    monkeypatch.setattr(ports["writer"], method, crash_before_effect)
    with pytest.raises(Crash):
        execute(ctx, plan)
    monkeypatch.setattr(ports["writer"], method, original)
    assert content(project) == before
    assert recover(ports)[0]["action"] == "rolled_back"
    assert content(project) == before
