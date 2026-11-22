"""Тесты домена `editing.scene_ops`: нормировка батча и приёмка ответа моста.

Мост подменён заглушкой с готовым ответом — ни сокета, ни файлов (домен без IO,
R-11). Отпечаток `plan_digest` закреплён литералом: то же правило считает
`scene_executor.gd`, и расхождение реализаций должно краснеть здесь. Схемы
примитивов проверяются интеграционным тестом на словаре; здесь — сами правила
домена (R-22: на каждое обещание кейс).
"""

import json

import pytest

from python.kernel.errors import AppError
from python.modules.editing.scene_ops.domain import core

SCENE = "res://main.tscn"
OPS = [{"op": "add_node", "parent": ".", "name": "Player", "type": "Node2D"},
       {"op": "set_property", "node": "Player", "property": "position",
        "value": {"x": 1, "y": 2}}]
#: `core.digest_of("res://main.tscn", 3, OPS)` — литерал, а не пересчёт в тесте.
DIGEST = "d8cb8c98a84aef3083b6476da35fc1a99dabc177e7088aa147d2385969a84e35"


class StubClient:
    """Порт моста в минимуме: готовый ответ и схема «объект»."""

    def __init__(self, answer, schema=None):
        self.answer = answer
        self.schema = {"type": "object"} if schema is None else schema
        self.calls = []

    def call(self, verb, args=None):
        self.calls.append((verb, dict(args or {})))
        return self.answer

    def result_schema(self, verb):
        return self.schema


def _args(**over):
    args = {"scene": SCENE, "expected_revision": 3, "operations": OPS}
    args.update(over)
    return args


def _plan_answer(revision=3, digest=DIGEST, scene=SCENE):
    return {"scene": scene, "revision": revision, "plan_digest": digest,
            "steps": [{"index": 0, "op": "add_node", "target_node": ".",
                       "preview": "add_node Player"}],
            "would_change": ["."], "warnings": []}


def _apply_answer(revision=4, receipts=2, applied=True, scene=SCENE):
    return {"scene": scene, "applied_revision": revision,
            "undo_label": "agent: scene_ops",
            "receipts": [{"step_id": index, "op": OPS[index]["op"],
                          "node_path": ".", "applied": applied}
                         for index in range(receipts)],
            "changes": [{"node_path": ".", "field": "name", "before": None,
                         "after": "Player"}]}


def test_canon_matches_json_dumps():
    """Свой канонический JSON совпадает с `json.dumps` побайтово (домен без json)."""
    samples = [None, True, False, 0, -7, 1.5, 1.0, "", "строка", "кавычки \" и \\",
               "перевод\nстроки\tи \u0001", [1, "a", None], {"b": 1, "a": [True, {}]},
               {"op": "set_property", "value": {"position": {"x": 1.5, "y": -2}}}]
    for sample in samples:
        assert core.canon(sample) == json.dumps(sample, sort_keys=True,
                                                separators=(",", ":"),
                                                ensure_ascii=False)


def test_canon_rejects_unserializable_value():
    """Не-JSON значение — `invalid_input`, а не тихая подмена строкой."""
    with pytest.raises(AppError) as excinfo:
        core.canon({"value": {1, 2}})
    assert excinfo.value.kind == "invalid_input"
    with pytest.raises(AppError):
        core.canon({1: "ключ не строка"})


# --- нормировка запроса ------------------------------------------------
def test_unknown_operation_breaks_whole_batch():
    """Неизвестная операция — `invalid_input/unknown_operation`, а не «пропустим»."""
    args = _args(operations=[OPS[0], {"op": "delete_node", "node": "Player"}])
    with pytest.raises(AppError) as excinfo:
        core.build_request(args)
    assert excinfo.value.kind == "invalid_input"
    assert excinfo.value.details["reason"] == "unknown_operation"


def test_limits_are_enforced():
    """Больше 64 операций, пустой список и значение > 4 КиБ — отказ."""
    many = [dict(OPS[0], name="N%d" % index) for index in range(core.MAX_OPERATIONS + 1)]
    for operations in ([], many,
                       [{"op": "set_property", "node": "Player", "property": "text",
                         "value": "я" * (core.MAX_VALUE_BYTES // 2 + 1)}]):
        with pytest.raises(AppError) as excinfo:
            core.build_request(_args(operations=operations))
        assert excinfo.value.kind == "invalid_input"


def test_apply_requires_matching_plan_digest():
    """`apply=true` без отпечатка плана или с чужим — `stale_plan`."""
    for digest in (None, "0" * 64):
        with pytest.raises(AppError) as excinfo:
            core.build_request(_args(apply=True, plan_digest=digest))
        assert excinfo.value.kind == "stale_plan"
    assert core.build_request(_args(apply=True, plan_digest=DIGEST))["apply"] is True


def test_scene_and_revision_are_validated():
    """Сцена только `res://`, ревизия — целое >= 0 (bool не считается числом)."""
    for args in (_args(scene="main.tscn"), _args(expected_revision=True),
                 _args(expected_revision=-1), _args(expected_revision="3")):
        with pytest.raises(AppError) as excinfo:
            core.build_request(args)
        assert excinfo.value.kind == "invalid_input"





# --- ответ моста ------------------------------------------------------
def test_plan_accepts_consistent_answer():
    """Годный ответ: план без записи, отпечаток и ревизия — из запроса."""
    client = StubClient(_plan_answer())
    answer = core.plan(client, core.build_request(_args()))
    assert answer["applied"] is False
    assert answer["plan_digest"] == DIGEST
    assert answer["revision"] == 3
    verb, sent = client.calls[0]
    assert verb == "editor_scene_plan"
    assert sent["expected_revision"] == 3
    assert sent["operations"] == OPS
    assert "plan_digest" not in sent


def test_plan_reports_revision_conflict():
    """Сцена ушла вперёд — `conflict/revision_mismatch`, а не «применим на удачу»."""
    with pytest.raises(AppError) as excinfo:
        core.plan(StubClient(_plan_answer(revision=4)), core.build_request(_args()))
    assert excinfo.value.kind == "conflict"
    assert excinfo.value.details["reason"] == "revision_mismatch"


def test_plan_rejects_foreign_digest():
    """Другая реализация отпечатка — `engine_down/bad_result`."""
    with pytest.raises(AppError) as excinfo:
        core.plan(StubClient(_plan_answer(digest="1" * 64)),
                  core.build_request(_args()))
    assert excinfo.value.kind == "engine_down"
    assert excinfo.value.details["reason"] == "bad_result"


def test_plan_rejects_other_scene_and_schema_problem():
    """Ответ про другую сцену и ответ не по схеме — оба отказ."""
    with pytest.raises(AppError):
        core.plan(StubClient(_plan_answer(scene="res://other.tscn")),
                  core.build_request(_args()))
    strict = {"type": "object", "properties": {"scene": {"type": "string"}},
              "required": ["scene", "revision"], "additionalProperties": False}
    with pytest.raises(AppError) as excinfo:
        core.plan(StubClient({"scene": SCENE}, strict), core.build_request(_args()))
    assert excinfo.value.kind == "engine_down"
    assert excinfo.value.details["problems"]


def test_apply_accepts_full_receipts():
    """Применение: квитанции на все шаги, ревизия +1, undo одним именем."""
    client = StubClient(_apply_answer())
    answer = core.apply(client, core.build_request(_args(apply=True,
                                                         plan_digest=DIGEST)))
    assert answer["applied"] is True
    assert answer["applied_revision"] == 4
    assert [item["applied"] for item in answer["receipts"]] == [True, True]
    assert client.calls[0][0] == "editor_scene_apply"
    assert client.calls[0][1]["plan_digest"] == DIGEST
    assert client.calls[0][1]["operations"] == OPS


def test_apply_rejects_partial_or_growing_batch():
    """Не все квитанции, неприменённый шаг, чужая новая ревизия — отказ."""
    request = core.build_request(_args(apply=True, plan_digest=DIGEST))
    for answer in (_apply_answer(receipts=1), _apply_answer(applied=False),
                   _apply_answer(revision=9)):
        with pytest.raises(AppError) as excinfo:
            core.apply(StubClient(answer), request)
        assert excinfo.value.kind == "engine_down"
        assert excinfo.value.details["reason"] == "bad_result"


def test_run_dispatches_by_apply_flag():
    """`perform` — план или применение по флагу `apply` в запросе."""
    plan, applied = StubClient(_plan_answer()), StubClient(_apply_answer())
    assert core.perform(plan, core.build_request(_args()))["applied"] is False
    assert core.perform(applied, core.build_request(
        _args(apply=True, plan_digest=DIGEST)))["applied"] is True
    assert plan.calls[0][0] == "editor_scene_plan"
    assert applied.calls[0][0] == "editor_scene_apply"
