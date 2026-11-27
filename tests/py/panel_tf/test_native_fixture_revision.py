"""Actual current C.21 inputs, including all seven preexisting Godot sidecars."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "fixtures/corpus/editing/paths_preview"
CASES = sorted(p for p in CORPUS.glob("*.json") if p.name != "manifest.json")
REVISION = json.loads((ROOT / "fixtures/corpus/editor/tf5-panel-ui/input-revision.json").read_bytes())
BASE_BYTES = (CORPUS / "manifest.json").read_bytes()
BASE = json.loads(BASE_BYTES)


def inputs(project):
    return {p.relative_to(project).as_posix(): {
        "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in project.rglob("*") if p.is_file()}


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_current_uid_revision_preserves_exact_native_result(tmp_path, case_path):
    assert hashlib.sha256(BASE_BYTES).hexdigest() == REVISION["base_manifest_sha256"]
    extra = REVISION["added_inputs"]
    assert len(extra) == 7 and not set(extra).intersection(BASE["inputs"])
    assert all(p.endswith(".gd.uid") and p.removesuffix(".uid") in BASE["inputs"] for p in extra)
    fact = next(f for f in BASE["cases"] if f["file"] == case_path.name)
    assert hashlib.sha256(case_path.read_bytes()).hexdigest() == fact["sha256"]
    case = json.loads(case_path.read_bytes())
    project = tmp_path / "project"
    shutil.copytree(ROOT / "fixtures/projects" / case["fixture"], project)
    prefix = case["fixture"] + "/"
    expected = {p[len(prefix):]: f for p, f in {**BASE["inputs"], **extra}.items() if p.startswith(prefix)}
    before = inputs(project)
    assert before == expected  # No ignoring sidecars or unlisted files.
    agent = build_agent(project, profile="test", state_dir=tmp_path / "state")
    first = agent.call("paths_preview", case["args"])
    assert agent.call("paths_preview", case["args"]) == first and inputs(project) == before
    assert first["ok"] == case["expect"]["ok"]
    if first["ok"]:
        assert first["result"] == case["expect"]["result"]
    else:
        assert first["kind"] == case["expect"]["kind"]
        assert first["message"] == case["expected_message"]
