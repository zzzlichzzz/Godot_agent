"""modules/code_intel/usages/tests/test_rename.py - предпросмотр переименования.

`analyze` — обёртка, а не второй поиск (R-04): он обязан звать `core.find` и
только группировать его ответ. Это проверяется подменой `find` (см.
`test_analyze_calls_the_existing_search`), а не глазами ревьюера.
"""

import pytest

from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.modules.code_intel.shared import symbol_index
from python.modules.code_intel.usages.domain import core

ENTITY = ("class_name LabEntity\n"
          "extends Node\n"
          "\n"
          "const MAX_HP := 100\n"
          "\n"
          "var hp: int = 0\n"
          "\n"
          "func take_damage(amount: int) -> int:\n"
          "\thp -= amount\n"
          "\treturn hp\n")

ROOT = ("extends Node\n"
        "\n"
        "func run(entity: LabEntity) -> void:\n"
        "\tentity.take_damage(9)\n"
        "\tentity.call(\"take_damage\", 1)\n")

TURRET = ("extends LabEntity\n"
          "\n"
          "func fire() -> void:\n"
          "\ttake_damage(1)\n")


class _Files:
    """Поддельный порт `fs`: словарь «путь → текст» (substrate не тянем, R-11)."""

    def __init__(self, files):
        self._files = dict(files)

    def list_files(self):
        return sorted(self._files)

    def read_text(self, rel_path):
        return self._files[rel_path]


def _index(files):
    return symbol_index.build(_Files(files), PathPolicy(""))


def _analyze(files, kind, old_name, new_name, declaration, mode=None,
             allow_unverified=None):
    index = _index(files)
    query = core.build_rename_query(kind, old_name, new_name, declaration, mode,
                                    allow_unverified)
    return core.analyze(index, query)


@pytest.mark.parametrize("new_name", [None, "", "   "])
def test_new_name_is_required(new_name):
    with pytest.raises(AppError) as caught:
        core.build_rename_query("function", "take_damage", new_name,
                                "res://src/lab_entity.gd:8")
    assert caught.value.kind == "invalid_input"


def test_mode_is_validated_instead_of_echoed():
    """Опечатка в mode не должна молча ослабить проверки (отличие, deviations)."""
    with pytest.raises(AppError) as caught:
        core.build_rename_query("function", "take_damage", "apply_damage",
                                "res://src/lab_entity.gd:8", "fast")
    assert caught.value.kind == "invalid_input"


def test_allow_unverified_must_be_boolean():
    with pytest.raises(AppError) as caught:
        core.build_rename_query("function", "take_damage", "apply_damage",
                                "res://src/lab_entity.gd:8", "strict", "yes")
    assert caught.value.kind == "invalid_input"


def test_defaults_are_strict_and_false():
    query = core.build_rename_query("function", "take_damage", "apply_damage",
                                    "res://src/lab_entity.gd:8")
    assert (query.mode, query.allow_unverified) == ("strict", False)


def test_declaration_path_and_line_are_parsed_once():
    result = _analyze({"src/lab_entity.gd": ENTITY}, "function", "take_damage",
                      "apply_damage", "res://src/lab_entity.gd:8")
    assert (result["declaration_path"], result["declaration_line"]) == (
        "res://src/lab_entity.gd", 8)
    assert result["declaration"] == "res://src/lab_entity.gd:8"
    assert result["new_name"] == "apply_damage"


def test_affected_paths_are_sorted_and_unique():
    text = ("extends Node\n"
            "\n"
            "var counter: int = 0\n"
            "\n"
            "func bump() -> void:\n"
            "\tcounter += 1\n"
            "\tcounter += 1\n")
    result = _analyze({"src/b.gd": text}, "variable", "counter", "tally",
                      "res://src/b.gd:3")
    assert result["risks"] == []
    assert result["affected_paths"] == ["res://src/b.gd"]
    assert result["proven_count"] == 3


def test_affected_paths_span_files_sorted():
    """В affected_paths попадают только файлы с доказанными ссылками."""
    result = _analyze({"src/lab_turret.gd": TURRET, "src/lab_entity.gd": ENTITY},
                      "function", "take_damage", "apply_damage",
                      "res://src/lab_entity.gd:8")
    assert result["affected_paths"] == ["res://src/lab_entity.gd",
                                        "res://src/lab_turret.gd"]
    assert result["affected_paths"] == sorted(result["affected_paths"])


def test_risks_are_strings_in_reference_format():
    result = _analyze({"src/lab_entity.gd": ENTITY, "src/lab_root.gd": ROOT},
                      "function", "take_damage", "apply_damage",
                      "res://src/lab_entity.gd:8")
    assert all(isinstance(line, str) for line in result["risks"])
    assert "res://src/lab_root.gd:4 [member, probable] — не удалось доказать тип " \
           "ресивера «entity»: добавь аннотацию типа, и ссылка переименуется сама" \
           in result["risks"]
    assert "res://src/lab_root.gd:5 [string, dynamic] — call() по имени" in result["risks"]
    assert result["proven_count"] + result["probable_count"] + \
        result["dynamic_count"] == len(result["usages"])


def test_analyze_calls_the_existing_search(monkeypatch):
    """R-04: второго обхода нет — обёртка зовёт `find` и только группирует."""
    index = _index({"src/lab_entity.gd": ENTITY})
    query = core.build_rename_query("const", "MAX_HP", "MAX_VALUE",
                                    "res://src/lab_entity.gd:4")
    calls = []
    real_find = core.find

    def spy(target_index, target_query):
        calls.append((target_index, target_query))
        return real_find(target_index, target_query)

    monkeypatch.setattr(core, "find", spy)
    result = core.analyze(index, query)
    assert calls == [(index, query)]
    assert result["risks"] == []
    assert result["affected_paths"] == ["res://src/lab_entity.gd"]
