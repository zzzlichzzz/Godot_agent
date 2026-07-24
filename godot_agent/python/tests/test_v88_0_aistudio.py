# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v88.0: сетевой захват ответа Google AI Studio (ai_studio_net).

Структура чанков воспроизводит РЕАЛЬНЫЙ дамп Response запроса
MakerSuiteService/GenerateContent от 2026-07-22 (см. README v88.0):
размышления с флагом part[12]==1, дельты ответа, финальный чанк с
маркером [content, 1] и пустой part с подписью на позиции 13.
"""
import base64
import gzip
import json
import time

from ai_studio_net import (
    AiStudioChatMonitor,
    decode_aistudio_chunks_partial,
    extract_parts,
    has_finish_marker,
)

URL = ("https://alkalimakersuite-pa.clients6.google.com/$rpc/"
       "google.internal.alkali.applications.makersuite.v1."
       "MakerSuiteService/GenerateContent")
MIME = "application/json+protobuf; charset=UTF-8"


def _thought_chunk(text):
    part = [None, text] + [None] * 10 + [1]
    return [[[[[part], "model"]]], None,
            [6820, None, 6820, None, [[1, 6820]]],
            None, None, None, None, "v1_tok"]


def _answer_chunk(text):
    part = [None, text]
    return [[[[[part], "model"]]], None,
            [6820, 9, 14980, None, [[1, 6820]], None, None, None, None, 8151],
            None, None, None, None, "v1_tok"]


def _final_chunk():
    part = [None, ""] + [None] * 11 + ["c2lnbmF0dXJl"]
    content = [[part], "model"]
    return [[[content, 1]], None,
            [6820, 1523, 16494, None, [[1, 6820]], None, None, None, None, 8151],
            None, None, None, None, "v1_tok"]


THOUGHT_1 = ("**Initiating Scene Creation**\n\n"
             "Я начинаю новую 3D сцену в Godot 4.6.\n\n\n")
ANS_1 = "Создаю 3D сцену с настро"
ANS_2 = ("енным освещением.\n\n```agent_action\n{\n  \"action\": \"plan\",\n"
         "  \"steps\": []\n}\n```\n===FILE_1===\nextends Node3D\n"
         "===END_FILE_1===\n===DONE===")
EXPECT_ANSWER = ANS_1 + ANS_2

BODY = json.dumps(
    [_thought_chunk(THOUGHT_1), _answer_chunk(ANS_1),
     _answer_chunk(ANS_2), _final_chunk()],
    ensure_ascii=False).encode("utf-8")


class _FakeCDP:
    """Стрим включается, getResponseBody недоступен (как _StreamOnlyCDP
    в тестах kimi)."""

    def __init__(self):
        self.handlers = {}
        self.body_calls = 0

    def on_event(self, name, cb):
        self.handlers[name] = cb

    def send_command(self, method, params=None):
        if method == "Network.streamResourceContent":
            return {"bufferedData": ""}
        if method == "Network.getResponseBody":
            self.body_calls += 1
            raise RuntimeError("body is not available")
        return {}

    def is_alive(self):
        return True


def _start_request(mon, req_id="req-1"):
    mon._on_response_received({
        "requestId": req_id,
        "response": {"url": URL, "mimeType": MIME},
    })
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if mon._stream_mode.get(req_id):
            return
        time.sleep(0.01)
    raise AssertionError("живой стрим не включился")


def _feed(mon, req_id, data):
    mon._on_data_received({
        "requestId": req_id,
        "data": base64.b64encode(data).decode("ascii"),
    })


def _wait_not_generating(mon, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not mon.is_generating():
            return True
        time.sleep(0.01)
    return False


def _collect(events):
    answer = ""
    thought = ""
    finished = False
    for ev in events:
        for text, is_thought in extract_parts(ev):
            if is_thought:
                thought += text
            else:
                answer += text
        finished = finished or has_finish_marker(ev)
    return answer, thought, finished


def test_full_body_parses_completely():
    events, consumed = decode_aistudio_chunks_partial(BODY)
    assert consumed == len(BODY), (consumed, len(BODY))
    answer, thought, finished = _collect(events)
    assert answer == EXPECT_ANSWER, answer
    assert thought == THOUGHT_1, thought
    assert finished


def test_partial_decoder_survives_any_split():
    for step in (1, 3, 7, 64, 1024):
        buf = bytearray()
        events_all = []
        for k in range(0, len(BODY), step):
            buf.extend(BODY[k:k + step])
            events, consumed = decode_aistudio_chunks_partial(bytes(buf))
            if consumed:
                del buf[:consumed]
            events_all.extend(events)
        answer, thought, finished = _collect(events_all)
        assert answer == EXPECT_ANSWER, ("шаг", step, answer)
        assert thought == THOUGHT_1, ("шаг", step)
        assert finished, ("шаг", step)


def test_no_false_finish_marker():
    assert not has_finish_marker(_answer_chunk("x"))
    assert not has_finish_marker(_thought_chunk("y"))
    assert has_finish_marker(_final_chunk())


def test_thought_not_mixed_into_answer():
    assert extract_parts(_thought_chunk("думаю")) == [("думаю", True)]
    assert extract_parts(_answer_chunk("отвечаю")) == [("отвечаю", False)]


def test_monitor_streams_live_and_finishes():
    cdp = _FakeCDP()
    mon = AiStudioChatMonitor(cdp)
    _start_request(mon)
    assert mon.is_generating()
    mid = len(BODY) // 2  # режем в т.ч. посреди многобайтовых символов
    _feed(mon, "req-1", BODY[:mid])
    _feed(mon, "req-1", BODY[mid:])
    assert mon.current_text() == EXPECT_ANSWER, mon.current_text()
    assert mon.thought_text() == THOUGHT_1
    assert mon.is_finished()
    mon._on_loading_finished({"requestId": "req-1"})
    assert _wait_not_generating(mon)
    assert mon.assistant_message_count() == 1
    assert cdp.body_calls == 0  # тело собрано живым стримом


def test_monitor_gzip_stream_no_duplicates():
    cdp = _FakeCDP()
    mon = AiStudioChatMonitor(cdp)
    _start_request(mon)
    gz = gzip.compress(BODY)
    third = max(1, len(gz) // 3)
    _feed(mon, "req-1", gz[:third])
    _feed(mon, "req-1", gz[third:2 * third])
    _feed(mon, "req-1", gz[2 * third:])
    assert mon.current_text() == EXPECT_ANSWER, mon.current_text()
    assert mon.thought_text() == THOUGHT_1
    mon._on_loading_finished({"requestId": "req-1"})
    assert _wait_not_generating(mon)


def test_truncated_stream_resets_generating():
    cdp = _FakeCDP()
    mon = AiStudioChatMonitor(cdp)
    _start_request(mon)
    body = json.dumps([_answer_chunk("обрыв посере")],
                      ensure_ascii=False).encode("utf-8")
    _feed(mon, "req-1", body[:-5])  # без финального чанка и «]»
    mon._on_loading_finished({"requestId": "req-1"})
    assert _wait_not_generating(mon)  # generating сброшен, зависания нет


def test_net_fallback_splits_action():
    """v88.2: сетевой фолбэк в extract_answer_settled должен отдавать
    actionRaw = содержимое ограды agent_action (JSON + тела ===МЕТОК===),
    а не None — иначе решатель меток не находит тела и действие
    пропадает (репорт тестера 23.07: «действие: нет» при полном
    сетевом тексте 9649 симв.)."""
    _install_selenium_stub()
    from parser_base import extract_answer_settled, split_net_text_and_action

    net_full = _NET_FULL_SAMPLE

    # Сплит сам по себе: проза без ограды и DONE, raw с телами меток.
    body, raw = split_net_text_and_action(net_full)
    assert raw is not None and u"===FILE_1===" in raw and u"===END_FILE_2===" in raw
    assert u"===DONE===" not in body and u"```" not in body
    assert body.startswith(u"Пояснение")

    # DOM отдал обрезанный ответ: JSON есть, тел меток нет.
    dom_result = {
        "text": u"Пояснение перед планом правок.",
        "actionRaw": u'{"action": "plan", "steps": [{"search_ref": "FILE_1", "replace_ref": "FILE_2"}]}',
    }
    res = extract_answer_settled(
        None, lambda d: dict(dom_result),
        is_generating_fn=lambda d: False,
        log_tag=u"[test]", attempts=1, delay=0.0, poll=0.01,
        net_fallback_fn=lambda: net_full)
    assert res["actionRaw"] is not None, u"actionRaw не должен быть None"
    assert u"===FILE_1===" in res["actionRaw"], u"тела меток должны быть в actionRaw"
    assert u"===DONE===" not in res["text"]


def test_insert_verify_matches():
    """v88.4: сверка текста поля ввода с отправляемым промптом — защита
    от отправки «не того сообщения» (идея тестера 23.07). Пробелы/переводы
    строк/NBSP не считаются различием (contenteditable их меняет)."""
    _install_selenium_stub()
    from parser_base import BaseSiteParser
    match = BaseSiteParser._insert_text_matches
    assert match(None, u"привет  мир\n", u"привет мир")
    assert match(None, u"привет\u00a0мир", u"привет мир")
    assert not match(None, u"привет мир", u"привет мираж")
    assert not match(None, u"", u"привет")
    assert not match(None, u"привет мир и ещё старый хвост", u"привет мир")


def _install_selenium_stub():
    # --- заглушка selenium (как в test_v87_9_regen.py): боевого браузера нет ---
    import sys
    import types
    if "selenium" not in sys.modules:
        _selenium = types.ModuleType("selenium")
        _webdriver = types.ModuleType("selenium.webdriver")
        _common = types.ModuleType("selenium.webdriver.common")
        _keys_mod = types.ModuleType("selenium.webdriver.common.keys")
        _common_pkg = types.ModuleType("selenium.common")
        _exc_mod = types.ModuleType("selenium.common.exceptions")

        class _Keys(object):
            ENTER = "\n"
            CONTROL = "\ue009"
            SPACE = " "
            BACKSPACE = "\ue003"

        class WebDriverException(Exception):
            pass

        class JavascriptException(WebDriverException):
            pass

        class StaleElementReferenceException(WebDriverException):
            pass

        class NoSuchWindowException(WebDriverException):
            pass

        class TimeoutException(WebDriverException):
            pass

        _keys_mod.Keys = _Keys
        for _n, _c in (("WebDriverException", WebDriverException),
                       ("JavascriptException", JavascriptException),
                       ("StaleElementReferenceException", StaleElementReferenceException),
                       ("NoSuchWindowException", NoSuchWindowException),
                       ("TimeoutException", TimeoutException)):
            setattr(_exc_mod, _n, _c)
        _selenium.webdriver = _webdriver
        _webdriver.common = _common
        _common.keys = _keys_mod
        _selenium.common = _common_pkg
        _common_pkg.exceptions = _exc_mod
        sys.modules.setdefault("selenium", _selenium)
        sys.modules.setdefault("selenium.webdriver", _webdriver)
        sys.modules.setdefault("selenium.webdriver.common", _common)
        sys.modules.setdefault("selenium.webdriver.common.keys", _keys_mod)
        sys.modules.setdefault("selenium.common", _common_pkg)
        sys.modules.setdefault("selenium.common.exceptions", _exc_mod)


_NET_FULL_SAMPLE = (
        u"Пояснение перед планом правок.\n\n"
        u"```agent_action\n"
        u"{\n"
        u'  "action": "plan",\n'
        u'  "description": "Фикс",\n'
        u'  "steps": [{"action": "patch_file", "path": "res://a.gd",'
        u' "search_ref": "FILE_1", "search_ref_lines": 1,'
        u' "replace_ref": "FILE_2", "replace_ref_lines": 1}]\n'
        u"}\n"
        u"===FILE_1===\nold_line\n===END_FILE_1===\n"
        u"===FILE_2===\nnew_line\n===END_FILE_2===\n"
        u"```\n===DONE==="
)


def _run_all():
    tests = [
        test_full_body_parses_completely,
        test_partial_decoder_survives_any_split,
        test_no_false_finish_marker,
        test_thought_not_mixed_into_answer,
        test_monitor_streams_live_and_finishes,
        test_monitor_gzip_stream_no_duplicates,
        test_truncated_stream_resets_generating,
        test_net_fallback_splits_action,
        test_insert_verify_matches,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("OK   %s" % fn.__name__)
        except Exception as e:
            failed += 1
            print("FAIL %s -> %r" % (fn.__name__, e))
    if failed:
        print("%d test(s) FAILED" % failed)
        raise SystemExit(1)
    print("ALL OK")


if __name__ == "__main__":
    _run_all()
