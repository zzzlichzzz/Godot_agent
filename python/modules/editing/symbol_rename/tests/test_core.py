"""modules/editing/symbol_rename/tests/test_core.py - unit-тесты компилятора.

Компилятор только строит план: поиск ссылок делает `code_intel.usages`, запись —
воронка `editing.write_preview`. Проверяются отказы (`invalid_input` на запросе,
`conflict` + `details.reason` на существе), смещения правок, переводы строк и
равенство `CONTRIBUTIONS` домену. Правила: R-04, R-12, ADR-0005.
"""

import hashlib

import pytest

from python.kernel.errors import AppError
from python.modules.editing.symbol_rename import COMPILER
from python.modules.editing.symbol_rename.domain.compiler import (compile_plan,
                                                                  validate_request)

PLAYER = """extends Node


func old_name() -> void:
	pass
"""
CALLER = """extends Node


func _ready() -> void:
	old_name()
"""
CONFLICTING = """extends Node


func old_name() -> void:
	pass


func new_name() -> void:
	pass
"""
TEXTS = {"scripts/player.gd": PLAYER, "scripts/caller.gd": CALLER}


def _usage(path, line, column, link="reference", confidence="proven"):
    return {"path": path, "line": line, "column": column, "link": link,
            "confidence": confidence}


def _analysis(usages=None, **over):
    """Отчёт `analyze_rename` в минимальном виде, достаточном компилятору."""
    data = {"kind": "function", "old_name": "old_name", "new_name": "new_name",
            "declaration": "scripts/player.gd:4",
            "declaration_path": "scripts/player.gd", "declaration_line": 4,
            "mode": "strict", "allow_unverified": False, "risks": [],
            "usages": [_usage("scripts/player.gd", 4, 6, "declaration"),
                       _usage("scripts/caller.gd", 5, 2)]
            if usages is None else usages,
            "proven_count": 1, "probable_count": 0, "dynamic_count": 0}
    data.update(over)
    return data


def _refusal(call):
    with pytest.raises(AppError) as caught:
        call()
    return caught.value.kind, (caught.value.details or {}).get("reason")


def test_validate_request_accepts_valid_request():
    """Имя-идентификатор, известный вид и режим — запрос проходит."""
    assert validate_request("function", "old_name", "new_name", "strict",
                            False) is None


def test_validate_request_rejects_unknown_kind():
    assert _refusal(lambda: validate_request("macro", "a", "b", "strict",
                                             False)) == ("invalid_input", None)


def test_validate_request_rejects_bad_identifier():
    assert _refusal(lambda: validate_request("variable", "a", "1abc", "strict",
                                             False))[0] == "invalid_input"


def test_validate_request_rejects_keyword():
    assert _refusal(lambda: validate_request("function", "a", "func", "strict",
                                             False))[0] == "invalid_input"


def test_validate_request_rejects_same_name():
    """Переименование в себя — отказ с причиной, план на него не нужен."""
    assert _refusal(lambda: validate_request("function", "a", "a", "strict",
                                             False)) == ("invalid_input",
                                                         "same_name")


def test_validate_request_rejects_unknown_mode():
    assert _refusal(lambda: validate_request("function", "a", "b", "loose",
                                             False))[0] == "invalid_input"


def test_validate_request_rejects_non_bool_flag():
    assert _refusal(lambda: validate_request("function", "a", "b", "strict",
                                             "yes"))[0] == "invalid_input"



def test_plan_edits_declaration_and_reference():
    """План: по шагу на файл, смещения внутри текста, хеш исходного файла."""
    plan = compile_plan(_analysis(), TEXTS, "strict", False)
    assert [step.target for step in plan["steps"]] == ["scripts/caller.gd",
                                                      "scripts/player.gd"]
    caller, player = plan["steps"]
    assert caller.payload["edits"] == [{"start": CALLER.index("old_name"),
                                        "end": CALLER.index("old_name") + 8,
                                        "replacement": "new_name"}]
    assert player.payload["edits"] == [{"start": PLAYER.index("old_name"),
                                        "end": PLAYER.index("old_name") + 8,
                                        "replacement": "new_name"}]
    assert player.expected_hash == hashlib.sha256(
        PLAYER.encode("utf-8")).hexdigest()
    assert plan["stats"] == {"files": 2, "edits": 2, "proven": 1,
                             "probable": 0, "dynamic": 0, "skipped": 0}


def test_plan_refuses_name_conflict():
    """Новое имя уже объявлено в том же файле — отказ `name_conflict`."""
    texts = dict(TEXTS, **{"scripts/player.gd": CONFLICTING})
    assert _refusal(lambda: compile_plan(_analysis(), texts, "strict",
                                         False)) == ("conflict", "name_conflict")


def test_plan_refuses_unverified_without_flag():
    """`probable`-ссылка без разрешения останавливает план (ADR-0005)."""
    analysis = _analysis([_usage("scripts/player.gd", 4, 6, "declaration"),
                          _usage("scripts/caller.gd", 5, 2,
                                 confidence="probable")],
                         probable_count=1)
    assert _refusal(lambda: compile_plan(analysis, TEXTS, "strict",
                                         False)) == ("conflict",
                                                     "unverified_references")


def test_plan_allows_unverified_with_flag():
    """С `allow_unverified` та же ссылка правится и попадает в stats."""
    analysis = _analysis([_usage("scripts/player.gd", 4, 6, "declaration"),
                          _usage("scripts/caller.gd", 5, 2,
                                 confidence="probable")],
                         probable_count=1)
    plan = compile_plan(analysis, TEXTS, "strict", True)
    assert plan["stats"]["edits"] == 2
    assert plan["stats"]["probable"] == 1


def test_plan_refuses_dynamic_reference():
    """Динамическая ссылка по строке не правится автоматически никогда."""
    analysis = _analysis([_usage("scripts/player.gd", 4, 6, "declaration"),
                          _usage("scripts/caller.gd", 5, 2,
                                 confidence="dynamic")],
                         dynamic_count=1)
    assert _refusal(lambda: compile_plan(analysis, TEXTS, "strict",
                                         False)) == ("conflict",
                                                     "dynamic_references")


def test_plan_refuses_when_all_references_excluded():
    """Все ссылки сняты пользователем — переименование не имеет смысла."""
    assert _refusal(lambda: compile_plan(_analysis(), TEXTS, "strict", False,
                                         exclude=(("scripts/caller.gd", 5),))) \
        == ("conflict", "all_usages_excluded")


def test_plan_records_skipped_and_newlines():
    """Снятая ссылка уходит в `skipped_usages`, перевод строки — в payload."""
    analysis = _analysis([_usage("scripts/player.gd", 4, 6, "declaration"),
                          _usage("scripts/caller.gd", 5, 2),
                          _usage("scripts/caller.gd", 7, 2)])
    texts = dict(TEXTS, **{"scripts/caller.gd": CALLER + "\n\told_name()\n"})
    plan = compile_plan(analysis, texts, "strict", False,
                        exclude=(("scripts/caller.gd", 5),),
                        newlines={"scripts/caller.gd": "crlf"})
    assert plan["stats"]["skipped"] == 1
    assert plan["stats"]["edits"] == 2
    assert len(plan["skipped_usages"]) == 1
    assert plan["steps"][0].payload["newline"] == "crlf"


def test_contribution_build_matches_domain():
    """Вклад `COMPILER` — тот же домен: расхождение плана недопустимо."""
    plan = COMPILER.build(_analysis(), TEXTS, "strict", False)
    assert plan == compile_plan(_analysis(), TEXTS, "strict", False)

