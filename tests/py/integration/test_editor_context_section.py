"""Секция `editor` в пакете контекста: вклад, профиль, отказы моста.

Проверки §5 п.8: в профиле `editor` с фейком секция собирается, без моста -
`no_bridge`, в `headless` вклада нет вовсе (`unavailable` с `no_module`).
Правила: R-22, R-11 (домен без IO), R-09.
"""

from python.runtime.bootstrap import build_agent
from python.substrate.editor.client import PORT_FILE_ENV
from tests.py.integration.fake_editor import FakeEditor
from tests.py.integration.test_editor_context_bridge import fast_timeouts  # noqa: F401


def _project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    return root


def _agent(root, tmp_path, profile):
    return build_agent(project_root=str(root), profile=profile,
                       state_dir=str(tmp_path / "state"))


def test_editor_profile_collects_section_from_bridge(tmp_path, monkeypatch):
    """Живой мост (фейк): секция `editor` есть, снимок на месте."""
    root = _project(tmp_path)
    fake = FakeEditor()
    fake.__enter__()
    try:
        monkeypatch.setenv(PORT_FILE_ENV, str(fake.write_port_file(tmp_path / "port.json")))
        agent = _agent(root, tmp_path, "editor")
        out = agent.call("context", {"sections": ["editor"]})
    finally:
        fake.close()
    assert out["ok"] is True
    section = out["result"]["sections"]["editor"]
    assert section["available"] is True
    assert section["open_scenes"][0]["path"] == "res://main.tscn"
    assert section["selection"]["node_path"] == "/root/Main/Player"
    assert out["result"]["available"] == ["editor"]
    assert out["result"]["unavailable"] == []


def test_editor_without_bridge_reports_no_bridge(tmp_path, monkeypatch):
    """Мост не запущен: секция собирается, но `available: false` с причиной."""
    root = _project(tmp_path)
    monkeypatch.setenv(PORT_FILE_ENV, str(tmp_path / "нет.json"))
    agent = _agent(root, tmp_path, "editor")
    out = agent.call("context", {"sections": ["editor"]})
    assert out["ok"] is True
    assert out["result"]["sections"] == {}
    assert out["result"]["available"] == []
    assert out["result"]["unavailable"] == [{"name": "editor", "reason": "no_bridge"}]


def test_headless_has_no_editor_contribution(tmp_path):
    """В `headless` вклад не регистрируется: причина `no_module`, контекст цел."""
    root = _project(tmp_path)
    agent = _agent(root, tmp_path, "headless")
    out = agent.call("context", {"sections": ["editor"]})
    assert out["ok"] is True
    assert out["result"]["unavailable"] == [{"name": "editor", "reason": "no_module"}]
    assert "context.editor_context" in agent.disabled()
