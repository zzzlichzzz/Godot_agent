"""Native corpus and shared transfer/WAL acceptance pins for C.22."""
import base64
import hashlib
import json
from pathlib import Path

import pytest

from python.kernel.write_plan import Step, WritePlan
from python.modules.editing.rollback import recover
from python.runtime.bootstrap import build_agent, default_ports

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "fixtures/corpus/editing/file_refactor"
CARDS = json.loads((CORPUS / "manifest.json").read_bytes())["cases"]
RAW = b"\xef\xbb\xbfRAW\r\nLONE\rLF\n\x00\xff"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def files(project):
    return {p.relative_to(project).as_posix(): p.read_bytes()
            for p in project.rglob("*") if p.is_file()}


def prepared(tmp_path, steps, expected, initial=None):
    project = tmp_path / "project"
    project.mkdir()
    for rel, raw in (initial or {}).items():
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    ports = default_ports(project, "test", tmp_path / "state")
    plan = WritePlan("plan_c22", "digest_c22", tuple(steps), expected).as_dict()
    ports["journal"].write_prepared(plan, {"tool": "file_refactor"})
    agent = build_agent(project, "test", ports=ports)
    return project, ports, agent, plan


def apply(agent, plan):
    return agent.call("write_apply", {"plan_id": plan["plan_id"], "digest": plan["digest"]})


def move(old="res://old.bin", new="res://nested/new.bin", raw=RAW):
    return Step("move", old, {"dest": new}, sha(raw), "move")


@pytest.mark.parametrize("entry", CARDS, ids=lambda entry: entry["id"])
def test_native_corpus(entry):
    from tools import snapshot_diff
    record = json.loads((CORPUS / entry["file"]).read_bytes())
    assert sha((CORPUS / entry["file"]).read_bytes()) == entry["sha256"]
    assert snapshot_diff.file_refactor_answer(record) == snapshot_diff.file_refactor_expected(record)


@pytest.mark.parametrize("raw", [RAW, b"\x00\xff", b"\xef\xbb\xbfline\r\n", b"line\r", b"line\n", b""])
def test_move_preserves_arbitrary_bytes_and_rollback(tmp_path, raw):
    step = move(raw=raw)
    project, ports, agent, plan = prepared(tmp_path, [step],
        {step.target: sha(raw), step.payload["dest"]: ""}, {"old.bin": raw, "foreign.uid": b"foreign"})
    before = files(project)
    answer = apply(agent, plan)
    assert answer["ok"], answer
    assert (project / "nested/new.bin").read_bytes() == raw
    assert not (project / "old.bin").exists()
    entries = ports["journal"].read(plan["plan_id"])
    assert [r["state"] for r in entries] == ["PREPARED", "APPLYING", "EFFECT_INTENT", "RECEIPT", "COMMITTED"]
    intent = entries[2]
    assert intent["target"] == step.target and intent["dest"] == step.payload["dest"]
    assert intent["expected_hash"] == sha(raw) and intent["op"] == "move"
    result = agent.call("write_rollback", {"entry_id": answer["result"]["entry_id"]})
    assert result["ok"], result
    assert files(project) == before


@pytest.mark.parametrize("change", ["source_modified", "source_deleted", "target_occupied", "later_patch_changed"])
def test_whole_plan_preflight_before_any_effect(tmp_path, change):
    patched = b"references\r\n"
    step = move()
    patch = Step("replace_raw", "res://refs.gd", {"bytes_b64": base64.b64encode(b"after\r\n").decode()}, sha(patched))
    project, ports, agent, plan = prepared(tmp_path, [step, patch],
        {step.target: sha(RAW), step.payload["dest"]: "", patch.target: sha(patched)},
        {"old.bin": RAW, "refs.gd": patched})
    if change == "source_modified":
        (project / "old.bin").write_bytes(b"foreign")
    elif change == "source_deleted":
        (project / "old.bin").unlink()
    elif change == "target_occupied":
        (project / "nested").mkdir()
        (project / "nested/new.bin").write_bytes(b"foreign")
    else:
        (project / "refs.gd").write_bytes(b"foreign")
    before, wal = files(project), ports["journal"].read(plan["plan_id"])
    answer = apply(agent, plan)
    assert not answer["ok"] and answer["kind"] == "stale_plan", answer
    assert files(project) == before
    assert ports["journal"].read(plan["plan_id"]) == wal


def test_same_move_plan_reapply_is_stale_without_effect(tmp_path):
    step = move()
    project, _, agent, plan = prepared(tmp_path, [step],
        {step.target: sha(RAW), step.payload["dest"]: ""}, {"old.bin": RAW})
    assert apply(agent, plan)["ok"]
    before = files(project)
    answer = apply(agent, plan)
    assert not answer["ok"] and answer["kind"] == "stale_plan"
    assert files(project) == before


class Crash(BaseException):
    pass


class FaultWriter:
    def __init__(self, writer, nth=1, crash=False):
        self.writer, self.nth, self.crash, self.effects = writer, nth, crash, 0

    def __getattr__(self, name):
        return getattr(self.writer, name)

    def move(self, old, new):
        self.effects += 1
        if self.effects == self.nth and not self.crash:
            raise OSError("injected second effect")
        self.writer.move(old, new)
        if self.effects == self.nth and self.crash:
            raise Crash("after effect, before RECEIPT")


def test_second_step_failure_compensates_moves_in_reverse(tmp_path):
    steps = [move(), move("res://other.bin", "res://nested/other.bin", b"other")]
    expected = {"res://old.bin": sha(RAW), "res://other.bin": sha(b"other"),
                "res://nested/new.bin": "", "res://nested/other.bin": ""}
    project, ports, _, plan = prepared(tmp_path, steps, expected, {"old.bin": RAW, "other.bin": b"other"})
    before = files(project)
    ports["writer"] = FaultWriter(ports["writer"], 2)
    agent = build_agent(project, "test", ports=ports)
    answer = apply(agent, plan)
    assert not answer["ok"] and answer["kind"] == "internal", answer
    assert files(project) == before
    assert ports["journal"].read(plan["plan_id"])[-1]["state"] == "ROLLED_BACK"


@pytest.mark.parametrize("foreign", [False, True])
def test_recovery_after_effect_before_receipt_and_foreign_guard(tmp_path, foreign):
    step = move()
    project, ports, _, plan = prepared(tmp_path, [step],
        {step.target: sha(RAW), step.payload["dest"]: ""}, {"old.bin": RAW})
    before = files(project)
    normal = ports["writer"]
    ports["writer"] = FaultWriter(normal, crash=True)
    agent = build_agent(project, "test", ports=ports)
    with pytest.raises(Crash):
        apply(agent, plan)
    assert not any(r["state"] == "RECEIPT" for r in ports["journal"].read(plan["plan_id"]))
    assert (project / "nested/new.bin").read_bytes() == RAW
    ports["writer"] = normal
    if foreign:
        (project / "nested/new.bin").write_bytes(b"foreign")
    report = recover(ports)
    assert report[0]["action"] == ("failed" if foreign else "rolled_back"), report
    if foreign:
        assert (project / "nested/new.bin").read_bytes() == b"foreign"
        assert not (project / "old.bin").exists()
    else:
        assert files(project) == before
        assert recover(ports) == []


def test_replace_raw_dependent_on_move_restores_before_owner(tmp_path):
    old, dest, after = "res://old.bin", "res://nested/new.bin", RAW.replace(b"RAW", b"NEW")
    steps = [move(), Step("replace_raw", dest, {"bytes_b64": base64.b64encode(after).decode()}, sha(RAW))]
    project, _, agent, plan = prepared(tmp_path, steps, {old: sha(RAW), dest: ""}, {"old.bin": RAW})
    answer = apply(agent, plan)
    assert answer["ok"], answer
    assert (project / "nested/new.bin").read_bytes() == after
    rolled = agent.call("write_rollback", {"entry_id": answer["result"]["entry_id"]})
    assert rolled["ok"], rolled
    assert files(project) == {"old.bin": RAW}


@pytest.mark.parametrize("payload", [{}, {"bytes_b64": "!invalid!"}, {"bytes_b64": 3}])
def test_invalid_raw_payload_is_refused_before_move(tmp_path, payload):
    steps = [move(), Step("replace_raw", "res://nested/new.bin", payload, sha(RAW))]
    project, _, agent, plan = prepared(tmp_path, steps,
        {"res://old.bin": sha(RAW), "res://nested/new.bin": ""}, {"old.bin": RAW})
    answer = apply(agent, plan)
    assert not answer["ok"] and answer["kind"] == "invalid_input", answer
    assert files(project) == {"old.bin": RAW}


def test_external_move_anchor_is_not_moved_twice_and_rollback_moves_back(tmp_path):
    step = Step("move", "res://old.bin", {"dest": "res://new.bin", "already_moved": True}, sha(RAW), "move")
    project, _, agent, plan = prepared(tmp_path, [step],
        {step.target: "", "res://new.bin": sha(RAW)}, {"new.bin": RAW})
    answer = apply(agent, plan)
    assert answer["ok"], answer
    assert files(project) == {"new.bin": RAW}
    rolled = agent.call("write_rollback", {"entry_id": answer["result"]["entry_id"]})
    assert rolled["ok"], rolled
    assert files(project) == {"old.bin": RAW}


def test_legacy_no_intent_still_left_prepared(tmp_path):
    step = Step("create", "res://new.py", {"text": "new"}, "", "delete")
    project, ports, _, plan = prepared(tmp_path, [step], {step.target: ""}, {"new.py": b"new"})
    ports["journal"].append(plan["plan_id"], {"state": "APPLYING", "entry_id": plan["plan_id"] + "#1"})
    assert recover(ports)[0]["action"] == "left_prepared"
    assert files(project) == {"new.py": b"new"}
