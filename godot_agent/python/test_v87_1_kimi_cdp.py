# -*- coding: utf-8 -*-
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

sys.path.insert(0, "/data/godot_agent_v86/godot_agent_update/python")

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
        # v87.8: фейк имитирует СТАРЫЙ Chrome без Network.streamResourceContent -
        # тест проверяет запасной путь через getResponseBody.
        if method == "Network.streamResourceContent":
            raise Exception("'Network.streamResourceContent' wasn't found")
        if threading.current_thread() is threading.main_thread():
            # вызов из "read_loop" (тест играет read_loop в main thread) -
            # никто не вызовет _deliver извне, так что это неизбежно истечёт таймаут.
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
        # v87.8: имитация старого Chrome - только getResponseBody.
        if method == "Network.streamResourceContent":
            raise Exception("'Network.streamResourceContent' wasn't found")
        return self._response_body


def test_on_loading_finished_recovers_from_bad_frame_decode():
    # v87.5 regression: до v87.5 всё, что после успешного send_command
    # (разбор base64/Connect-к����ров/применение событий) было вне
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


# ---------------------------------------------------------------------------
# v87.7 regressions: гонки отставших тел, тишина на сокете, confirm_sent по сети
# ---------------------------------------------------------------------------

class _FakeCDPWithBodies:
    """Старый Chrome: только getResponseBody (с настраиваемыми задержками),
    живого стрима нет - тесты проверяют запасной путь."""

    def __init__(self, bodies, delays=None):
        self._handlers = {}
        self._bodies = bodies
        self._delays = delays or {}

    def on_event(self, method, cb):
        self._handlers.setdefault(method, []).append(cb)

    def emit(self, method, params):
        for cb in self._handlers.get(method, []):
            cb(params)

    def send_command(self, method, params=None, timeout=2.0):
        import base64 as _b64
        if method == "Network.streamResourceContent":
            raise Exception("'Network.streamResourceContent' wasn't found")
        if method == "Network.getResponseBody":
            req_id = (params or {}).get("requestId")
            time.sleep(self._delays.get(req_id, 0))
            raw = self._bodies[req_id]
            return {"body": _b64.b64encode(raw).decode("ascii"),
                    "base64Encoded": True}
        return {}


def _kimi_frames(*objs):
    return b"".join(cdp_ws.encode_connect_frame(o) for o in objs)


def _kimi_resp_params(req_id):
    return {
        "requestId": req_id,
        "response": {
            "url": "https://www.kimi.com/api/kimi.chat.v1.ChatService/Chat",
            "mimeType": "application/connect+json",
        },
    }


def test_stale_request_body_does_not_clobber_new_request():
    # v87.7: отставшее тело СТАРОГО запроса (медленный getResponseBody)
    # не должно затирать состояние уже активного НОВОГО запроса.
    old_body = _kimi_frames(
        {"op": "set", "mask": "message",
         "message": {"id": "m1", "role": "assistant",
                     "status": "MESSAGE_STATUS_GENERATING"}},
        {"op": "set", "mask": "block.text",
         "block": {"id": "1", "text": {"content": "СТАРЫЙ ответ"}}})
    new_body = _kimi_frames(
        {"op": "set", "mask": "message",
         "message": {"id": "m2", "role": "assistant",
                     "status": "MESSAGE_STATUS_GENERATING"}},
        {"op": "set", "mask": "block.text",
         "block": {"id": "1", "text": {"content": "НОВЫЙ ответ"}}},
        {"op": "set", "mask": "message.status",
         "message": {"id": "m2", "status": "MESSAGE_STATUS_COMPLETED"}})
    cdp = _FakeCDPWithBodies({"req-1": old_body, "req-2": new_body},
                             delays={"req-1": 0.5})
    mon = KimiChatMonitor(cdp)
    cdp.emit("Network.responseReceived", _kimi_resp_params("req-1"))
    cdp.emit("Network.loadingFinished", {"requestId": "req-1"})
    time.sleep(0.1)
    # пока тело req-1 ещё скачивается, приходит новый запрос
    cdp.emit("Network.responseReceived", _kimi_resp_params("req-2"))
    cdp.emit("Network.loadingFinished", {"requestId": "req-2"})
    deadline = time.time() + 3.0
    while time.time() < deadline and "НОВЫЙ" not in mon.current_text():
        time.sleep(0.02)
    time.sleep(0.7)  # даём отставшему телу req-1 шанс всё испортить
    assert "НОВЫЙ ответ" in mon.current_text(), mon.current_text()
    assert "СТАРЫЙ" not in mon.current_text(), (
        "отставшее тело старого запроса затёрло новый: %r"
        % mon.current_text())
    assert not mon.is_generating()


def test_generating_resets_when_stream_truncated_at_generating():
    # v87.7: если ответ оборвался на MESSAGE_STATUS_GENERATING (без
    # COMPLETED), после loadingFinished generating всё равно должен
    # сброситься - больше данных по этому соединению не придёт.
    body = _kimi_frames(
        {"op": "set", "mask": "message",
         "message": {"id": "m1", "role": "assistant",
                     "status": "MESSAGE_STATUS_GENERATING"}},
        {"op": "set", "mask": "block.text",
         "block": {"id": "1", "text": {"content": "оборванный текст"}}})
    cdp = _FakeCDPWithBodies({"req-1": body})
    mon = KimiChatMonitor(cdp)
    cdp.emit("Network.responseReceived", _kimi_resp_params("req-1"))
    cdp.emit("Network.loadingFinished", {"requestId": "req-1"})
    deadline = time.time() + 2.0
    while time.time() < deadline and mon.is_generating():
        time.sleep(0.02)
    assert not mon.is_generating(), (
        "generating обязан сброситься после loadingFinished даже без "
        "MESSAGE_STATUS_COMPLETED")
    assert "оборванный текст" in mon.current_text()


def test_read_loop_survives_socket_silence():
    # v87.7 (BUG 1): MiniWebSocket оставлял 10с таймаут на сокете и
    # _read_loop умирал на первой же паузе длиннее таймаута. Здесь
    # реальный WS-сервер молчит ДОЛЬШЕ таймаута (1.6с > 1.0с) и только
    # потом шлёт событие - сессия обязана дожить и принять его.
    import base64 as _b64
    import hashlib
    import json as _json
    import socket

    def _serve(srv):
        conn, _ = srv.accept()
        data = b""
        while b"\r\n\r\n" not in data:
            data += conn.recv(4096)
        key = ""
        for line in data.decode("latin-1").split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
        accept = _b64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
        ).digest()).decode("ascii")
        conn.sendall(("HTTP/1.1 101 Switching Protocols\r\n"
                      "Upgrade: websocket\r\n"
                      "Connection: Upgrade\r\n"
                      "Sec-WebSocket-Accept: %s\r\n\r\n" % accept)
                     .encode("ascii"))
        time.sleep(1.6)  # тишина длиннее таймаута сокета (1.0с)
        payload = _json.dumps({"method": "Test.ping", "params": {}})\
            .encode("utf-8")
        conn.sendall(b"\x81" + bytes([len(payload)]) + payload)
        time.sleep(1.0)
        try:
            conn.close()
        except Exception:
            pass

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    threading.Thread(target=_serve, args=(srv,), daemon=True).start()
    sess = cdp_ws.CDPSession("ws://127.0.0.1:%d/devtools" % port, timeout=1.0)
    got = threading.Event()
    sess.on_event("Test.ping", lambda p: got.set())
    assert got.wait(4.0), (
        "read loop умер на тишине сокета - событие после паузы не принято")
    assert sess.is_alive(), "сессия должна быть жива после паузы без данных"
    try:
        sess.close()
    except Exception:
        pass


class _FakeDriverLeftoverText:
    """Поле ввода НЕ очистилось (сайт медленный) - до v87.7 это давало
    ложное «не ушло» и реальный повторный POST."""

    def execute_script(self, script, *args):
        if "innerText" in script:
            return "текст, который сайт ещё не очистил"
        return None


class _FakeMonitorCounter:
    def __init__(self, count):
        self._count = count

    def chat_request_count(self):
        return self._count


def test_confirm_sent_treats_new_chat_post_as_sent():
    # v87.7 (BUG 2): главный критерий «ушло» - СЕТЬ: новый POST к
    # ChatService/Chat после клика => отправлено, даже если поле ввода
    # ещё не очистилось (ложные «не ушло» порождали дубли POST,
    # обрывавшие чтение настоящего ответа - лог 2026-07-22).
    from kimi_parser import KimiParser
    parser = KimiParser()
    old_monitor = KimiParser._monitor
    try:
        KimiParser._monitor = _FakeMonitorCounter(1)
        parser._req_count_before_send = 0  # до клика было 0, стало 1
        t0 = time.time()
        ok = parser.confirm_sent(_FakeDriverLeftoverText(), object())
        elapsed = time.time() - t0
    finally:
        KimiParser._monitor = old_monitor
    assert ok is True, (
        "новый POST в сети обязан считаться подтверждением отправки, "
        "даже если поле ввода не очистилось")
    assert elapsed < 2.0, "при видимом POST ответ должен быть быстрым, без 5с опроса"


# ---------------------------------------------------------------------------
# v87.8 regressions: живой стрим тела (streamResourceContent/dataReceived)
# ---------------------------------------------------------------------------

def test_decode_connect_frames_partial_keeps_tail():
    # v87.8: чанки dataReceived режут Connect-конверты посередине - декодер
    # обязан вернуть полные кадры и НЕ потерять неполный хвост.
    f1 = cdp_ws.encode_connect_frame({"a": 1})
    f2 = cdp_ws.encode_connect_frame({"b": 2})
    blob = f1 + f2
    cut = len(f1) + 3  # второй кадр обрезан посередине
    frames1, consumed1 = cdp_ws.decode_connect_frames_partial(blob[:cut])
    assert len(frames1) == 1 and frames1[0][1] == {"a": 1}
    assert consumed1 == len(f1), "неполный хвост должен остаться в буфере"
    frames2, consumed2 = cdp_ws.decode_connect_frames_partial(blob[consumed1:])
    assert len(frames2) == 1 and frames2[0][1] == {"b": 2}
    assert consumed2 == len(f2)


class _FakeCDPStreamingChrome:
    """v87.8: имитация НОВОГО Chrome: streamResourceContent работает, а
    getResponseBody для стримингового тела данных НЕ возвращает (как в
    реальности: тело, прочитанное страницей через ReadableStream, в буфере
    DevTools не хранится; живой лог 2026-07-22: кадров=1, длина_текста=0
    при ответе, видимом в чате)."""

    def __init__(self, buffered=b""):
        self._handlers = {}
        self._buffered = buffered
        self.get_body_called = False

    def on_event(self, method, cb):
        self._handlers.setdefault(method, []).append(cb)

    def emit(self, method, params):
        for cb in self._handlers.get(method, []):
            cb(params)

    def emit_chunk(self, req_id, raw):
        import base64 as _b64
        self.emit("Network.dataReceived", {
            "requestId": req_id,
            "dataLength": len(raw),
            "encodedDataLength": len(raw),
            "data": _b64.b64encode(raw).decode("ascii"),
        })

    def send_command(self, method, params=None, timeout=2.0):
        import base64 as _b64
        if method == "Network.streamResourceContent":
            return {"bufferedData":
                    _b64.b64encode(self._buffered).decode("ascii")}
        if method == "Network.getResponseBody":
            self.get_body_called = True
            return {"body": "", "base64Encoded": False}
        return {}


def test_streaming_body_captured_live():
    # v87.8: главный сценарий нового Chrome - тело читается ЖИВЫМ стримом
    # (bufferedData + чанки dataReceived, в т.ч. с разрезом кадра посередине),
    # getResponseBody вообще не вызывается.
    first = cdp_ws.encode_connect_frame(
        {"op": "set", "mask": "message",
         "message": {"id": "m1", "role": "assistant",
                     "status": "MESSAGE_STATUS_GENERATING"}})
    text_frame = cdp_ws.encode_connect_frame(
        {"op": "set", "mask": "block.text",
         "block": {"id": "1", "text": {"content": "Привет. Готов к работе."}}})
    done = cdp_ws.encode_connect_frame(
        {"op": "set", "mask": "message.status",
         "message": {"id": "m1", "status": "MESSAGE_STATUS_COMPLETED"}})
    cdp = _FakeCDPStreamingChrome(buffered=first)
    mon = KimiChatMonitor(cdp)
    cdp.emit("Network.responseReceived", _kimi_resp_params("req-1"))
    time.sleep(0.3)  # даём потоку _enable_stream включить стрим
    cut = len(text_frame) // 2
    cdp.emit_chunk("req-1", text_frame[:cut])  # кадр разрезан посередине
    assert mon.is_generating() is True
    cdp.emit_chunk("req-1", text_frame[cut:] + done)
    assert "Привет. Готов к работе." in mon.current_text(), (
        "текст должен собираться live по чанкам, ещё до loadingFinished")
    cdp.emit("Network.loadingFinished", {"requestId": "req-1"})
    deadline = time.time() + 2.0
    while time.time() < deadline and mon.is_generating():
        time.sleep(0.02)
    assert mon.is_generating() is False
    assert mon.message_status() == "MESSAGE_STATUS_COMPLETED"
    assert mon.assistant_message_count() == 1
    assert "Привет. Готов к работе." in mon.current_text()
    assert cdp.get_body_called is False, (
        "при работающем живом стриме getResponseBody вызываться не должен")


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
