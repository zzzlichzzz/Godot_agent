"""C.23 real disk/client/metadata routing; no public resource dispatch."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "fixtures/corpus/editing/resource_ops"
RECORDS = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CORPUS.glob("[0-9]*.json"))]


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: r["id"])
def test_native_client(record):
    from tools.probe import resource_corpus_answer
    assert resource_corpus_answer(record) == record["expect"]


def test_tool_less_with_corpus_reaches_snapshot(monkeypatch):
    spec = importlib.util.spec_from_file_location("c23_selfcheck", ROOT / "tools/selfcheck.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    calls = []
    monkeypatch.setattr(gate, "_spec", lambda _: (SimpleNamespace(
        provides_tools=(), contributes_to=("write_preview",), corpus="corpus"), ""))
    monkeypatch.setattr(gate, "run_check", lambda name, args: calls.append((name, args)) or ("ok", "кейсов 185"))
    assert gate.check_corpus("editing.resource_ops") == ("ok", "кейсов 185")
    assert calls == [("corpus", ["tools/snapshot_diff.py", "editing.resource_ops"])]


def test_internal_route_compares_exact_error_text(monkeypatch, tmp_path):
    import tools.probe as probe
    import tools.snapshot_diff as diff
    record = next(r for r in RECORDS if not r["expect"]["ok"])
    (tmp_path / "001.json").write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(probe, "resource_corpus_answer", lambda _: dict(record["expect"], message="wrong"))
    total, passed, failed = diff.run_corpus({}, tmp_path, {"resource_ops"})
    assert total == 1 and passed == 0 and len(failed) == 1
    assert "message" in failed[0]


def test_bootstrap_port_order_and_no_public_tools(tmp_path):
    from python.modules.editing.resource_ops.module import MODULE
    from python.modules.editing.resource_ops.ports import ResourceRead
    from python.runtime.bootstrap import default_ports, build_agent
    ports = default_ports(str(tmp_path), "test", str(tmp_path / "state"))
    assert list(ports) == ["gd_lint", "node_diff", "fs", "paths_fs", "api_cache", "librarian", "chat_gateway", "native_planner", "journal",
                           "writer", "backups", "lock", "editor", "resource_read", "project_text_fs"]
    assert isinstance(ports["resource_read"], ResourceRead)
    assert MODULE.provides_tools == ()
    agent = build_agent(str(tmp_path), "test", ports=ports)
    assert "editing.resource_ops" not in agent.disabled()
    for name in ("resource_ops", "edit_resource"):
        assert agent.call(name, {})["kind"] == "unknown_tool"
