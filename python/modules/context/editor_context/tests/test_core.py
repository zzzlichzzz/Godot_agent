"""Тесты домена `context.editor_context`: ответы моста и их валидация.

Кейсы - из ответов фейка (`tests/py/integration/fake_editor.py`), а не копии
кода: домен проверяет схему и собирает фрагмент (R-07, R-09 без skip/xfail).
Корпуса у вклада нет намеренно: `uptime_s` и абсолютные пути недетерминированы.
"""

import json
from pathlib import Path

import pytest

from python.kernel.errors import AppError
from python.modules.context.editor_context.domain import core

#: Контракт читается, а не копируется: фикстура не должна доказывать ответ
#: несуществующей версии словаря (B.1, R-07).
ROOT = Path(__file__).resolve().parents[5]
CONTRACT = json.loads((ROOT / "contract" / "editor_verbs.json").read_text(
    encoding="utf-8"))

PING = {"godot": "4.6", "verbs_version": CONTRACT["verbs_version"], "protocol": 1,
        "open_scenes": 1, "uptime_s": 12.5}
SCENE = {"path": "res://main.tscn", "revision": 3, "dirty": False,
         "active": True, "unsaved_changes": 0}
STATE = {"open_scenes": [SCENE], "active_scene": "res://main.tscn",
         "project_hash": "abc123"}
SELECTION = {"node_path": "/root/Main/Player", "scene": "res://main.tscn",
             "properties": [{"name": "position", "type": "Vector2",
                             "value": [1, 2]}],
             "script": "res://player.gd"}

#: Копия `result_schema` из `contract/editor_verbs.json`. Модуль не импортирует
#: `substrate` (R-11), поэтому сверку с самим контрактом держат интеграционные
#: тесты (`tests/py/integration/test_editor_context_bridge.py`).
SCHEMAS = {
    "editor_ping": {
        "type": "object",
        "properties": {"godot": {"type": "string"},
                       "verbs_version": {"type": "integer", "minimum": 1},
                       "protocol": {"type": "integer", "minimum": 1},
                       "open_scenes": {"type": "integer", "minimum": 0},
                       "uptime_s": {"type": "number", "minimum": 0}},
        "required": ["godot", "verbs_version", "protocol", "open_scenes", "uptime_s"],
        "additionalProperties": False,
    },
    "editor_state": {
        "type": "object",
        "properties": {
            "open_scenes": {"type": "array", "items": {
                "type": "object",
                "properties": {"path": {"type": "string"},
                               "revision": {"type": "integer", "minimum": 0},
                               "dirty": {"type": "boolean"},
                               "active": {"type": "boolean"},
                               "unsaved_changes": {"type": "integer", "minimum": 0}},
                "required": ["path", "revision", "dirty", "active", "unsaved_changes"],
                "additionalProperties": False}},
            "active_scene": {"type": ["string", "null"]},
            "project_hash": {"type": "string"},
        },
        "required": ["open_scenes", "active_scene", "project_hash"],
        "additionalProperties": False,
    },
    "editor_selection": {
        "type": "object",
        "properties": {
            "node_path": {"type": ["string", "null"]},
            "scene": {"type": ["string", "null"]},
            "properties": {"type": "array", "items": {
                "type": "object",
                "properties": {"name": {"type": "string"},
                               "type": {"type": "string"},
                               "value": {}},
                "required": ["name", "type", "value"],
                "additionalProperties": False}},
            "script": {"type": ["string", "null"]},
        },
        "required": ["node_path", "scene", "properties", "script"],
        "additionalProperties": False,
    },
}


class FakeClient:
    """Порт `editor` в минимуме: примитив → ответ, схема - из словаря."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def call(self, verb, args=None):
        self.calls.append(verb)
        answer = self.answers[verb]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def result_schema(self, verb):
        return SCHEMAS[verb]


def _answers(**overrides):
    answers = {"editor_ping": dict(PING), "editor_state": dict(STATE),
               "editor_selection": dict(SELECTION)}
    answers.update(overrides)
    return answers


def test_collect_reads_three_primitive():
    """Снимок = три примитива, каждый сверен со своей схемой."""
    client = FakeClient(_answers())
    fragment = core.collect(client)
    assert client.calls == ["editor_ping", "editor_state", "editor_selection"]
    assert fragment["available"] is True
    assert fragment["open_scenes"] == [SCENE]
    assert fragment["selection"]["node_path"] == "/root/Main/Player"


def test_nullable_selection_is_valid():
    """`None` в nullable-полях - норма: снимок собирается, а не падает."""
    selection = {"node_path": None, "scene": None, "script": None,
                 "properties": []}
    fragment = core.collect(FakeClient(_answers(editor_selection=selection)))
    assert fragment["selection"] == {"node_path": None, "scene": None,
                                     "script": None, "properties": []}


def test_bad_revision_type_is_refused_with_field_path():
    """`revision: "3"` внутри `open_scenes[0]` - отказ с путём поля."""
    state = dict(STATE, open_scenes=[dict(SCENE, revision="3")])
    with pytest.raises(AppError) as excinfo:
        core.collect(FakeClient(_answers(editor_state=state)))
    assert excinfo.value.kind == "engine_down"
    assert excinfo.value.details["reason"] == "bad_result"
    assert any("open_scenes[0].revision" in item
               for item in excinfo.value.details["problems"])


def test_missing_field_is_refused():
    """Нет `project_hash` - ответ не годен: частичного снимка не бывает."""
    state = {"open_scenes": [], "active_scene": None}
    with pytest.raises(AppError) as excinfo:
        core.collect(FakeClient(_answers(editor_state=state)))
    assert any("project_hash" in item
               for item in excinfo.value.details["problems"])


def test_ping_without_uptime_is_refused():
    """`uptime_s` обязателен: мост не отвечал - это не «пустой снимок»."""
    ping = {name: value for name, value in PING.items() if name != "uptime_s"}
    with pytest.raises(AppError) as excinfo:
        core.collect(FakeClient(_answers(editor_ping=ping)))
    assert any("uptime_s" in item
               for item in excinfo.value.details["problems"])


def test_non_object_answer_is_refused():
    """Ответ не объект - отказ с причиной `bad_result`, а не TypeError."""
    with pytest.raises(AppError) as excinfo:
        core.collect(FakeClient(_answers(editor_state=["не объект"])))
    assert excinfo.value.details["reason"] == "bad_result"


def test_non_string_node_path_is_refused():
    """`5` на месте `node_path` - не годный ответ: отказ с путём поля."""
    selection = {"node_path": 5, "scene": None, "script": None, "properties": []}
    with pytest.raises(AppError) as excinfo:
        core.collect(FakeClient(_answers(editor_selection=selection)))
    assert excinfo.value.details["reason"] == "bad_result"
    assert any("node_path" in item for item in excinfo.value.details["problems"])


def test_client_refusal_propagates():
    """`no_bridge` транспорта - отказ транспорта: причины домен не подменяет."""
    with pytest.raises(AppError) as excinfo:
        core.collect(FakeClient(_answers(editor_ping=AppError(
            "unavailable", "нет моста", details={"reason": "no_bridge"}))))
    assert excinfo.value.details["reason"] == "no_bridge"


def test_check_reports_empty_schema_problems():
    """Годный ответ - `[]`: `check` не бросает и ничего не возвращает."""
    assert core.check(core.STATE, STATE, SCHEMAS[core.STATE]) is None



def test_ping_version_matches_contract():
    """Фикстура ответа называет ту же версию словаря, что контракт."""
    assert PING["verbs_version"] == CONTRACT["verbs_version"]
