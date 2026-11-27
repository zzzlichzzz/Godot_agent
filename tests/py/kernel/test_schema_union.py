"""kernel/schema.py: union-типы и отказ на неизвестном типе (часть A, nullable).

`["string", "null"]` — самый частый ответ моста редактора: «выделения нет»,
«активной сцены нет», «скрипта нет». Раньше `_type_ok` падал на списке
(`_TYPES.get(list)` → `TypeError`), поэтому проверить ответ моста схемой было
нельзя. Тесты держат три свойства: union работает и вложенно, неизвестный тип —
отказ (fail closed), `validate` тотальна на мусорных схемах.
"""

import json
from pathlib import Path

from python.kernel.schema import unknown_schema_types, validate

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "contract" / "editor_verbs.json"


def verbs():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    return data["verbs"]


def result_schema(name):
    return next(item["result_schema"] for item in verbs() if item["name"] == name)


def nullable_field():
    return {"type": "object", "properties": {"node_path": {"type": ["string", "null"]}}}


def open_scene(**overrides):
    scene = {"path": "res://a.tscn", "revision": 3, "dirty": False,
             "active": True, "unsaved_changes": 0}
    scene.update(overrides)
    return {"open_scenes": [scene], "active_scene": None, "project_hash": "abc"}


def test_none_passes_nullable_union():
    assert validate({"node_path": None}, nullable_field()) == []


def test_string_passes_nullable_union():
    assert validate({"node_path": "res://a.tscn"}, nullable_field()) == []


def test_number_fails_nullable_union_with_field_path():
    problems = validate({"node_path": 5}, nullable_field())
    assert len(problems) == 1
    assert "node_path" in problems[0]


def test_open_scenes_from_contract_are_valid():
    assert validate(open_scene(), result_schema("editor_state")) == []


def test_open_scenes_revision_is_checked_inside_the_item():
    problems = validate(open_scene(revision="3"), result_schema("editor_state"))
    assert any("[0].revision" in item for item in problems), problems


def test_nullable_fields_of_selection_are_valid():
    selection = result_schema("editor_selection")
    payload = {"node_path": None, "scene": None, "properties": [], "script": None}
    assert validate(payload, selection) == []
    chosen = {"node_path": "Root/Player", "scene": "res://a.tscn",
              "properties": [{"name": "visible", "type": "bool", "value": True}],
              "script": "res://player.gd"}
    assert validate(chosen, selection) == []


def test_unknown_type_fails_closed():
    problems = validate("2026-10-27", {"type": "date"})
    assert len(problems) == 1
    assert "date" in problems[0]


def test_unknown_type_is_named_with_its_path():
    schema = {"type": "object", "properties": {"node_path": {"type": "date"}}}
    assert unknown_schema_types(schema) == [
        "(аргументы).node_path: неизвестный тип 'date'"]


def test_unknown_type_inside_union_and_items_is_named():
    schema = {"type": "array", "items": {"type": ["string", "date"]}}
    assert unknown_schema_types(schema) == [
        "(аргументы)[]: неизвестный тип 'date'"]


def test_garbage_schemas_do_not_raise():
    garbage = ({"type": 5}, {"items": "x"}, {"properties": []}, {"required": "path"},
               {"properties": {"a": "не схема"}}, {"type": ["string", None]},
               {"type": {"x": 1}}, {"type": [{"x": 1}]},
               {"properties": {"a": {"type": {"x": 1}}}},
               {"properties": 5}, {"required": 5})
    for schema in garbage:
        assert isinstance(validate({"a": 1}, schema), list)
        assert isinstance(validate([1, 2], schema), list)
        assert isinstance(unknown_schema_types(schema), list)


def test_non_string_type_is_refused_not_raised():
    """Не-строковый `type` — отказ, а не `TypeError` (тотальность `validate`).

    Держит строку `if not isinstance(expected, str): return False` в `_type_ok`:
    без неё `_TYPES.get({'x': 1})` бросает `cannot use 'dict' as a dict key`.
    """
    assert validate({"a": 1}, {"type": {"x": 1}}) == ["(аргументы): ожидался {'x': 1}"]
    assert unknown_schema_types({"type": {"x": 1}}) == [
        "(аргументы): неизвестный тип {'x': 1}"]


def test_type_null_means_type_is_not_set():
    """`type: None` — «тип не задан», а не отказ и не «неизвестный тип»."""
    assert validate("x", {"type": None}) == []
    assert unknown_schema_types({"type": None}) == []
    assert validate("x", {"type": "date"}) != []


def test_every_primitive_schema_has_known_types():
    for verb in verbs():
        assert unknown_schema_types(verb["result_schema"], verb["name"]) == []
