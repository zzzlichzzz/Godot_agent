"""D19 explicit effect entrypoint, strict public apply schema, real WAL proof."""
import ast
from pathlib import Path

import pytest

from tests.py.contract.test_resource_apply_cases import ANIMATION, CASES, TEXTURE, action


@pytest.mark.parametrize("bad", [None, [], {}, {"plan_id": "p"}, {"plan_id": "p", "digest": 1},
                                {"plan_id": "p", "digest": "d", "bytes_b64": "YQ=="},
                                {"plan_id": "p", "digest": "d", "target": "res://data.tres"}])
def test_apply_client_strict_schema_before_effect(tmp_path, bad):
    from tools.probe import resource_client
    answer = resource_client(tmp_path, bad, "apply")
    assert answer["ok"] is False and answer["kind"] == "invalid_input"
    assert list(tmp_path.iterdir()) == []


def test_client_application_uses_real_funnel_only(tmp_path, monkeypatch):
    from python.modules.editing.shared import funnel
    from tools.probe import file_refactor_context, resource_client
    project, state = tmp_path / "project", str(tmp_path / "state")
    project.mkdir()
    (project / "data.tres").write_bytes(ANIMATION)
    for name in ("old.tres", "new.tres"):
        (project / name).write_bytes(TEXTURE)
    seen, original = [], funnel.execute

    def witnessed(ctx, plan, report):
        seen.append(plan["steps"])
        return original(ctx, plan, report)

    monkeypatch.setattr(funnel, "execute", witnessed)
    preview = resource_client(project, action(CASES[0][2]), "prepare_write", state_dir=state)
    assert preview["ok"] and (project / "data.tres").read_bytes() == ANIMATION
    request = {name: preview["result"][name] for name in ("plan_id", "digest")}
    applied = resource_client(project, request, "apply", state_dir=state)
    assert applied["ok"] and len(seen) == 1 and seen[0][0]["op"] == "replace_raw"
    agent, _, ports = file_refactor_context(project, state)
    phases = [r.get("state") for r in ports["journal"].read(request["plan_id"])]
    assert phases == ["PREPARED", "APPLYING", "EFFECT_INTENT", "RECEIPT", "COMMITTED"]
    assert (project / "data.tres").read_bytes() == ANIMATION.replace(b"1.0", b"2.0")
    assert agent.call("write_rollback", {"entry_id": applied["result"]["entry_id"]})["ok"]
    assert (project / "data.tres").read_bytes() == ANIMATION
    folder = Path(__file__).resolve().parents[3] / "python/modules/editing/resource_ops"
    for source in folder.rglob("*.py"):
        if "tests" not in source.parts:
            calls = [n.func for n in ast.walk(ast.parse(source.read_text(encoding="utf-8"))) if isinstance(n, ast.Call)]
            assert not any(isinstance(n, ast.Name) and n.id == "open" or
                           isinstance(n, ast.Attribute) and (n.attr in ("write_raw", "write_bytes") or
                               n.attr == "replace" and isinstance(n.value, ast.Name) and n.value.id == "os") for n in calls)
