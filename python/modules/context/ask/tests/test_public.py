"""Mandatory real Agent.call lane, separate from the213 reference operations."""
import json
from pathlib import Path
import shutil
import sys

import pytest

from tests.py.context.observations import CORPUS, ROOT, references, setup, state
from tests.py.context.ask_composition import headless_agent, headless_ports, isolated_activation

CATALOG = json.loads((CORPUS / "catalog.json").read_bytes())
ANSWERS = [row for row in CATALOG if row["operation"] == "answer"
           and isinstance(row.get("query"), str) and row["query"].strip()
           and isinstance(row.get("budget", 6000), int)]
APIS = [row for row in CATALOG if row["operation"] == "api"]


@pytest.fixture(autouse=True)
def isolated_native_setup():
    with isolated_activation():
        yield


def test_real_public_call_activates_ask_without_the_new_adapter_fixture(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "project.godot").write_bytes(b'[application]\nconfig/name="Ask activation fixture"\n')
    (project / "public.gd").write_bytes(b"extends Node\nfunc public_symbol():\n\treturn 17\n")
    before = state(project, tmp_path)
    agent = headless_agent(project, tmp_path / "state")
    answer = agent.call("ask", {"query": "public_symbol"})
    assert answer["ok"] is True, answer
    assert isinstance(answer["result"], str) and "public_symbol" in answer["result"]
    assert state(project, tmp_path) == before


@pytest.fixture
def public(tmp_path):
    sandbox = tmp_path / "ask"
    project = setup(sandbox)
    with references(sandbox) as subjects:
        profile, addon = sandbox / "profile", sandbox / "cache-addon"
        ports = headless_ports(project, profile, addon)
        agent = headless_agent(project, profile, ports)
        yield agent, subjects, sandbox, project, profile, ports["librarian"]


@pytest.mark.parametrize("case", ANSWERS, ids=lambda case: "public-" + case["id"])
def test_public_answer_text_matches_the_unchanged_native_answer(public, case):
    agent, _subjects, sandbox, project, _profile, _adapter = public
    before = state(project, sandbox)
    answer = agent.call("ask", {"query": case["query"], "budget_chars": case.get("budget", 6000)})
    expected = json.loads((CORPUS / "observations" / (case["id"] + ".json")).read_bytes())["result"]
    assert answer == {"ok": True, "result": expected}
    assert state(project, sandbox) == before


@pytest.mark.parametrize("case", APIS, ids=lambda case: "public-" + case["id"])
def test_public_api_answer_uses_explicit_fixture_cache_not_changed_bootstrap(public, case):
    agent, _subjects, _sandbox, _project, _profile, adapter = public
    folder = Path(adapter.addon_dir) / "agent_api_cache"
    folder.mkdir(parents=True)
    if case["mode"] == "deployed":
        shutil.copyfile(ROOT / "agent_api_cache/default_api_cache.json", folder / "default_api_cache.json")
    elif case["mode"] == "malformed":
        (folder / "default_api_cache.json").write_bytes(b"{invalid json")
    answer = agent.call("ask", {"query": case["query"]})
    expected = json.loads((CORPUS / "observations" / (case["id"] + ".json")).read_bytes())["result"]["answer"]
    assert answer == {"ok": True, "result": expected}


@pytest.mark.parametrize("args", [{}, {"query": None}, {"query": 17}, {"query": ""},
    {"query": "  "}, {"query": "take_damage", "budget_chars": True},
    {"query": "take_damage", "budget_chars": "500"},
    {"query": "take_damage", "operation": "log"}])
def test_public_invalid_input_is_typed_and_does_not_log(public, args):
    agent, _subjects, _sandbox, _project, _profile, adapter = public
    answer = agent.call("ask", args)
    assert answer["ok"] is False and answer["kind"] == "invalid_input"
    assert not adapter.log_path.exists()


@pytest.mark.parametrize("query", ["res://../outside/private.gd", ".agent_history/private.gd",
    "addons/vendor/private.gd", "Addons/vendor/private.gd"])
def test_public_denied_has_no_native_read_or_log(public, query):
    agent, _subjects, sandbox, project, _profile, adapter = public
    before = state(project, sandbox)
    answer = agent.call("ask", {"query": query})
    assert answer["ok"] is False and answer["kind"] == "denied"
    assert str(sandbox) not in json.dumps(answer)
    assert not adapter.log_path.exists()
    assert state(project, sandbox) == before


def test_real_default_composition_registers_ask_and_returns_map_fragments(public):
    _agent, _subjects, sandbox, project, _profile, _adapter = public
    before = state(project, sandbox)
    agent = headless_agent(project, sandbox / "real-default-profile")
    assert "ask" in {tool["name"] for tool in agent.tools()}
    answer = agent.call("ask", {"query": "take_damage", "budget_chars": 6000})
    assert answer["ok"] and "MAP (most relevant files, best first):" in answer["result"]
    assert "FRAGMENTS (verbatim matches):" in answer["result"]
    assert state(project, sandbox) == before


def test_native_append_is_profile_local_crlf_and_payload_idempotent(public):
    agent, subjects, sandbox, project, profile, adapter = public
    before = state(project, sandbox)
    original_override = subjects["data"]._BASE_OVERRIDE
    original_history = subjects["history"]._STORAGE_OVERRIDE
    had_project_history = (project / ".agent_history").exists()
    one = agent.call("ask", {"query": "take_damage", "budget_chars": 6000})
    two = agent.call("ask", {"query": "take_damage", "budget_chars": 6000})
    assert one == two and one["ok"]
    raw = adapter.log_path.read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n") == 2
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    assert records[0] == records[1]
    assert records[0]["query"] == "take_damage" and records[0]["chars"] == len(one["result"])
    assert records[0]["root"] == str(project.resolve()) and records[0]["ts"] == "1970-01-01T00:16:40"
    assert adapter.log_path.is_relative_to(profile)
    assert state(project, sandbox) == before
    assert subjects["data"]._BASE_OVERRIDE == original_override
    assert subjects["history"]._STORAGE_OVERRIDE == original_history
    assert (adapter.storage_base / "agent_history" / "snapshots").is_dir()
    assert (project / ".agent_history").exists() is had_project_history


@pytest.mark.parametrize("size, rotates", [(262143, False), (262144, False), (262145, True)])
def test_native_strict_rotation_is_exercised_through_public_ask(public, size, rotates):
    agent, _subjects, sandbox, project, _profile, adapter = public
    adapter.log_path.parent.mkdir(parents=True)
    initial = b"x" * size
    adapter.log_path.write_bytes(initial)
    before = state(project, sandbox)
    answer = agent.call("ask", {"query": "take_damage", "budget_chars": 6000})
    assert answer["ok"]
    rotated = adapter.log_path.with_name(adapter.log_path.name + ".1")
    assert rotated.exists() is rotates
    if rotates:
        assert rotated.read_bytes() == initial
        appended = adapter.log_path.read_bytes()
    else:
        raw = adapter.log_path.read_bytes()
        assert raw[:size] == initial
        appended = raw[size:]
    assert appended.endswith(b"\r\n") and appended.count(b"\n") == 1
    assert json.loads(appended)["query"] == "take_damage"
    assert state(project, sandbox) == before


def test_profile_switch_does_not_leak_log_or_storage_override(public):
    agent, subjects, sandbox, project, _profile, adapter = public
    other = sandbox / "other-profile"
    ports = headless_ports(project, other, adapter.addon_dir)
    second = ports["librarian"]
    another = headless_agent(project, other, ports)
    original = subjects["data"]._BASE_OVERRIDE
    original_history = subjects["history"]._STORAGE_OVERRIDE
    assert agent.call("ask", {"query": "take_damage"})["ok"]
    first_bytes = adapter.log_path.read_bytes()
    assert another.call("ask", {"query": "health_changed"})["ok"]
    assert adapter.log_path.read_bytes() == first_bytes
    assert json.loads(second.log_path.read_bytes())["query"] == "health_changed"
    assert subjects["data"]._BASE_OVERRIDE == original
    assert subjects["history"]._STORAGE_OVERRIDE == original_history
    assert not hasattr(sys.modules["minilich"], "__path__")
    assert not any(name in sys.modules for name in ("function_card", "ml_train", "ml_model"))


def test_adapter_refuses_profile_storage_inside_project_before_any_write(public):
    _agent, _subjects, sandbox, project, _profile, adapter = public
    from python.kernel.errors import AppError
    cls = type(adapter)
    before = state(project, sandbox)
    unsafe = cls(project, project / "unsafe-state", adapter.addon_dir)
    with pytest.raises(AppError) as failure:
        unsafe.answer("take_damage", 6000)
    assert failure.value.kind == "denied"
    assert state(project, sandbox) == before


def test_legacy_history_junction_outside_profile_is_denied(public):
    import _winapi
    agent, subjects, sandbox, project, _profile, adapter = public
    outside = sandbox / "outside-history"
    outside.mkdir()
    (outside / "private-marker").write_bytes(b"outside history must not be read or written")
    adapter.storage_base.mkdir(parents=True)
    _winapi.CreateJunction(str(outside), str(adapter.storage_base / "agent_history"))
    before = state(project, sandbox)
    outside_before = state(outside, sandbox)
    history_override = subjects["history"]._STORAGE_OVERRIDE
    answer = agent.call("ask", {"query": "take_damage"})
    assert answer["ok"] is False and answer["kind"] == "denied"
    assert not adapter.log_path.exists()
    assert subjects["history"]._STORAGE_OVERRIDE == history_override
    assert state(outside, sandbox) == outside_before and state(project, sandbox) == before


def test_failed_history_storage_routing_is_denied_and_restores_overrides(public, monkeypatch):
    agent, subjects, sandbox, project, _profile, adapter = public
    before = state(project, sandbox)
    data_override = subjects["data"]._BASE_OVERRIDE
    history_override = subjects["history"]._STORAGE_OVERRIDE
    old_history = state(Path(history_override), sandbox)
    monkeypatch.setattr(subjects["history"], "set_storage_dir", lambda base: None)
    answer = agent.call("ask", {"query": "take_damage"})
    assert answer["ok"] is False and answer["kind"] == "denied"
    assert subjects["data"]._BASE_OVERRIDE == data_override
    assert subjects["history"]._STORAGE_OVERRIDE == history_override
    assert not adapter.log_path.exists()
    assert state(Path(history_override), sandbox) == old_history and state(project, sandbox) == before


def test_missing_project_is_typed_not_found_without_creating_storage(public):
    _agent, _subjects, sandbox, _project, _profile, adapter = public
    from python.kernel.errors import AppError
    profile = sandbox / "missing-project-profile"
    missing = type(adapter)(sandbox / "not-a-project", profile, adapter.addon_dir)
    with pytest.raises(AppError) as failure:
        missing.answer("take_damage", 6000)
    assert failure.value.kind == "not_found" and not profile.exists()


def test_physical_junction_outside_project_is_denied_through_public_ask(public):
    import _winapi
    agent, _subjects, sandbox, project, _profile, adapter = public
    outside = sandbox / "outside"
    outside.mkdir()
    (outside / "private.gd").write_bytes(b"func outside_secret_marker():\n\treturn 17\n")
    _winapi.CreateJunction(str(outside), str(project / "outside-link"))
    before = state(project, sandbox)
    answer = agent.call("ask", {"query": "res://outside-link/private.gd"})
    assert answer["ok"] is False and answer["kind"] == "denied"
    assert not adapter.log_path.exists()
    assert state(project, sandbox) == before


def test_profile_storage_creation_failure_cannot_fall_back_to_old_native_storage(public):
    agent, subjects, sandbox, project, _profile, adapter = public
    adapter.storage_base.parent.mkdir(parents=True)
    adapter.storage_base.write_bytes(b"occupied profile path")
    before = state(project, sandbox)
    old_override = subjects["data"]._BASE_OVERRIDE
    old_storage = state(Path(old_override), sandbox)
    answer = agent.call("ask", {"query": "take_damage"})
    assert answer["ok"] is False and answer["kind"] == "denied"
    assert subjects["data"]._BASE_OVERRIDE == old_override
    assert state(Path(old_override), sandbox) == old_storage
    assert state(project, sandbox) == before


def test_legacy_addon_cache_does_not_migrate_and_native_answer_is_unchanged(public):
    agent, subjects, sandbox, project, _profile, adapter = public
    case = next(row for row in APIS if row["mode"] == "deployed")
    addon = Path(adapter.addon_dir)
    addon.mkdir()
    legacy = addon / subjects["api"].DEFAULT_CACHE_FILENAME
    shutil.copyfile(ROOT / "agent_api_cache/default_api_cache.json", legacy)
    before = state(addon, sandbox)
    project_before = state(project, sandbox)
    original_migration = subjects["api"]._migrate_legacy_addon_cache
    expected = json.loads((CORPUS / "observations" / (case["id"] + ".json")).read_bytes())["result"]["answer"]
    answer = agent.call("ask", {"query": case["query"]})
    assert answer == {"ok": True, "result": expected}
    assert state(addon, sandbox) == before
    assert state(project, sandbox) == project_before
    assert legacy.is_file() and not (addon / "agent_api_cache").exists()
    assert subjects["api"]._migrate_legacy_addon_cache is original_migration
