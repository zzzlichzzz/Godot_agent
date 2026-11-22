"""Сценарии моста на фейке: кадры, handshake, отказы, повторы.

Проверки §5 среза: годный снимок, чужие `verbs_version`/`project_hash`, обрыв
посреди кадра, молчание, кадр больше лимита, двойной ответ, устаревший порт,
кадр без токена, переподключение. Живого Godot нет: сервер на GDScript
проверяется харнессом `needs_live` (`editor/harness/validate.gd`), приёмкой он
не считается. Правила: R-22 (кейс на каждое обещание), R-09 (без skip/xfail).
"""

from contextlib import contextmanager
import threading

import pytest

from python.kernel.errors import AppError
from python.kernel.schema import validate
from python.substrate.editor import framing, retry, verbs_catalog
from python.substrate.editor.client import EditorClient
from tests.py.integration.fake_editor import FakeEditor

TOKEN = "fake-token"


@pytest.fixture(autouse=True)
def fast_timeouts(monkeypatch):
    """Таймауты `retry.py` урезаются только в тесте: ждать 5 секунд незачем."""
    monkeypatch.setattr(retry, "REPLY_TIMEOUT", 0.2)
    monkeypatch.setattr(retry, "HANDSHAKE_TIMEOUT", 0.2)
    monkeypatch.setattr(retry, "CONNECT_TIMEOUT", 0.5)


@contextmanager
def bridge(tmp_path, mode="ok", port_file=None):
    """Фейк + клиент на его `port.json`; закрываются в обратном порядке."""
    fake = FakeEditor(mode)
    fake.__enter__()
    path = fake.write_port_file(tmp_path / "port.json") if port_file is None else port_file
    client = EditorClient(port_file=path)
    try:
        yield fake, client
    finally:
        client.close()
        fake.close()


def test_handshake_is_first_frame_then_primitive(tmp_path):
    """Первый кадр - `hello` с токеном и версией, дальше - примитив с токеном."""
    with bridge(tmp_path) as (fake, client):
        client.call("editor_ping")
    hello = fake.frames[0]["hello"]
    assert hello["protocol"] == 1
    assert hello["verbs_version"] == verbs_catalog.version()
    assert hello["token"] == TOKEN
    assert fake.frames[1]["verb"] == "editor_ping"
    assert fake.frames[1]["token"] == TOKEN


def test_ping_matches_contract_schema(tmp_path):
    """Ответ моста проходит `result_schema` примитива из словаря."""
    with bridge(tmp_path) as (_fake, client):
        ping = client.call("editor_ping")
    assert ping == {"godot": "4.6", "verbs_version": verbs_catalog.version(), "protocol": 1,
                    "open_scenes": 1, "uptime_s": 12.5}
    assert validate(ping, verbs_catalog.result_schema("editor_ping")) == []


def test_verbs_mismatch_is_not_retried(tmp_path):
    """Чужая версия словаря - `engine_down/verbs_mismatch` без повторов."""
    with bridge(tmp_path, "verbs_mismatch") as (fake, client):
        with pytest.raises(AppError) as excinfo:
            client.call("editor_ping")
    assert excinfo.value.kind == "engine_down"
    assert excinfo.value.details["reason"] == "verbs_mismatch"
    assert fake.connections == 1


def test_wrong_project_is_refused(tmp_path):
    """Чужой `project_hash` - `engine_down/wrong_project`."""
    with bridge(tmp_path, "wrong_project") as (fake, client):
        with pytest.raises(AppError) as excinfo:
            client.call("editor_ping")
    assert excinfo.value.details["reason"] == "wrong_project"
    assert fake.connections == 1


def test_truncated_frame_is_retried_once(tmp_path):
    """Обрыв посреди кадра - `truncated`: один повтор, дальше отказ."""
    with bridge(tmp_path, "truncate") as (fake, client):
        with pytest.raises(AppError) as excinfo:
            client.call("editor_ping")
    assert excinfo.value.details["reason"] == "truncated"
    assert fake.connections == 2


def test_silence_is_one_timeout_retry(tmp_path):
    """Молчание моста - `timeout`; после одного повтора отказ."""
    with bridge(tmp_path, "silent") as (fake, client):
        with pytest.raises(AppError) as excinfo:
            client.call("editor_ping")
    assert excinfo.value.details["reason"] == "timeout"
    assert fake.connections == 2


def test_frame_over_limit_is_not_retried(tmp_path):
    """Кадр больше лимита - `frame_too_big`, повтора нет."""
    with bridge(tmp_path, "too_big") as (fake, client):
        with pytest.raises(AppError) as excinfo:
            client.call("editor_ping")
    assert excinfo.value.details["reason"] == "frame_too_big"
    assert fake.connections == 1


def test_missing_port_file_is_no_bridge(tmp_path):
    """Нет `port.json` - это `no_bridge` (`unavailable`), а не ошибка инструмента."""
    client = EditorClient(port_file=str(tmp_path / "нет.json"))
    with pytest.raises(AppError) as excinfo:
        client.call("editor_ping")
    assert excinfo.value.kind == "unavailable"
    assert excinfo.value.details["reason"] == "no_bridge"


def test_stale_port_is_connect_failed(tmp_path):
    """Устаревший порт - `connect_failed`, а не вечное переподключение."""
    path = tmp_path / "port.json"
    path.write_text('{"port": 1, "token": "fake-token", "protocol": 1}',
                    encoding="utf-8")
    client = EditorClient(port_file=str(path))
    with pytest.raises(AppError) as excinfo:
        client.call("editor_ping")
    assert excinfo.value.kind == "engine_down"
    assert excinfo.value.details["reason"] == "connect_failed"


def test_double_answer_does_not_break_next_call(tmp_path):
    """Ответ пришёл дважды: второй кадр мусор, следующий вызов читает свой."""
    with bridge(tmp_path, "double") as (fake, client):
        first = client.call("editor_state")
        second = client.call("editor_state")
    assert first == second
    assert fake.connections == 1


def test_bad_token_is_refused_without_retry(tmp_path):
    """Токен не принят: отказ `denied` с причиной, соединения нет."""
    with bridge(tmp_path, "bad_token") as (fake, client):
        with pytest.raises(AppError) as excinfo:
            client.call("editor_ping")
        assert client._sock is None
    assert excinfo.value.kind == "denied"
    assert excinfo.value.details["reason"] == "bad_token"
    assert fake.connections == 1


def test_unknown_verb_is_refused(tmp_path):
    """Примитива нет в словаре моста - `unknown_tool` из ответа сервера."""
    with bridge(tmp_path, "ok") as (_fake, client):
        with pytest.raises(AppError) as excinfo:
            client.call("editor_unknown")
    assert excinfo.value.kind == "unknown_tool"


def test_reconnect_after_break(tmp_path):
    """Обрыв на первом соединении: вызов проходит после переподключения."""
    with bridge(tmp_path, ["close", "ok"]) as (fake, client):
        assert client.call("editor_ping")["godot"] == "4.6"
    assert fake.connections == 2


def test_snapshot_frame_roundtrip():
    """`decode(encode(x)) == x` для снимка: кадр не теряет поля."""
    from tests.py.integration.fake_editor import STATE

    obj, rest = framing.decode(framing.encode(STATE))
    assert obj == STATE
    assert rest == b""


def test_second_call_waits_for_the_first(tmp_path, monkeypatch):
    """Один in-flight: второй вызов ждёт ответа первого и не теряется."""
    from tests.py.integration.fake_editor import PING

    monkeypatch.setattr(retry, "REPLY_TIMEOUT", 2.0)
    with bridge(tmp_path, "slow") as (fake, client):
        answers = []
        first = threading.Thread(target=lambda: answers.append(
            client.call("editor_ping")))
        first.start()
        second = client.call("editor_ping")
        first.join(timeout=5)
    assert answers == [PING]
    assert second == PING
    assert fake.connections == 1
