# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Offline tests for v87.1 (kimi.com CDP-based parser pilot).

No live browser/network needed: uses the two real HAR captures already
parsed into fixtures under /data/qwen_repro/ during design (see
README_CHANGES.txt, v87.1) to validate:
  1. cdp_ws.decode_connect_frames <-> encode_connect_frame round-trip.
  2. KimiChatMonitor block-assembly logic reproduces the exact streamed
     text (including the ```agent_action fence and ===DONE===) from real
     captured Connect-RPC events.
  3. kimi_parser.split_text_and_action correctly separates the action JSON
     from the answer text.
"""
import pickle
import sys
import threading
import time
import types

# (путь настраивается в шапке файла — v104-restructure)

# selenium is not installed in this sandbox; parser_base/kimi_parser only
# need a few names from it at import time (mirrors dump_js2.py's stub).
selenium_mod = types.ModuleType("selenium")
selenium_common = types.ModuleType("selenium.common")
selenium_common_exceptions = types.ModuleType("selenium.common.exceptions")


class JavascriptException(Exception):
    pass


class StaleElementReferenceException(Exception):
    pass


class WebDriverException(Exception):
    pass


selenium_common_exceptions.JavascriptException = JavascriptException
selenium_common_exceptions.StaleElementReferenceException = StaleElementReferenceException
selenium_common_exceptions.WebDriverException = WebDriverException
selenium_webdriver = types.ModuleType("selenium.webdriver")
selenium_webdriver_common = types.ModuleType("selenium.webdriver.common")
selenium_webdriver_common_keys = types.ModuleType("selenium.webdriver.common.keys")


class Keys:
    ENTER = "\n"


selenium_webdriver_common_keys.Keys = Keys
sys.modules["selenium"] = selenium_mod
sys.modules["selenium.common"] = selenium_common
sys.modules["selenium.common.exceptions"] = selenium_common_exceptions
sys.modules["selenium.webdriver"] = selenium_webdriver
sys.modules["selenium.webdriver.common"] = selenium_webdriver_common
sys.modules["selenium.webdriver.common.keys"] = selenium_webdriver_common_keys

import cdp_ws
from kimi_parser import KimiChatMonitor, split_text_and_action


class _FakeCDP:
    def on_event(self, method, callback):
        pass


def test_connect_frame_roundtrip():
    obj = {"op": "append", "mask": "block.text.content",
           "block": {"id": "3", "text": {"content": u"\u043f\u0440\u0438\u0432\u0435\u0442"}}}
    frame = cdp_ws.encode_connect_frame(obj)
    decoded = cdp_ws.decode_connect_frames(frame)
    assert len(decoded) == 1, "expected exactly one decoded frame"
    flags, out_obj = decoded[0]
    assert flags == 0
    assert out_obj == obj, "round-tripped object must equal the original"


def test_connect_frame_multi_and_truncated():
    obj1 = {"op": "set", "mask": "block.text", "block": {"id": "1", "text": {"content": "a"}}}
    obj2 = {"op": "append", "mask": "block.text.content", "block": {"id": "1", "text": {"content": "b"}}}
    raw = cdp_ws.encode_connect_frame(obj1) + cdp_ws.encode_connect_frame(obj2)
    decoded = cdp_ws.decode_connect_frames(raw)
    assert [o for _f, o in decoded] == [obj1, obj2]
    # A truncated trailing frame must be dropped, not raise.
    decoded2 = cdp_ws.decode_connect_frames(raw + b"\x00\x00\x00\x00\xff")
    assert [o for _f, o in decoded2] == [obj1, obj2]


def test_block_assembly_matches_real_capture():
    with open("/data/qwen_repro/chat_code_objs.pkl", "rb") as f:
        objs = pickle.load(f)
    monitor = KimiChatMonitor(_FakeCDP())
    for obj in objs:
        if isinstance(obj, dict):
            monitor._apply_event(obj)
    text = monitor.current_text()
    assert "```agent_action" in text, "expected the agent_action fence in assembled text"
    assert "===DONE===" in text, "expected the ===DONE=== marker in assembled text"
    assert '"action": "read_file"' in text, "expected the read_file action JSON in assembled text"
    assert monitor.message_status() == "MESSAGE_STATUS_COMPLETED"
    assert monitor.assistant_message_count() == 1
    return text


def test_split_text_and_action():
    text = test_block_assembly_matches_real_capture()
    clean_text, action_raw = split_text_and_action(text)
    assert "===DONE===" not in clean_text
    assert "```agent_action" not in clean_text
    assert action_raw is not None
    assert '"action": "read_file"' in action_raw
    assert "project.godot" in action_raw


def test_split_text_and_action_no_fence():
    clean_text, action_raw = split_text_and_action("just a plain answer, nothing else")
    assert action_raw is None
    assert clean_text == "just a plain answer, nothing else"


class _FakeElement:
    """имитирует selenium WebElement - Не число, чтобы range(el) падал, если
    el случайно подставится как retries в _safe_execute (реальная ошибка v87.2,
    текст "'WebElement' object cannot be interpreted as an integer")."""
    pass


class _FakeDriverConfirmSent:
    """требует, что el был реально передан в execute_script как аргумент, а не
    съеден позиционным аргументом _safe_execute (баг v87.2)."""

    def execute_script(self, script, *args):
        assert "arguments[0]" in script
        assert len(args) == 1 and isinstance(args[0], _FakeElement)
        return ""


def test_confirm_sent_forwards_element_not_swallowed_by_retries():
    # v87.2 regression: confirm_sent must NOT pass el positionally into
    # _safe_execute (whose 3rd positional arg is retries, an int) - that
    # caused range(el) -> "'WebElement' object cannot be interpreted as an
    # integer". confirm_sent must call driver.execute_script(script, el)
    # directly instead.
    from kimi_parser import PARSER
    driver = _FakeDriverConfirmSent()
    el = _FakeElement()
    result = PARSER.confirm_sent(driver, el)
    assert result is True, "empty input field after send must be reported as sent"


class _FakeCDPReadLoopDeadlockCheck:
    """имитирует тот самый однопоточный read_loop из cdp_ws.CDPSession:
    send_command блокируется, пока "read_loop" (здесь - главный поток теста) не
    вызовет _deliver(). Если confirm_sent/_on_loading_finished вызовет send_command
    синхронно из того же потока, где быдет вызван _deliver — получимся истинный
    дедлок (timeout).
    """

    def __init__(self, response_body):
        self._response_body = response_body
        self._delivered = threading.Event()

    def on_event(self, method, callback):
        pass

    def _deliver(self):
        # играет роль "чтение ответа из сокета" - приходит только снаружи,
        # через короткую задержку, и только если вызывается в отдельном потоке.
        time.sleep(0.05)
        self._delivered.set()

    def send_command(self, method, params=None, timeout=2.0):
        if threading.current_thread() is threading.main_thread():
            # вызов из "read_loop" (тест играет read_loop в main thread) -
            # ��икто не вызовет _deliver извне, так что это неизбежно истечёт таймаут.
            if not self._delivered.wait(timeout):
                raise Exception("Timed out waiting for CDP response to %s" % method)
        else:
            self._deliver()
        return self._response_body


def test_on_loading_finished_does_not_deadlock_the_read_loop():
    # v87.4 regression: реальный CDPSession._read_loop вызывает
    # обработчики событий СиНхронно внутри себя (cb(params)). Старый
    # _on_loading_finished вызывал self._cdp.send_command(...) НАПАСРФСУ в
    # этом обработчике - т.е. блокировал read_loop, а ответ мог прийти
    # только через тот же read_loop - гарантированный таймаут каждый раз
    # (реальная ошибка пользователя 2026-07-22, v87.4). Исправление: тело
    # запроса читается в отдельном потоке, чтобы read_loop оставался свободным.
    from cdp_ws import encode_connect_frame
    from kimi_parser import KimiChatMonitor

    frame = encode_connect_frame({
        "op": "set", "mask": "block.text",
        "block": {"id": "1", "text": {"content": "Привет. Что нужно сделать?\n===DONE==="}}
    })
    import base64 as _b64
    fake_cdp = _FakeCDPReadLoopDeadlockCheck(
        {"body": _b64.b64encode(frame).decode("ascii"), "base64Encoded": True})
    monitor = KimiChatMonitor(fake_cdp)
    monitor._active_request_id = "req-1"
    monitor._generating = True

    started = time.time()
    monitor._on_loading_finished({"requestId": "req-1"})
    elapsed = time.time() - started
    assert elapsed < 0.5, (
        "_on_loading_finished must return almost immediately (fetch runs "
        "in a background thread) - it took %.2fs, looks like it is "
        "blocking the read loop again" % elapsed)

    deadline = time.time() + 2.0
    while time.time() < deadline and "===DONE===" not in monitor.current_text():
        time.sleep(0.02)
    assert "Привет" in monitor.current_text(), "background fetch never applied the frame"


class _FakeCDPBodyOnly:
    def __init__(self, response_body):
        self._response_body = response_body

    def on_event(self, method, callback):
        pass

    def send_command(self, method, params=None, timeout=2.0):
        return self._response_body


def test_on_loading_finished_recovers_from_bad_frame_decode():
    # v87.5 regression: до v87.5 всё, что после успешного send_command
    # (разбор base64/Connect-ка��ров/применение событий) было вне
    # try/except - при любой ошибке разбора (например невалидный base64)
    # исключение тихо гасило фоновый поток, а generating оставался True
    # навечно. Живой признак: лог без единой строки Ошибки
    # Network.getResponseBody, но answers=0/len=0/generating=True до самого
    # 900с TimeoutError (пользователь, 2026-07-22).
    from kimi_parser import KimiChatMonitor

    fake_cdp = _FakeCDPBodyOnly({"body": "---not-valid-base64!!!---", "base64Encoded": True})
    monitor = KimiChatMonitor(fake_cdp)
    monitor._active_request_id = "req-1"
    monitor._generating = True
    monitor._on_loading_finished({"requestId": "req-1"})

    deadline = time.time() + 1.0
    while time.time() < deadline and monitor.is_generating():
        time.sleep(0.02)
    assert not monitor.is_generating(), (
        "a decode error after a successful send_command must still reset "
        "generating - otherwise the whole pipeline hangs until the 900s "
        "timeout with zero diagnostic output")


def test_on_loading_finished_resets_generating_when_no_completion_seen():
    # v87.5 regression: Network.loadingFinished значит, что HTTP-ответ
    # получен ПОЛНОСтью - если в нём так и не пришло MESSAGE_STATUS_
    # COMPLETED (например сайт тихо оборвал запрос без какого-либо явного
    # сигнала завершения), generating всё равно должен сброситься -
    # больше данных по этому соединению всё равно не придёт.
    from cdp_ws import encode_connect_frame
    from kimi_parser import KimiChatMonitor
    import base64 as _b64

    # кадр с текстом, но без события завершения
    frame = encode_connect_frame({
        "op": "set", "mask": "block.text",
        "block": {"id": "1", "text": {"content": "...текст обрезан, соединение закрыто…"}}
    })
    fake_cdp = _FakeCDPBodyOnly(
        {"body": _b64.b64encode(frame).decode("ascii"), "base64Encoded": True})
    monitor = KimiChatMonitor(fake_cdp)
    monitor._active_request_id = "req-1"
    monitor._generating = True
    monitor._on_loading_finished({"requestId": "req-1"})

    deadline = time.time() + 1.0
    while time.time() < deadline and monitor.is_generating():
        time.sleep(0.02)
    assert not monitor.is_generating(), (
        "loadingFinished means no more data will ever arrive on this "
        "request - generating must not stay True forever just because no "
        "MESSAGE_STATUS_COMPLETED frame happened to appear in the body")
    assert "текст обрезан" in monitor.current_text()


def test_on_loading_finished_failure_does_not_hang_generating_forever():
    # v87.4: если Network.getResponseBody проваливается (таймаут/ошибка),
    # is_generating() Не должен оставаться True навечно (иначе wait_for_new_answer
    # висит всю отведенную на TIMEOUT (900с), хотя ответ давно готов на
    # странице).
    from kimi_parser import KimiChatMonitor

    class _FailingCDP:
        def on_event(self, method, callback):
            pass

        def send_command(self, method, params=None, timeout=2.0):
            raise Exception("Timed out waiting for CDP response to %s" % method)

    monitor = KimiChatMonitor(_FailingCDP())
    monitor._active_request_id = "req-1"
    monitor._generating = True
    monitor._on_loading_finished({"requestId": "req-1"})
    # _fetch_and_apply_body запущен в фоне - даём ему чуть времени отработать.
    deadline = time.time() + 1.0
    while time.time() < deadline and monitor.is_generating():
        time.sleep(0.02)
    assert not monitor.is_generating(), (
        "is_generating() must not stay stuck at True forever after a "
        "failed Network.getResponseBody - the whole wait_for_new_answer "
        "pipeline would hang until the 900s timeout otherwise")


class _RecordingCDP:
    """запоминает, какие CDP-команды вызывались."""

    def __init__(self):
        self.calls = []

    def on_event(self, method, callback):
        pass

    def send_command(self, method, params=None, timeout=2.0):
        self.calls.append(method)
        return {"body": "", "base64Encoded": False}


def test_stale_request_body_does_not_clobber_new_request():
    # v87.7 regression: пока тело СТАРОГО запроса шло к разбору, браузер уже
    # отправил НОВЫЙ POST (повтор confirm_sent). Старое тело нельзя ни
    # применять, ни сбрасывать им состояние нового запроса - иначе
    # loadingFinished НОВОГО запроса отбрасывался и настоящий ответ
    # никогда не читался (лог 2026-07-22: "кадров=1, длина_текста=0").
    from kimi_parser import KimiChatMonitor

    cdp = _RecordingCDP()
    monitor = KimiChatMonitor(cdp)
    monitor._active_request_id = "req-NEW"
    monitor._generating = True
    monitor._blocks = {"1": "текст нового ответа"}
    monitor._block_order = ["1"]

    monitor._fetch_and_apply_body("req-OLD")
    assert cdp.calls == [], (
        "тело устаревшего запроса не должно даже запрашиваться: %r" % cdp.calls)
    assert monitor._active_request_id == "req-NEW"
    assert monitor.is_generating()

    # завершение СТАРОГО запроса тоже не должно трогать состояние нового
    monitor._reset_after_finish("req-OLD", "тест")
    assert monitor._active_request_id == "req-NEW"
    assert monitor.is_generating()
    assert "текст нового ответа" in monitor.current_text()


class _StreamOnlyCDP:
    """v87.8: стрим включается, а getResponseBody НЕДОСТУПЕН - как в реальном
    Chrome, где тело стримингового ответа не хранится в буфере DevTools."""

    def __init__(self):
        self.body_calls = 0

    def on_event(self, method, callback):
        pass

    def send_command(self, method, params=None, timeout=2.0):
        if method == "Network.streamResourceContent":
            return {"bufferedData": ""}
        if method == "Network.getResponseBody":
            self.body_calls += 1
            raise Exception("стриминговое тело в буфере DevTools не хранится")
        return {}


def _start_stream_request(monitor, req_id="req-1"):
    monitor._on_response_received({
        "requestId": req_id,
        "response": {
            "url": "https://www.kimi.com/apiv2/kimi.chat.v1.ChatService/Chat",
            "mimeType": "application/connect+json",
        },
    })
    deadline = time.time() + 2.0
    while time.time() < deadline and not monitor._stream_mode.get(req_id):
        time.sleep(0.02)
    assert monitor._stream_mode.get(req_id), "живой стрим так и не включился"


def test_decode_connect_frames_partial_keeps_tail():
    # v87.8: инкрементный декодер для живого стрима: чанки режут
    # Connect-конверт посередине - неполный хвост НЕ выбрасывается
    # (в отличие от decode_connect_frames), а ждёт следующего чанка.
    obj1 = {"op": "set", "mask": "block.text", "block": {"id": "1", "text": {"content": "a"}}}
    obj2 = {"op": "append", "mask": "block.text.content", "block": {"id": "1", "text": {"content": "b"}}}
    f1 = cdp_ws.encode_connect_frame(obj1)
    f2 = cdp_ws.encode_connect_frame(obj2)
    raw = f1 + f2
    cut = len(f1) + 3  # второй конверт разрезан посередине

    frames, consumed = cdp_ws.decode_connect_frames_partial(raw[:cut])
    assert [o for _f, o in frames] == [obj1]
    assert consumed == len(f1), "неполный хвост не должен быть съеден"

    tail = raw[consumed:]
    frames2, consumed2 = cdp_ws.decode_connect_frames_partial(tail)
    assert [o for _f, o in frames2] == [obj2]
    assert consumed2 == len(f2)


def test_streaming_body_captured_live():
    # v87.8: тело стримингового ответа собирается ЖИВЬЁМ из
    # Network.dataReceived; getResponseBody (буфер DevTools) не нужен вовсе.
    import base64 as _b64
    from cdp_ws import encode_connect_frame
    from kimi_parser import KimiChatMonitor

    cdp = _StreamOnlyCDP()
    monitor = KimiChatMonitor(cdp)
    _start_stream_request(monitor)

    raw = (
        encode_connect_frame({"op": "set", "mask": "message",
                              "message": {"id": "m1", "role": "assistant",
                                          "status": "MESSAGE_STATUS_GENERATING"}})
        + encode_connect_frame({"op": "set", "mask": "block.text",
                                "block": {"id": "1", "text": {"content": "Привет из живого стрима"}}})
        + encode_connect_frame({"op": "set", "mask": "message.status",
                                "message": {"id": "m1", "status": "MESSAGE_STATUS_COMPLETED"}})
    )
    cut = len(raw) // 2  # чанки режут Connect-конверт произвольно
    for chunk in (raw[:cut], raw[cut:]):
        monitor._on_data_received({"requestId": "req-1",
                                   "data": _b64.b64encode(chunk).decode("ascii")})

    assert "Привет из живого стрима" in monitor.current_text(), (
        "текст должен собираться живьём из dataReceived, ДО loadingFinished")
    assert monitor.message_status() == "MESSAGE_STATUS_COMPLETED"

    monitor._on_loading_finished({"requestId": "req-1"})
    deadline = time.time() + 2.0
    while time.time() < deadline and monitor.is_generating():
        time.sleep(0.02)
    assert not monitor.is_generating()
    assert cdp.body_calls == 0, "getResponseBody не должен вызываться при живом стриме"


def test_generating_resets_when_stream_truncated_at_generating():
    # v87.7/v87.8: соединение закрылось, а ПОСЛЕДНИЙ увиденный статус -
    # MESSAGE_STATUS_GENERATING (COMPLETED так и не пришёл, обрыв). generating
    # обязан сброситься: данных по этому запросу больше не будет,
    # иначе ожидание висит до полного 900с таймаута.
    import base64 as _b64
    from cdp_ws import encode_connect_frame
    from kimi_parser import KimiChatMonitor

    cdp = _StreamOnlyCDP()
    monitor = KimiChatMonitor(cdp)
    _start_stream_request(monitor)

    raw = (
        encode_connect_frame({"op": "set", "mask": "message",
                              "message": {"id": "m1", "role": "assistant",
                                          "status": "MESSAGE_STATUS_GENERATING"}})
        + encode_connect_frame({"op": "set", "mask": "block.text",
                                "block": {"id": "1", "text": {"content": "текст обрезан на полусл"}}})
    )
    monitor._on_data_received({"requestId": "req-1",
                               "data": _b64.b64encode(raw).decode("ascii")})
    assert monitor.is_generating()

    monitor._on_loading_finished({"requestId": "req-1"})
    deadline = time.time() + 2.0
    while time.time() < deadline and monitor.is_generating():
        time.sleep(0.02)
    assert not monitor.is_generating(), (
        "обрыв стрима на статусе GENERATING не должен оставлять generating=True навечно")
    assert "текст обрезан" in monitor.current_text()


def test_read_loop_survives_socket_silence():
    # v87.7: после хендшейка таймаут сокета СНИМАЕТСЯ (settimeout(None)) -
    # иначе любые 10с ТИШИНЫ в CDP-событиях (модель думает, пользователь
    # читает) роняли recv() по socket.timeout и read_loop МОЛЧА умирал -
    # монитор навсегда глох, все send_command ловили таймауты.
    import cdp_ws as _c

    class _FakeSock:
        def __init__(self):
            self.timeouts = []

        def settimeout(self, value):
            self.timeouts.append(value)

        def sendall(self, data):
            pass

        def close(self):
            pass

    fake = _FakeSock()
    orig_create = _c.socket.create_connection
    orig_handshake = _c._ws_handshake
    _c.socket.create_connection = lambda addr, timeout=None: fake
    _c._ws_handshake = lambda sock, hostport, path: b""
    try:
        ws = _c.MiniWebSocket("ws://127.0.0.1:9222/devtools/page/x", timeout=10.0)
    finally:
        _c.socket.create_connection = orig_create
        _c._ws_handshake = orig_handshake
    assert ws._sock is fake
    assert fake.timeouts and fake.timeouts[-1] is None, (
        "после хендшейка таймаут сокета должен быть снят (settimeout(None)), "
        "иначе тишина дольше таймаута убивает read_loop: %r" % (fake.timeouts,))


def test_confirm_sent_treats_new_chat_post_as_sent():
    # v87.7: главный критерий «ушло» - СЕТЬ: если после клика появился новый
    # POST к ChatService/Chat, сообщение отправлено, даже если сайт ещё не
    # очистил поле ввода (ложные «не ушло» порождали дубли POST,
    # обрывавшие чтение настоящего ответа).
    from kimi_parser import KimiParser, PARSER

    class _MonStub:
        def chat_request_count(self):
            return 1  # вырос относительно снимка до отправки (0)

    class _DriverLeftover:
        def execute_script(self, script, *args):
            return "текст всё ещё в поле ввода"  # DOM говорит «не ушло»

    old_mon = KimiParser._monitor
    KimiParser._monitor = _MonStub()
    try:
        PARSER._req_count_before_send = 0
        started = time.time()
        result = PARSER.confirm_sent(_DriverLeftover(), _FakeElement())
        elapsed = time.time() - started
    finally:
        KimiParser._monitor = old_mon
    assert result is True, "новый POST в сети = сообщение ушло, даже при непустом поле ввода"
    assert elapsed < 1.0, "ответ должен быть мгновенным, без 5-секундного ожидания DOM"


def _run_all():
    tests = [
        test_connect_frame_roundtrip,
        test_connect_frame_multi_and_truncated,
        test_block_assembly_matches_real_capture,
        test_split_text_and_action,
        test_split_text_and_action_no_fence,
        test_confirm_sent_forwards_element_not_swallowed_by_retries,
        test_on_loading_finished_does_not_deadlock_the_read_loop,
        test_on_loading_finished_failure_does_not_hang_generating_forever,
        test_on_loading_finished_recovers_from_bad_frame_decode,
        test_on_loading_finished_resets_generating_when_no_completion_seen,
        test_stale_request_body_does_not_clobber_new_request,
        test_generating_resets_when_stream_truncated_at_generating,
        test_read_loop_survives_socket_silence,
        test_confirm_sent_treats_new_chat_post_as_sent,
        test_decode_connect_frames_partial_keeps_tail,
        test_streaming_body_captured_live,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as e:
            failed += 1
            print("FAIL", t.__name__, "->", e)
    if failed:
        print("%d test(s) FAILED" % failed)
        sys.exit(1)
    print("All v87.1 tests passed.")


if __name__ == "__main__":
    _run_all()
