"""C.21 real agent/native corpus, exact messages and byte-invariance."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from python.kernel.schema import validate
from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "fixtures/corpus/editing/paths_preview"
CASES = sorted(p for p in CORPUS.glob("*.json") if p.name != "manifest.json")
MANIFEST = json.loads((CORPUS / "manifest.json").read_bytes())
UID_REVISION = json.loads((ROOT / "fixtures/corpus/editor/tf5-panel-ui/input-revision.json").read_bytes())


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_actual_native_corpus_is_exact_and_idempotent(tmp_path, case_path):
    fact = next(f for f in MANIFEST["cases"] if f["file"] == case_path.name)
    assert hashlib.sha256(case_path.read_bytes()).hexdigest() == fact["sha256"]
    case = json.loads(case_path.read_bytes())
    project = tmp_path / "project"
    shutil.copytree(ROOT / "fixtures/projects" / case["fixture"], project)
    agent = build_agent(project, profile="test", state_dir=tmp_path / "state")
    before = hashes(project)
    prefix = case["fixture"] + "/"
    assert hashlib.sha256((CORPUS / "manifest.json").read_bytes()).hexdigest() == UID_REVISION["base_manifest_sha256"]
    extra = UID_REVISION["added_inputs"]
    assert not set(extra) & MANIFEST["inputs"].keys()
    expected_inputs = {p[len(prefix):]: f for p, f in {**MANIFEST["inputs"], **extra}.items()
                       if p.startswith(prefix)}
    assert {p: {"bytes": (project / p).stat().st_size, "sha256": h} for p, h in before.items()} == expected_inputs
    first = agent.call("paths_preview", case["args"])
    second = agent.call("paths_preview", case["args"])
    assert first == second and hashes(project) == before
    assert first["ok"] == case["expect"]["ok"], first
    if first["ok"]:
        assert first["result"] == case["expect"]["result"]
        from python.modules.editing.paths_preview.tools import TOOLS
        assert validate(first["result"], TOOLS[0].result) == []
    else:
        assert first["kind"] == case["expect"]["kind"]
        assert first["message"] == case["expected_message"]


def test_extension_and_addon_filters_are_not_convenience_search(tmp_path):
    fixtures = ROOT / "fixtures/projects/corpus/editing/paths_preview"
    assert {p.relative_to(ROOT / "fixtures/projects").as_posix() for p in fixtures.rglob("*.gd") if p.is_file()} == {
        p for p in MANIFEST["inputs"] if p.lower().endswith(".gd")}
    source = ROOT / "fixtures/projects/corpus/editing/paths_preview/basic"
    project = tmp_path / "project"
    shutil.copytree(source, project)
    agent = build_agent(project, profile="test", state_dir=tmp_path / "state")
    result = agent.call("paths_preview", {"old_path": "res://assets/item.gd", "new_path": "res://next/item.gd"})
    assert result["ok"], result
    paths = [r["path"] for r in result["result"]["files"]]
    assert len(paths) == 12 and result["result"]["file_count"] == 13
    assert paths == sorted(paths)
    assert not any("addons/" in p or "excluded/" in p or "__pycache__/" in p for p in paths)
    row = next(r for r in result["result"]["files"] if r["path"] == "res://b.gd")
    assert [r[0] for r in row["rel_matches"]] != sorted(r[0] for r in row["rel_matches"])


def test_source_policy_is_after_missing_and_target_conflict(tmp_path):
    project = tmp_path / "project"
    (project / "addons/x").mkdir(parents=True)
    (project / "addons/x/a.gd").write_text("extends Node\n", encoding="utf-8")
    (project / "b.gd").write_text("extends Node\n", encoding="utf-8")
    agent = build_agent(project, profile="test", state_dir=tmp_path / "state")
    assert agent.call("paths_preview", {"old_path": "res://addons/x/missing.gd", "new_path": "res://b.gd"})["kind"] == "not_found"
    assert agent.call("paths_preview", {"old_path": "res://addons/x/a.gd", "new_path": "res://b.gd"})["kind"] == "conflict"
    assert agent.call("paths_preview", {"old_path": "res://addons/x/a.gd", "new_path": "res://new.gd"})["kind"] == "denied"


@pytest.mark.parametrize("size,expected", [(4 * 1024 * 1024 + 50, 1), (5 * 1024 * 1024 + 50, 0)])
def test_candidate_five_mib_limit_is_native_and_local(tmp_path, size, expected):
    (tmp_path / "a.gd").write_bytes(b"extends Node\n")
    tail = b'"res://a.gd"\n'
    (tmp_path / "ref.gd").write_bytes(b"#" + b"x" * (size - len(tail) - 1) + tail)
    agent = build_agent(tmp_path, profile="test", state_dir=tmp_path.parent / "state")
    answer = agent.call("paths_preview", {"old_path": "res://a.gd", "new_path": "res://next.gd"})
    assert answer["ok"] and answer["result"]["reference_count"] == expected


def test_invalid_utf8_and_bom_relative_offsets_follow_native_text(tmp_path):
    (tmp_path / "a.gd").write_bytes(b"extends Node\n")
    raw = b'\xef\xbb\xbf#\xff\r\nconst A=preload("a.gd")\r# tail\n'
    (tmp_path / "ref.gd").write_bytes(raw)
    agent = build_agent(tmp_path, profile="test", state_dir=tmp_path.parent / "state")
    answer = agent.call("paths_preview", {"old_path": "res://a.gd", "new_path": "res://next.gd"})
    assert answer["ok"], answer
    row = answer["result"]["files"][0]
    # utf-8-sig fails; native fallback retains U+FEFF and replaces invalid bytes.
    text = raw.decode("utf-8", errors="replace")
    offset = text.index("a.gd")
    assert row["bom"] is True and row["rel_matches"] == [[offset, offset + 4, "a.gd"]]
    assert (tmp_path / "ref.gd").read_bytes() == raw
