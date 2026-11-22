"""tools/gen_contract.py: словарь примитивов и сверка с обработчиками (R-14).

Каждый случай — свой временный корень: вердикт обязан зависеть от того, что лежит
в `editor/`, а не от флага в JSON. Пока маркеров `# verb:` нет, пропуск сверки
разрешён, но долг виден в `note`; появился первый маркер — сверка включается сама,
а `_handlers` становится мёртвым выключателем и обязан быть снят.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERBS = ("editor_ping", "editor_state", "editor_selection")
DEBT = "мост: 0 обработчиков из 3, ожидаются"


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
        "result": ["path", "revision"],
        "result_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "revision": {"type": "integer"},
            },
            "required": ["path", "revision"],
            "additionalProperties": False,
        },
    }


def dictionary(**overrides):
    data = {
        "schema_version": 1,
        "verbs_version": 3,
        "_change_policy": "добавил примитив — поднял версию",
        "_handlers": "pending-editor-bridge",
        "verbs": [verb(name) for name in VERBS],
    }
    data.update(overrides)
    return data


def root(tmp_path, markers=(), data=None):
    """Временный корень: `contract/editor_verbs.json` + `editor/` с маркерами."""
    payload = dictionary() if data is None else data
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "editor_verbs.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    editor = tmp_path / "editor"
    editor.mkdir()
    for name in markers:
        (editor / ("%s.gd" % name)).write_text(
            "extends Node\n\n\nfunc handle():\n    # verb: %s\n    pass\n" % name,
            encoding="utf-8")
    return tmp_path


def test_zero_markers_with_pending_flag_allows_skip(tmp_path):
    problems, note = gen_contract.check_editor_verbs(root(tmp_path))
    assert problems == []
    assert note == DEBT


def test_zero_markers_without_flag_reports_no_handler(tmp_path):
    data = dictionary()
    data.pop("_handlers")
    problems, note = gen_contract.check_editor_verbs(root(tmp_path, data=data))
    assert any("нет ни одного обработчика" in item for item in problems)
    assert note == ""


def test_subset_of_markers_reports_every_missing_verb(tmp_path):
    problems, note = gen_contract.check_editor_verbs(root(tmp_path, ["editor_ping"]))
    assert note == ""
    missing = [item for item in problems if item.startswith("нет обработчика:")]
    assert len(missing) == 1
    assert "editor_state" in missing[0] and "editor_selection" in missing[0]
    assert not any("вне словаря" in item for item in problems)


def test_unknown_handler_is_reported_as_extra(tmp_path):
    problems, note = gen_contract.check_editor_verbs(
        root(tmp_path, list(VERBS) + ["editor_undo"]))
    assert note == ""
    extra = [item for item in problems if item.startswith("обработчик вне словаря:")]
    assert len(extra) == 1 and "editor_undo" in extra[0]
    assert not any("нет обработчика" in item for item in problems)


def test_markers_with_pending_flag_demand_removing_the_flag(tmp_path):
    problems, _note = gen_contract.check_editor_verbs(root(tmp_path, list(VERBS)))
    assert any("снимите _handlers" in item for item in problems)
    assert not any("нет обработчика" in item for item in problems)


def test_verb_without_result_schema_fails_with_its_name(tmp_path):
    data = dictionary()
    data["verbs"][1].pop("result_schema")
    problems, _note = gen_contract.check_editor_verbs(root(tmp_path, data=data))
    assert any("editor_state" in item and "result_schema" in item for item in problems)


def test_renaming_a_schema_field_breaks_the_old_result_list(tmp_path):
    data = dictionary()
    properties = data["verbs"][0]["result_schema"]["properties"]
    properties["revised"] = properties.pop("revision")
    problems, _note = gen_contract.check_editor_verbs(root(tmp_path, data=data))
    assert any("поля result_schema" in item for item in problems)


def test_missing_verbs_version_fails(tmp_path):
    problems, _note = gen_contract.check_editor_verbs(
        root(tmp_path, data=dictionary(verbs_version=0)))
    assert any("verbs_version" in item for item in problems)


def test_repository_contract_has_no_problems():
    problems, _note = gen_contract.check_editor_verbs(ROOT)
    assert problems == []


def test_repository_debt_is_visible_until_the_first_handler():
    """Долг моста не прячется: пока обработчиков нет, он печатается в `detail`."""
    problems, note = gen_contract.check_editor_verbs(ROOT)
    assert problems == []
    handlers = gen_contract.editor_handlers(ROOT)
    assert note == ("" if handlers else DEBT)
