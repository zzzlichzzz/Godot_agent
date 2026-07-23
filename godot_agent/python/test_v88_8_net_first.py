# -*- coding: utf-8 -*-
"""Тесты v88.8: сеть — ОСНОВНОЙ источник ответа для qwen (как у kimi):
если стрим /api/v2/chat/completions завершён — ответ берётся из захвата
сразу, без медленного DOM-чтения (тишина 4 с, перехват Copy, высота блока).
"""
import sys
import traceback
import types


def _install_selenium_stub():
    if "selenium" in sys.modules:
        return
    selenium = types.ModuleType("selenium")
    webdriver = types.ModuleType("selenium.webdriver")
    common = types.ModuleType("selenium.webdriver.common")
    keys_mod = types.ModuleType("selenium.webdriver.common.keys")
    sel_common = types.ModuleType("selenium.common")
    exceptions = types.ModuleType("selenium.common.exceptions")

    class _Keys(object):
        ENTER = u"\ue007"
        CONTROL = u"\ue009"
        SPACE = u" "
        BACKSPACE = u"\ue003"

    keys_mod.Keys = _Keys
    for name in ("WebDriverException", "JavascriptException",
                 "StaleElementReferenceException", "NoSuchWindowException",
                 "TimeoutException"):
        setattr(exceptions, name, type(name, (Exception,), {}))
    sel_common.exceptions = exceptions
    selenium.webdriver = webdriver
    selenium.common = sel_common
    sys.modules.setdefault("selenium", selenium)
    sys.modules.setdefault("selenium.webdriver", webdriver)
    sys.modules.setdefault("selenium.webdriver.common", common)
    sys.modules.setdefault("selenium.webdriver.common.keys", keys_mod)
    sys.modules.setdefault("selenium.common", sel_common)
    sys.modules.setdefault("selenium.common.exceptions", exceptions)


_install_selenium_stub()
import qwen_parser  # noqa: E402
from qwen_parser import QwenParser  # noqa: E402

_NET_TEXT = (u"Перечитываю сцену, чтобы учесть актуальные изменения вне диалога."
             u"\n\n```agent_action\n"
             u'{"action": "read_file", "paths": ["res://src/scenes/cs2_game.tscn"],'
             u' "reason": "Получить актуальное содержимое"}'
             u"\n```\n===DONE===")


class _FakeCdp(object):
    def is_alive(self):
        return True


class _FakeMonitor(object):
    def __init__(self, text=_NET_TEXT, finished=True, req_count=1,
                 answer_req_count=None):
        self._text = text
        self._finished = finished
        self._req_count = req_count
        # v88.10: номер POST, чей ответ лежит в буфере (по умолчанию —
        # как req_count: ответ на последний POST уже пришёл)
        self._answer_req_count = (req_count if answer_req_count is None
                                  else answer_req_count)
        self._cdp = _FakeCdp()

    def current_text(self):
        return self._text

    def is_finished(self):
        return self._finished

    def chat_request_count(self):
        return self._req_count

    def answer_request_count(self):
        return self._answer_req_count

    def assistant_message_count(self):
        return 1


class _NoDomDriver(object):
    """Любое обращение к DOM = провал теста быстрого пути."""

    def execute_script(self, *a, **k):
        raise AssertionError(u"быстрый путь не должен трогать DOM")


def _fresh_parser(mon, before):
    p = QwenParser()
    QwenParser._monitor = mon
    QwenParser._monitor_next_retry = 0.0
    QwenParser._req_count_before_send = before
    return p


def test_net_first_skips_dom():
    p = _fresh_parser(_FakeMonitor(req_count=1), before=0)
    res = p.extract_answer(_NoDomDriver())
    assert res["error"] is None
    assert res["actionRaw"] and u'"read_file"' in res["actionRaw"], res
    assert res["text"].startswith(u"Перечитываю"), res
    assert u"===DONE===" not in res["text"]


def test_net_first_requires_new_post():
    # после submit НЕ ушёл новый POST -> текст в мониторе устаревший,
    # быстрый путь обязан уступить DOM-пути (здесь — AssertionError от DOM)
    p = _fresh_parser(_FakeMonitor(req_count=1), before=1)
    try:
        p.extract_answer(_NoDomDriver())
    except AssertionError as e:
        assert u"DOM" in str(e)
    else:
        raise AssertionError(u"устаревший сетевой текст не должен возвращаться")


def test_net_first_requires_finished():
    p = _fresh_parser(_FakeMonitor(finished=False, req_count=2), before=1)
    try:
        p.extract_answer(_NoDomDriver())
    except AssertionError as e:
        assert u"DOM" in str(e)
    else:
        raise AssertionError(u"незавершённый стрим не должен браться как готовый ответ")


def test_net_first_incomplete_action_falls_back():
    # в сетевом тексте есть ссылки на метки без тел — быстрый путь обязан
    # отказаться и передать дело DOM-пути (здесь — AssertionError от DOM)
    bad = (u"Текст\n\n```agent_action\n"
           u'{"action": "write_file", "path": "res://a.gd", "content_ref": "REF1"}'
           u"\n```\n")
    p = _fresh_parser(_FakeMonitor(text=bad, req_count=2), before=1)
    try:
        p.extract_answer(_NoDomDriver())
    except AssertionError as e:
        assert u"DOM" in str(e)
    else:
        raise AssertionError(u"неполное действие не должно проходить быстрым путём")


class _StaticDomDriver(object):
    """DOM всегда отвечает одной строкой — чтобы отличить источник."""

    def execute_script(self, *a, **k):
        return u"DOM_TEXT"


def test_live_stream_prefers_net():
    # v88.9: живая трансляция (answer_stream/preview/len) берётся из сети,
    # как у kimi — DOM не трогается вообще (иначе _NoDomDriver уронит тест)
    p = _fresh_parser(_FakeMonitor(req_count=1), before=0)
    drv = _NoDomDriver()
    assert p.answer_stream(drv) == _NET_TEXT
    assert p.answer_preview(drv) == _NET_TEXT[-160:]
    assert p.answer_len(drv) == len(_NET_TEXT)


def test_live_stream_stale_falls_back_to_dom():
    # новый POST после submit ещё не ушёл — сетево�� текст устаревший,
    # живая трансляция обязана читать DOM (защита от прошлого ответа)
    p = _fresh_parser(_FakeMonitor(req_count=1), before=1)
    drv = _StaticDomDriver()
    assert p.answer_stream(drv) == u"DOM_TEXT"
    assert p.answer_preview(drv) == u"DOM_TEXT"


def test_live_stream_empty_net_falls_back_to_dom():
    # POST ушёл, но токенов ещё нет — пустая сеть не должна затирать DOM
    p = _fresh_parser(_FakeMonitor(text=u"", req_count=1), before=0)
    drv = _StaticDomDriver()
    assert p.answer_stream(drv) == u"DOM_TEXT"


def test_stale_window_live_shows_no_old_text():
    # v88.10: POST уже ушёл (count=2 > before=1), но ответ ещё не пришёл —
    # в буфере ПРОШЛЫЙ ответ (answer_request_count=1). Именно это окно
    # дублировало старый текст в панели «печатает…».
    p = _fresh_parser(
        _FakeMonitor(req_count=2, answer_req_count=1), before=1)
    drv = _StaticDomDriver()
    assert p.answer_stream(drv) == u"DOM_TEXT"
    assert p.answer_preview(drv) == u"DOM_TEXT"


def test_stale_window_extract_falls_back_to_dom():
    # то же окно для быстрого пути извлечения: старый finished-буфер
    # не должен вернуться как НОВЫЙ ответ (уступаем DOM-пути)
    p = _fresh_parser(
        _FakeMonitor(req_count=2, answer_req_count=1), before=1)
    try:
        p.extract_answer(_NoDomDriver())
    except AssertionError as e:
        assert u"DOM" in str(e)
    else:
        raise AssertionError(u"старый буфер не должен считаться новым ответом")


class _FakeCdpFull(object):
    """CDP-заглушка для прямого теста QwenChatMonitor."""

    def __init__(self):
        self.handlers = {}

    def on_event(self, name, fn):
        self.handlers[name] = fn

    def send_command(self, name, params=None):
        return {}

    def is_alive(self):
        return True


def test_monitor_buffer_binds_to_post():
    # v88.10: answer_request_count меняется только вместе со сбросом
    # буфера (responseReceived), а не при отправке POST
    import qwen_net
    url = u"https://chat.qwen.ai/api/v2/chat/completions?chat_id=x"
    mon = qwen_net.QwenChatMonitor(_FakeCdpFull())
    mon._on_response_received(
        {"requestId": "r1",
         "response": {"url": url, "mimeType": "text/event-stream"}})
    with mon._lock:
        mon._answer_text = u"старый ответ"
    mon._on_request_will_be_sent(
        {"requestId": "r2", "request": {"url": url, "method": "POST"}})
    assert mon.chat_request_count() == 1
    assert mon.answer_request_count() == 0  # буфер ещё от прошлого ответа
    assert mon.current_text() == u"старый ответ"
    mon._on_response_received(
        {"requestId": "r2",
         "response": {"url": url, "mimeType": "text/event-stream"}})
    assert mon.answer_request_count() == 1  # теперь буфер — нового POST
    assert mon.current_text() == u""  # и он пуст, старый текст не утечёт


def test_module_loop_gate_accepts_net_done():
    # v88.8: в цикле докачки фолбэк разрешён и при still_generating=True,
    # если сеть уже FINISHED — проверяем по исходнику, что ворота на месте
    import inspect
    src = inspect.getsource(qwen_parser.extract_answer)
    assert "net_finished_fn" in src
    assert "not still_generating or net_done" in src


def _run_all():
    tests = [
        test_net_first_skips_dom,
        test_net_first_requires_new_post,
        test_net_first_requires_finished,
        test_net_first_incomplete_action_falls_back,
        test_live_stream_prefers_net,
        test_live_stream_stale_falls_back_to_dom,
        test_live_stream_empty_net_falls_back_to_dom,
        test_stale_window_live_shows_no_old_text,
        test_stale_window_extract_falls_back_to_dom,
        test_monitor_buffer_binds_to_post,
        test_module_loop_gate_accepts_net_done,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("OK   %s" % fn.__name__)
        except Exception as e:
            failed += 1
            print("FAIL %s -> %r" % (fn.__name__, e))
            traceback.print_exc()
    QwenParser._monitor = None
    QwenParser._req_count_before_send = None
    if failed:
        print("%d FAILED" % failed)
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    _run_all()
