"""tests/py/security/test_path_escape.py - SEC-12: выход за корень проекта.

`write_preview` обязан отказать до чтения: `..` в locator, абсолютный путь и
выход через `res://` — это `denied`/`invalid_input`, а не «попробуем открыть».
Симлинк на Windows без прав не создать, поэтому третий вектор — тот же побег
через `..` на уровень выше (поведение политики одинаковое).
"""

import pytest

from python.runtime.bootstrap import build_agent

FIXTURE = "fixtures/projects/rename"
BASE = {"kind": "function", "old_name": "take_damage",
        "new_name": "apply_damage", "declaration": "res://src/hero.gd:6"}


def _call(declaration):
    args = dict(BASE, declaration=declaration)
    return build_agent(project_root=FIXTURE, profile="test").call("write_preview", args)


@pytest.mark.parametrize("declaration", [
    "res://../outside.gd:1",
    "res://src/../../outside.gd:6",
])
def test_relative_escape_is_denied(declaration):
    answer = _call(declaration)
    assert answer["ok"] is False
    assert answer["kind"] == "denied", answer


@pytest.mark.parametrize("declaration", [
    r"D:\vajno\Godot\agent-rebuild\outside.gd:1",
    "/etc/passwd:1",
    r"\\server\share\outside.gd:1",
])
def test_absolute_path_is_denied(declaration):
    answer = _call(declaration)
    assert answer["ok"] is False
    assert answer["kind"] == "denied", answer


def test_exclude_cannot_point_outside_too():
    args = dict(BASE, mode="probable", allow_unverified=True,
                exclude=["res://../outside.gd:1"])
    answer = build_agent(project_root=FIXTURE, profile="test").call(
        "write_preview", args)
    assert answer["ok"] is False and answer["kind"] == "invalid_input", answer
