"""C.20 corpus: split plan is confirmed and applied only through WAL."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent, default_ports
from python.modules.editing.split_py import apply_flow

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "fixtures/corpus/editing/split_py"
PROJECTS = ROOT / "fixtures/projects"


def _case(number):
    path = next(CORPUS.glob("%03d-*.json" % number))
    return json.loads(path.read_bytes())


def _agent(tmp_path, case):
    project = tmp_path / "project"
    shutil.copytree(PROJECTS / case["fixture"], project)
    return project, build_agent(str(project), profile="test",
                                state_dir=str(tmp_path / "state"))


def _plan(agent, case):
    args = case["prepare"]["args"]
    answer = agent.call("split_plan", args)
    assert answer["ok"], answer
    return answer["result"]


def _apply(agent, case, plan):
    return agent.call("split_apply", {"path": case["args"]["path"],
                                       "plan": plan})


def _tree(project):
    return {path.relative_to(project).as_posix(): hashlib.sha256(
        path.read_bytes()).hexdigest() for path in sorted(project.rglob("*"))
        if path.is_file()}


def test_two_module_success_has_exact_native_fields_and_receipts(tmp_path):
    case = _case(97)
    project, agent = _agent(tmp_path, case)
    answer = _apply(agent, case, _plan(agent, case))
    assert answer["ok"], answer
    result = answer["result"]
    assert set(result) == {"donor", "written", "moved", "facade_lines", "receipts"}
    assert {k: result[k] for k in case["expect"]["result"]} == case["expect"]["result"]
    assert len(result["receipts"]) == 3
    assert (project / "one.py").is_file() and (project / "two.py").is_file()


@pytest.mark.parametrize("number,kind", [(98, "invalid_input"),
                                           (100, "stale_plan"),
                                           (103, "stale_plan"),
                                           (108, "invalid_input")])
def test_refusals_leave_tree_unchanged(tmp_path, number, kind):
    case = _case(number)
    project, agent = _agent(tmp_path, case)
    plan = _plan(agent, case)
    for rel, text in case.get("setup", {}).get("write_text", {}).items():
        (project / rel).write_text(text, encoding="utf-8")
    before = _tree(project)
    answer = _apply(agent, case, plan)
    assert not answer["ok"] and answer["kind"] == kind
    assert _tree(project) == before


def test_missing_donor_is_not_found(tmp_path):
    case = _case(99)
    project, agent = _agent(tmp_path, case)
    plan = _plan(agent, case)
    (project / "donor.py").unlink()
    answer = _apply(agent, case, plan)
    assert not answer["ok"] and answer["kind"] == "not_found"


def test_repeat_apply_is_stale_without_second_effect(tmp_path):
    case = _case(104)
    project, agent = _agent(tmp_path, case)
    plan = _plan(agent, case)
    assert _apply(agent, case, plan)["ok"]
    before = _tree(project)
    second = _apply(agent, case, plan)
    assert not second["ok"] and second["kind"] == "stale_plan"
    assert _tree(project) == before


def test_donor_bom_and_crlf_style_survives_apply(tmp_path):
    case = _case(105)
    project, agent = _agent(tmp_path, case)
    answer = _apply(agent, case, _plan(agent, case))
    assert answer["ok"], answer
    raw = (project / "donor.py").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_all_generated_text_is_compiled_before_first_effect(tmp_path, monkeypatch):
    case = _case(97)
    project, agent = _agent(tmp_path, case)
    public = _plan(agent, case)
    native = apply_flow.plan.plan_split

    def poisoned(*args, **kwargs):
        prepared = native(*args, **kwargs)
        prepared["modules"][1]["text"] = "def beta(:\n"
        prepared["errors"] = []
        return prepared

    monkeypatch.setattr(apply_flow.plan, "plan_split", poisoned)
    before = _tree(project)
    answer = _apply(agent, case, public)
    assert not answer["ok"] and answer["kind"] == "invalid_input"
    assert _tree(project) == before


def test_facade_is_compiled_before_first_effect(tmp_path, monkeypatch):
    case = _case(102)
    project, agent = _agent(tmp_path, case)
    public = _plan(agent, case)
    native = apply_flow.plan.plan_split

    def poisoned(*args, **kwargs):
        prepared = native(*args, **kwargs)
        prepared["facade"]["text"] = "return 1\n"
        prepared["errors"] = []
        return prepared

    monkeypatch.setattr(apply_flow.plan, "plan_split", poisoned)
    before = _tree(project)
    answer = _apply(agent, case, public)
    assert not answer["ok"] and answer["kind"] == "invalid_input"
    assert _tree(project) == before


class _FailSecondCreate:
    def __init__(self, writer):
        self._writer, self._count = writer, 0

    def __getattr__(self, name):
        return getattr(self._writer, name)

    def create(self, rel, data):
        self._count += 1
        if self._count == 2:
            raise OSError("injected second create failure")
        return self._writer.create(rel, data)


def test_second_create_failure_rolls_back_first_and_records_wal(tmp_path):
    case = _case(106)
    project = tmp_path / "project"
    shutil.copytree(PROJECTS / case["fixture"], project)
    state = tmp_path / "state"
    ports = default_ports(str(project), "test", str(state))
    ports["writer"] = _FailSecondCreate(ports["writer"])
    agent = build_agent(str(project), profile="test", state_dir=str(state), ports=ports)
    public, before = _plan(agent, case), _tree(project)
    answer = _apply(agent, case, public)
    assert not answer["ok"] and answer["kind"] == "internal"
    assert _tree(project) == before
    plan_id = ports["journal"].plan_ids()[0]
    states = [item["state"] for item in ports["journal"].read(plan_id)]
    assert states == case["expect"]["wal_states"]


def test_missing_donor_hash_is_rejected_without_effect(tmp_path):
    case = _case(97)
    project, agent = _agent(tmp_path, case)
    public, before = _plan(agent, case), _tree(project)
    del public["donor_sha256"]
    answer = _apply(agent, case, public)
    assert not answer["ok"] and answer["kind"] == "invalid_input"
    assert _tree(project) == before
