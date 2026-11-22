"""C.20: create/delete проходят общий WAL apply/rollback/recovery."""
import hashlib
from pathlib import Path

from python.kernel.write_plan import Step, WritePlan
from python.modules.editing.rollback import recover
from python.runtime.bootstrap import build_agent, default_ports


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _agent(tmp_path, steps, expected, plan_id="plan_c20"):
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    state = tmp_path / "state"
    ports = default_ports(str(project), "test", str(state))
    plan = WritePlan(plan_id, "digest_c20", tuple(steps), expected).as_dict()
    ports["journal"].write_prepared(plan, detail={"tool": "c20_test"})
    agent = build_agent(str(project), profile="test", state_dir=str(state), ports=ports)
    return project, ports, agent, plan


def test_create_apply_and_rollback_remove_created_file(tmp_path):
    target = "res://new.py"
    step = Step("create", target, {"text": "new\n", "newline": "lf"},
                expected_hash="", compensates="delete")
    project, _, agent, plan = _agent(tmp_path, [step], {target: ""})
    applied = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                          "digest": plan["digest"]})
    assert applied["ok"], applied
    assert (project / "new.py").read_bytes() == b"new\n"
    rolled = agent.call("write_rollback", {"entry_id": applied["result"]["entry_id"]})
    assert rolled["ok"], rolled
    assert not (project / "new.py").exists()


def test_occupied_create_is_stale_and_preserves_bytes(tmp_path):
    target = "res://new.py"
    step = Step("create", target, {"text": "new\n"}, "", "delete")
    project, _, agent, plan = _agent(tmp_path, [step], {target: ""})
    (project / "new.py").write_bytes(b"occupied\n")
    answer = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                         "digest": plan["digest"]})
    assert not answer["ok"] and answer["kind"] == "stale_plan"
    assert (project / "new.py").read_bytes() == b"occupied\n"


def test_delete_apply_and_rollback_restore_exact_bytes(tmp_path):
    raw = b"\xef\xbb\xbfline\r\n"
    target = "res://old.py"
    step = Step("delete", target, {}, _sha(raw))
    project, _, agent, plan = _agent(tmp_path, [step], {target: _sha(raw)})
    (project / "old.py").write_bytes(raw)
    applied = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                          "digest": plan["digest"]})
    assert applied["ok"], applied
    assert not (project / "old.py").exists()
    rolled = agent.call("write_rollback", {"entry_id": applied["result"]["entry_id"]})
    assert rolled["ok"], rolled
    assert (project / "old.py").read_bytes() == raw


def test_delete_missing_is_not_found_and_directory_is_invalid(tmp_path):
    target = "res://folder"
    step = Step("delete", target, {}, _sha(b"unused"))
    project, _, agent, plan = _agent(tmp_path, [step], {target: _sha(b"unused")})
    missing = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                          "digest": plan["digest"]})
    assert not missing["ok"] and missing["kind"] == "not_found"
    (project / "folder").mkdir()
    project, _, agent, plan = _agent(tmp_path, [step], {target: _sha(b"unused")},
                                      plan_id="plan_c20_dir")
    answer = agent.call("write_apply", {"plan_id": plan["plan_id"],
                                         "digest": plan["digest"]})
    assert not answer["ok"] and answer["kind"] == "invalid_input"
    assert (project / "folder").is_dir()


def test_recovery_deletes_receipted_create(tmp_path):
    target, raw = "res://new.py", b"new\n"
    step = Step("create", target, {"text": "new\n"}, "", "delete")
    project, ports, _, plan = _agent(tmp_path, [step], {target: ""})
    (project / "new.py").write_bytes(raw)
    entry_id = plan["plan_id"] + "#1"
    ports["journal"].append(plan["plan_id"], {"state": "APPLYING",
                                               "entry_id": entry_id})
    ports["journal"].append(plan["plan_id"], {"state": "RECEIPT",
        "entry_id": entry_id, "receipt": {"step_id": target,
        "applied_hash": _sha(raw), "undo_token": ""}})
    assert {"plan_id": plan["plan_id"], "action": "rolled_back"} in recover(ports)
    assert not (project / "new.py").exists()


def test_recovery_never_deletes_externally_changed_create(tmp_path):
    target, raw = "res://new.py", b"new\n"
    step = Step("create", target, {"text": "new\n"}, "", "delete")
    project, ports, _, plan = _agent(tmp_path, [step], {target: ""})
    (project / "new.py").write_bytes(b"external\n")
    entry_id = plan["plan_id"] + "#1"
    ports["journal"].append(plan["plan_id"], {"state": "APPLYING",
                                               "entry_id": entry_id})
    ports["journal"].append(plan["plan_id"], {"state": "RECEIPT",
        "entry_id": entry_id, "receipt": {"step_id": target,
        "applied_hash": _sha(raw), "undo_token": ""}})
    assert recover(ports)[0]["action"] == "failed"
    assert (project / "new.py").read_bytes() == b"external\n"
