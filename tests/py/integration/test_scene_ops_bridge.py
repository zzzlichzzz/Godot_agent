"""Сценарии батча сцены через фейковый мост (часть B, §5 среза).

Мост подменён `FakeEditor`: он отвечает на `editor_scene_plan` и
`editor_scene_apply` так же, как `editor/bridge/verbs/scene/`, и умеет отказать
по требованию сценария (`error`, `fail_at`, `drop_receipts`, подмена отпечатка и
ревизии). Python ничего не пишет в сцену: всё «применение» — это проверка
квитанций, а сам undo живёт в GDScript. Живой редактор не нужен — отсюда `needs_live`
в отдельном долге. Правила: R-22 (кейс на обещание), R-09 (без skip/xfail).
"""

from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.schema import validate
from python.modules.editing.scene_ops import app as ops_app
from python.modules.editing.scene_ops import tools as ops_tools
from python.modules.editing.scene_ops.domain import core
from python.substrate.editor import retry, verbs_catalog
from python.substrate.editor.client import EditorClient
from tests.py.integration.fake_editor import FakeEditor

SCENE = "res://main.tscn"
OPS = [{"op": "add_node", "parent": ".", "name": "Player", "type": "Node2D"},
       {"op": "set_property", "node": "Player", "property": "position",
        "value": {"x": 1, "y": 2}}]


@pytest.fixture(autouse=True)
def fast_timeouts(monkeypatch):
    """Таймауты `retry.py` урезаются только в тесте: ждать 5 секунд незачем."""
    monkeypatch.setattr(retry, "REPLY_TIMEOUT", 0.2)
    monkeypatch.setattr(retry, "HANDSHAKE_TIMEOUT", 0.2)
    monkeypatch.setattr(retry, "CONNECT_TIMEOUT", 0.5)


class Ctx:
    """Контекст модуля: единственный порт `editor` — клиент моста."""

    def __init__(self, client):
        self._client = client

    def port(self, name):
        assert name == "editor", name
        return self._client


def bridge(tmp_path, mode="ok", scene=None, digest_fn=core.digest_of):
    """Фейк + клиент + контекст на одном `port.json` (закрываются вместе)."""
    fake = FakeEditor(mode, digest_fn=digest_fn, scene=scene)
    fake.__enter__()
    path = fake.write_port_file(tmp_path / "port.json")
    client = EditorClient(port_file=path)
    return fake, Ctx(client), client


def call(ctx, **over):
    args = {"scene": SCENE, "expected_revision": 3, "operations": OPS}
    args.update(over)
    return ops_app.call("scene_ops", args, ctx)


def verbs_sent(fake):
    """Примитивы в кадрах: первый кадр — `hello`, дальше — запросы."""
    return [frame["verb"] for frame in fake.frames if "verb" in frame]


def test_plan_then_apply_in_one_undo(tmp_path):
    """План без записи, затем применение с его отпечатком: два кадра, один undo."""
    fake, ctx, client = bridge(tmp_path)
    try:
        planned = call(ctx)
        applied = call(ctx, apply=True, plan_digest=planned["plan_digest"])
    finally:
        client.close()
        fake.close()
    assert planned["applied"] is False
    assert planned["revision"] == 3
    assert applied["applied"] is True
    assert applied["applied_revision"] == 4
    assert applied["undo_label"] == "agent: scene_ops"
    assert [item["applied"] for item in applied["receipts"]] == [True, True]
    assert applied["plan_digest"] == planned["plan_digest"] == core.digest_of(SCENE, 3, OPS)
    assert verbs_sent(fake) == ["editor_scene_plan", "editor_scene_apply"]
    assert fake.frames[2]["args"]["plan_digest"] == planned["plan_digest"]
    assert validate(planned, ops_tools.SCENE_OPS.result) == []
    assert validate(applied, ops_tools.SCENE_OPS.result) == []
    for verb in ("editor_scene_plan", "editor_scene_apply"):
        assert verbs_catalog.result_schema(verb)["required"]
    assert ops_tools.SCENE_OPS.effects == "write"


def test_plan_alone_sends_no_apply(tmp_path):
    """Один план: кадр применения не уходит, «применилось» не появляется."""
    fake, ctx, client = bridge(tmp_path)
    try:
        planned = call(ctx)
    finally:
        client.close()
        fake.close()
    assert verbs_sent(fake) == ["editor_scene_plan"]
    assert planned["receipts"] == []
    assert planned["steps"][0]["target_node"] == "."
    assert planned["steps"][1]["index"] == 1



def test_revision_mismatch_is_conflict(tmp_path):
    """Сцена успела измениться — `conflict/revision_mismatch`, батч не ушёл."""
    fake, ctx, client = bridge(tmp_path, scene={"revision": 4})
    try:
        with pytest.raises(AppError) as excinfo:
            call(ctx)
    finally:
        client.close()
        fake.close()
    assert excinfo.value.kind == "conflict"
    assert excinfo.value.details["reason"] == "revision_mismatch"


def test_stale_plan_never_reaches_bridge(tmp_path):
    """Отпечаток плана не описывает новый батч — `stale_plan` до сети."""
    fake, ctx, client = bridge(tmp_path)
    try:
        planned = call(ctx)
        other = [dict(OPS[0], name="Enemy")]
        with pytest.raises(AppError) as excinfo:
            call(ctx, operations=other, apply=True, plan_digest=planned["plan_digest"])
    finally:
        client.close()
        fake.close()
    assert excinfo.value.kind == "stale_plan"
    assert verbs_sent(fake) == ["editor_scene_plan"]


def test_foreign_digest_is_engine_down(tmp_path):
    """Мост считает отпечаток иначе — ответ не принят (`engine_down/bad_result`)."""
    fake, ctx, client = bridge(tmp_path, digest_fn=None)
    try:
        with pytest.raises(AppError) as excinfo:
            call(ctx)
    finally:
        client.close()
        fake.close()
    assert excinfo.value.kind == "engine_down"
    assert excinfo.value.details["reason"] == "bad_result"
    assert "plan_digest" in excinfo.value.details["problems"][0]


def test_failure_on_second_operation_reports_nothing_applied(tmp_path):
    """Второй шаг не применился: квитанция `applied=false` — весь батч отвергнут."""
    fake, ctx, client = bridge(tmp_path, scene={"fail_at": 2})
    try:
        with pytest.raises(AppError) as excinfo:
            call(ctx, apply=True, plan_digest=core.digest_of(SCENE, 3, OPS))
    finally:
        client.close()
        fake.close()
    assert excinfo.value.kind == "engine_down"
    assert excinfo.value.details["reason"] == "bad_result"
    assert "неприменённый шаг" in excinfo.value.details["problems"][0]


def test_applied_without_receipts_is_refused(tmp_path):
    """«Применилось» без квитанций — не доказательство: ответ отвергнут."""
    fake, ctx, client = bridge(tmp_path, scene={"drop_receipts": True})
    try:
        with pytest.raises(AppError) as excinfo:
            call(ctx, apply=True, plan_digest=core.digest_of(SCENE, 3, OPS))
    finally:
        client.close()
        fake.close()
    assert excinfo.value.kind == "engine_down"
    assert "0 квитанций" in excinfo.value.details["problems"][0]


def test_apply_error_frame_is_not_retried(tmp_path):
    """Отказ моста на применении (`apply_failed`) — одно соединение, без повторов."""
    fake, ctx, client = bridge(tmp_path, scene={"error": "apply_failed"})
    try:
        with pytest.raises(AppError) as excinfo:
            call(ctx, apply=True, plan_digest=core.digest_of(SCENE, 3, OPS))
    finally:
        client.close()
        fake.close()
    assert excinfo.value.kind == "engine_down"
    assert excinfo.value.details["reason"] == "apply_failed"
    assert fake.connections == 1


def test_truncated_reply_after_apply_is_retried_once(tmp_path):
    """Обрыв кадра после запроса: политика `retry` даёт ровно один повтор."""
    fake, ctx, client = bridge(tmp_path, mode="truncate")
    try:
        with pytest.raises(AppError) as excinfo:
            call(ctx, apply=True, plan_digest=core.digest_of(SCENE, 3, OPS))
    finally:
        client.close()
        fake.close()
    assert excinfo.value.kind == "engine_down"
    assert excinfo.value.details["reason"] in ("truncated", "timeout")
    assert fake.connections == 2


def test_answer_about_other_verb_is_schema_failure(tmp_path):
    """Ответ не на тот примитив (`wrong_request`) не проходит схему словаря."""
    fake, ctx, client = bridge(tmp_path, mode="wrong_request")
    try:
        with pytest.raises(AppError) as excinfo:
            call(ctx)
    finally:
        client.close()
        fake.close()
    assert excinfo.value.kind == "engine_down"
    assert excinfo.value.details["reason"] == "bad_result"
    assert excinfo.value.details["problems"]


def test_bad_request_never_reaches_bridge(tmp_path):
    """Неизвестная операция и 65 операций — отказ до сети: кадров нет."""
    fake, ctx, client = bridge(tmp_path)
    try:
        for args in ({"operations": [{"op": "delete_node", "node": "Player"}]},
                     {"operations": [dict(OPS[0], name="N%d" % index)
                                     for index in range(core.MAX_OPERATIONS + 1)]}):
            with pytest.raises(AppError) as excinfo:
                call(ctx, **args)
            assert excinfo.value.kind == "invalid_input"
    finally:
        client.close()
        fake.close()
    assert fake.frames == []


def test_owner_serves_only_its_tool(tmp_path):
    """Чужой инструмент в `editing.scene_ops` — `unknown_tool`, кадров нет."""
    fake, ctx, client = bridge(tmp_path)
    try:
        with pytest.raises(AppError) as excinfo:
            ops_app.call("context", {"scene": SCENE}, ctx)
    finally:
        client.close()
        fake.close()
    assert excinfo.value.kind == "unknown_tool"
    assert fake.frames == []

