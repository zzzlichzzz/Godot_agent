"""gen_contract: гейт на неизвестные типы в схемах контракта.

Опечатка в `type` (`"date"`) раньше проходила молча: валидатор считал неизвестный
тип пропуском. Теперь такой контракт не собирается — иначе отказ всплыл бы на
первом ответе моста, а не здесь.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERBS = ("editor_ping", "editor_state", "editor_selection")


def _load(name):
    path = ROOT / "tools" / (name + ".py")
    spec = importlib.util.spec_from_file_location("tool_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen_contract = _load("gen_contract")


def verb(name):
    return {
        "name": name,
        "effects": "read",
        "thread": "main",
        "result": ["path"],
        "result_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    }


def root(tmp_path):
    (tmp_path / "contract").mkdir()
    data = {
        "schema_version": 1,
        "verbs_version": 3,
        "_change_policy": "добавил примитив — поднял версию",
        "_handlers": "pending-editor-bridge",
        "verbs": [verb(name) for name in VERBS],
    }
    (tmp_path / "contract" / "editor_verbs.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (tmp_path / "editor").mkdir()
    return tmp_path, data


def test_unknown_type_in_verb_schema_fails_with_its_name(tmp_path):
    folder, data = root(tmp_path)
    data["verbs"][0]["result_schema"]["properties"]["path"]["type"] = "date"
    (folder / "contract" / "editor_verbs.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    problems, _note = gen_contract.check_editor_verbs(folder)
    assert any("неизвестный тип 'date'" in item and "editor_ping" in item
               for item in problems), problems


def test_capability_artifact_with_unknown_type_fails(tmp_path):
    (tmp_path / "write_preview.json").write_text(json.dumps({
        "input_schema": {"type": "object",
                         "properties": {"path": {"type": "date"}}},
        "result_schema": {"type": "object",
                          "properties": {"ok": {"type": "boolean"}}},
    }, ensure_ascii=False), encoding="utf-8")
    problems = gen_contract.artifact_type_problems(tmp_path)
    assert len(problems) == 1
    assert "write_preview.json" in problems[0]
    assert "input_schema.path" in problems[0]


def test_capability_artifact_with_non_string_type_fails(tmp_path):
    """Не-строковый `type` (`5`) в артефакте — провал гейта, а не тихий пропуск."""
    (tmp_path / "write_preview.json").write_text(json.dumps({
        "input_schema": {"type": "object",
                         "properties": {"path": {"type": 5}}},
    }, ensure_ascii=False), encoding="utf-8")
    problems = gen_contract.artifact_type_problems(tmp_path)
    assert len(problems) == 1
    assert "write_preview.json" in problems[0]
    assert "input_schema.path" in problems[0]


def test_template_is_skipped_by_the_gate(tmp_path):
    (tmp_path / "_template.json").write_text(
        json.dumps({"input_schema": {"type": "date"}}), encoding="utf-8")
    assert gen_contract.artifact_type_problems(tmp_path) == []


def test_repository_artifacts_have_known_types():
    assert gen_contract.artifact_type_problems() == []
