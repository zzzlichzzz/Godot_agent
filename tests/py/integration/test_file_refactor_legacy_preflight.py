"""C.22 preflight keeps C.20 delete errors, without a prior effect or WAL change."""
import hashlib

import pytest

from python.kernel.write_plan import Step, WritePlan
from python.runtime.bootstrap import build_agent, default_ports


@pytest.mark.parametrize("directory,kind", [(False, "not_found"), (True, "invalid_input")])
def test_delete_error_before_an_earlier_create(tmp_path, directory, kind):
    project = tmp_path / "project"
    project.mkdir()
    if directory:
        (project / "missing").mkdir()
    ports = default_ports(project, "test", tmp_path / "state")
    sha = hashlib.sha256(b"unused").hexdigest()
    steps = (Step("create", "res://new.py", {"text": "new\n"}, "", "delete"),
             Step("delete", "res://missing", {}, sha))
    plan = WritePlan("plan_legacy", "digest", steps,
                     {"res://new.py": "", "res://missing": sha}).as_dict()
    ports["journal"].write_prepared(plan, {"tool": "file_refactor"})
    before = ports["journal"].read(plan["plan_id"])
    answer = build_agent(project, "test", ports=ports).call("write_apply",
        {"plan_id": plan["plan_id"], "digest": plan["digest"]})
    assert not answer["ok"] and answer["kind"] == kind, answer
    assert not (project / "new.py").exists()
    assert ports["journal"].read(plan["plan_id"]) == before
    assert (project / "missing").is_dir() == directory
