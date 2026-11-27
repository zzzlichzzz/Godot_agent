"""modules/code_intel/usages/tests/test_core.py - домен поиска использований (R-11).

Домен получает индекс (файл → разбор) и запрос, возвращает места. Диска здесь
нет: индекс собирается в памяти из текстов — тех же, что в корпусе
`fixtures/corpus/code_intel/usages/`.
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
          "\treturn hp\n"
          "\n"
          "func reset() -> void:\n"
          "\thp = MAX_HP\n")

TURRET = ("extends LabEntity\n"
          "\n"
          "func fire() -> void:\n"
          "\ttake_damage(1)\n")

DYNAMIC = ("extends Node\n"
           "\n"
           "func hit(target) -> void:\n"
           "\ttarget.hit(1)\n")

STRINGS = ("extends Node\n"
           "\n"
           "func trigger(node: Node) -> void:\n"
           "\tnode.call(\"on_hit\", 1)\n"
           "\n"
           "func on_hit() -> void:\n"
           "\tpass\n")


class _Files:
    """Поддельный порт `fs`: словарь «путь → текст».

    Своя реализация, а не `substrate.fs.memory_fs`: модуль не тянет substrate
    даже в тестах (R-11, проверяется `lint_arch`).
    """

    def __init__(self, files):
        self._files = dict(files)

    def list_files(self):
        return sorted(self._files)

    def read_text(self, rel_path):
        return self._files[rel_path]



def _index(files):
    """Индекс из словаря «путь → текст» через поддельный порт (без substrate)."""
    return symbol_index.build(_Files(files), PathPolicy(""))


def _find(files, kind, old_name, declaration, new_name=""):
    index = _index(files)
    return core.find(index, core.build_query(kind, old_name, new_name, declaration))


def test_locator_takes_line_and_optional_column():
    query = core.build_query("function", "take_damage", "",
                             "res://src/lab_entity.gd:8")
    assert (query.path, query.line, query.column) == ("res://src/lab_entity.gd", 8, None)
    query = core.build_query("function", "take_damage", "",
                             "res://src/lab_entity.gd:8:6")
    assert query.column == 6


@pytest.mark.parametrize('report', [core.find, core.analyze])
def test_super_calls_belong_to_nearest_declaring_parent(report):
    files = {'coin.gd': 'class_name Coin\nextends Area2D\nfunc _ready(): pass',
             'entity.gd': 'class_name LabEntity\nextends Node2D\nfunc _ready(): pass',
             'mid.gd': 'extends LabEntity',
             'turret.gd': 'class_name Turret\nextends "mid.gd"\nfunc _ready():\n\tsuper._ready()',
             'child.gd': 'extends Turret\nfunc run():\n\tsuper._ready()',
             'unknown.gd': 'extends Missing\nfunc run():\n\tsuper._ready()'}
    index = _index(files)
    def places(path):
        q = core.build_query('function', '_ready', '_start', 'res://'+path+'.gd:3')
        return [(i['path'], i['confidence']) for i in report(index, q)['usages'] if i['link'] != 'declaration']
    assert places('coin') == [('res://unknown.gd', 'probable')]
    assert places('entity') == [('res://turret.gd', 'proven'), ('res://unknown.gd', 'probable')]


@pytest.mark.parametrize("declaration", [
    "res://src/lab_entity.gd:abc",
    "src/lab_entity.gd:8",
    "res://src/lab_entity.gd",
    "res://src/lab_entity.gd:0",
])
def test_bad_locator_is_invalid_input(declaration):
    with pytest.raises(AppError) as caught:
        core.build_query("function", "take_damage", "", declaration)
    assert caught.value.kind == "invalid_input"


def test_kind_and_name_are_validated():
    with pytest.raises(AppError) as caught:
        core.build_query("method", "take_damage", "", "res://src/lab_entity.gd:8")
    assert caught.value.kind == "invalid_input"
    with pytest.raises(AppError) as caught:
        core.build_query("function", "func", "", "res://src/lab_entity.gd:8")
    assert caught.value.kind == "invalid_input"


def test_missing_declaration_is_not_found_with_names():
    index = _index({"src/lab_entity.gd": ENTITY})
    with pytest.raises(AppError) as caught:
        core.find(index, core.build_query("function", "take_damage", "",
                                          "res://src/lab_entity.gd:3"))
    error = caught.value
    assert error.kind == "not_found"
    assert "take_damage" in error.message


def test_declaration_and_calls_are_proven():
    result = _find({"src/lab_entity.gd": ENTITY, "src/lab_turret.gd": TURRET},
                   "function", "take_damage", "res://src/lab_entity.gd:8")
    assert [(item["link"], item["confidence"]) for item in result["usages"]] == [
        ("declaration", "proven"), ("call", "proven")]
    assert result["by_link"] == {"declaration": 1, "call": 1}
    assert result["proven_count"] == 2 and result["probable_count"] == 0


def test_local_shadow_is_excluded():
    text = ("extends Node\n\nvar counter: int = 0\n\n"
            "func bump() -> void:\n\tcounter += 1\n\n"
            "func shadowed() -> void:\n\tvar counter := 5\n\tcounter += 1\n")
    result = _find({"src/a.gd": text}, "variable", "counter", "res://src/a.gd:3")
    assert [(item["line"], item["confidence"]) for item in result["usages"]] == [
        (3, "proven"), (6, "proven")]


def test_unknown_receiver_is_probable_with_reason():
    result = _find({"src/lab_dynamic.gd": DYNAMIC}, "function", "hit",
                   "res://src/lab_dynamic.gd:3")
    place = result["usages"][-1]
    assert place["confidence"] == "probable"
    assert place["note"] and "аннотацию типа" in place["note"]
    assert result["probable_count"] == 1


def test_string_literal_next_to_call_is_dynamic():
    result = _find({"src/lab_strings.gd": STRINGS}, "function", "on_hit",
                   "res://src/lab_strings.gd:6")
    place = result["usages"][0]
    assert (place["link"], place["confidence"]) == ("string", "dynamic")
    assert place["note"] == "call() по имени"


def test_counters_match_usages():
    result = _find({"src/lab_entity.gd": ENTITY, "src/lab_turret.gd": TURRET},
                   "function", "take_damage", "res://src/lab_entity.gd:8")
    assert result["proven_count"] + result["probable_count"] + result["dynamic_count"] == len(result["usages"])
    assert sum(result["by_link"].values()) == len(result["usages"])


def test_const_is_public_name_for_parser_constant():
    result = _find({"src/lab_entity.gd": ENTITY}, "const", "MAX_HP",
                   "res://src/lab_entity.gd:4")
    assert [item["confidence"] for item in result["usages"]] == ["proven", "proven"]


def test_new_name_is_echoed():
    result = _find({"src/lab_entity.gd": ENTITY}, "function", "take_damage",
                   "res://src/lab_entity.gd:8", "apply_damage")
    assert result["new_name"] == "apply_damage"
    assert result["declaration"] == "res://src/lab_entity.gd:8"
