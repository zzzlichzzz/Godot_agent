"""modules/editing/write_preview/tests/test_core.py - план без диска и Godot.

Компилятор получает отчёт поиска и тексты: здесь проверяются НАШИ смещения
(срез текста обязан совпасть со старым именем), сортировка шагов, `exclude`,
отказы по `mode`/`allow_unverified` и стабильность digest.
"""

import hashlib

import pytest

from python.kernel.errors import AppError
from python.kernel.write_plan import digest_of
from python.modules.editing import symbol_rename

A = "res://src/a.gd"
B = "res://src/b.gd"
TEXTS = {A: "func take_damage(x):\n\tpass\n\nfunc run():\n\ttake_damage(1)\n",
         B: "func hit(other):\n\tother.take_damage(2)\n"}


def usage(path, line, column, link, confidence):
    return {"path": path, "line": line, "column": column, "link": link,
            "confidence": confidence, "note": None}


def analysis(**extra):
    data = {
        "kind": "function", "old_name": "take_damage",
        "new_name": "apply_damage", "declaration_path": A,
        "declaration_line": 1, "mode": "strict", "allow_unverified": False,
        "proven_count": 2, "probable_count": 1, "dynamic_count": 0,
        "usages": [usage(A, 1, 6, "declaration", "proven"),
                   usage(A, 5, 2, "call", "proven"),
                   usage(B, 2, 8, "member", "probable")],
        "risks": ["%s:2 [member, probable] — тип не доказан" % B],
    }
    data.update(extra)
    return data


def plan(mode="strict", allow=False, exclude=(), data=None):
    return symbol_rename.compile_plan(data or analysis(), TEXTS, mode, allow, exclude,
                                 {A: "lf", B: "crlf"})


def test_steps_are_sorted_by_target_and_carry_our_offsets():
    result = plan("probable", True)
    assert [step.target for step in result["steps"]] == [A, B]
    first = result["steps"][0]
    assert first.payload["newline"] == "lf"
    edits = first.payload["edits"]
    assert edits[0]["start"] == 5 and edits[0]["end"] == 16
    assert TEXTS[A][edits[0]["start"]:edits[0]["end"]] == "take_damage"
    second = result["steps"][1]
    assert second.payload["newline"] == "crlf"
    edit = second.payload["edits"][0]
    assert TEXTS[B][edit["start"]:edit["end"]] == "take_damage"
    assert edit["replacement"] == "apply_damage"


def test_expected_hash_is_sha256_of_normalised_text():
    result = plan("probable", True)
    digest = hashlib.sha256(TEXTS[A].encode("utf-8")).hexdigest()
    assert result["steps"][0].expected_hash == digest


def test_probable_without_allow_stays_out_of_the_plan():
    result = plan("probable", False)
    assert [step.target for step in result["steps"]] == [A]
    assert result["stats"]["skipped"] == 1
    assert result["stats"]["probable"] == 1


def test_allow_unverified_puts_probable_into_the_plan():
    result = plan("probable", True)
    assert result["stats"]["files"] == 2
    assert result["stats"]["edits"] == 3


def test_strict_with_probable_is_a_conflict():
    with pytest.raises(AppError) as caught:
        plan("strict", False)
    assert caught.value.kind == "conflict"
    assert caught.value.details["reason"] == "unverified_references"


def test_strict_with_dynamic_is_a_conflict_even_if_excluded():
    data = analysis()
    data["usages"].append(usage(B, 2, 8, "string", "dynamic"))
    with pytest.raises(AppError) as caught:
        symbol_rename.compile_plan(data, TEXTS, "strict", True, [(B, 2)], {})
    assert caught.value.details["reason"] == "dynamic_references"


def test_exclude_removes_the_place_from_steps_and_reports_it():
    result = plan("probable", True, exclude=[(B, 2)])
    assert [step.target for step in result["steps"]] == [A]
    assert len(result["skipped_usages"]) == 1
    assert "снято пользователем" in result["skipped_usages"][0]


def test_excluding_every_reference_is_a_conflict():
    with pytest.raises(AppError) as caught:
        plan("probable", True, exclude=[(A, 5), (B, 2)])
    assert caught.value.details["reason"] == "all_usages_excluded"


def test_name_conflict_is_detected_in_the_declaration_file():
    data = analysis(new_name="run")
    with pytest.raises(AppError) as caught:
        symbol_rename.compile_plan(data, TEXTS, "probable", True, (), {})
    assert caught.value.details["reason"] == "name_conflict"


def test_digest_depends_on_the_plan_not_on_the_call():
    first = plan("probable", True)
    second = plan("probable", True)
    body = dict(kind="function", declaration=A + ":1", old_name="take_damage",
                new_name="apply_damage", mode="probable", allow_unverified=True)
    assert (digest_of(steps=first["steps"], expected={A: "1", B: "2"}, **body)
            == digest_of(steps=second["steps"], expected={A: "1", B: "2"}, **body))


def test_digest_changes_when_the_text_moves():
    first = plan("probable", True)
    other = {A: TEXTS[A].replace("\tpass", "\t pass"), B: TEXTS[B]}
    moved = symbol_rename.compile_plan(analysis(), other, "probable", True, (), {})
    body = dict(kind="function", declaration=A + ":1", old_name="take_damage",
                new_name="apply_damage", mode="probable", allow_unverified=True)
    assert (digest_of(steps=first["steps"], expected={}, **body)
            != digest_of(steps=moved["steps"], expected={}, **body))


@pytest.mark.parametrize("kwargs", [
    {"old_name": "func"}, {"new_name": "2x y"}, {"new_name": "take_damage"},
    {"mode": "fast"}, {"allow_unverified": "yes"},
])
def test_request_validation(kwargs):
    base = {"kind": "function", "old_name": "take_damage",
            "new_name": "apply_damage", "mode": "strict",
            "allow_unverified": False}
    base.update(kwargs)
    with pytest.raises(AppError) as caught:
        symbol_rename.validate_request(base["kind"], base["old_name"], base["new_name"],
                                  base["mode"], base["allow_unverified"])
    assert caught.value.kind == "invalid_input"
