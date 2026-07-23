# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v88.11/v88.14: живой ввод — зеркалирование текста из панели в поле сайта.

v88.14: mirror_input набирает текст КЛАВИШАМИ (send_keys), не через insert_input.
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
        A = u"a"

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

import live_input  # noqa: E402
import parser_base  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402


class _FakeParser(object):
    def __init__(self, ok=True, raise_exc=None):
        self.calls = []
        self.ok = ok
        self.raise_exc = raise_exc

    def mirror_input(self, driver, text, prefer_url=None):
        if self.raise_exc is not None:
            raise self.raise_exc
        self.calls.append((text, prefer_url))
        return self.ok


def _mk(parser=None, driver="drv", busy=False, prefer_url=None):
    p = parser if parser is not None else _FakeParser()
    m = live_input.LiveInputMirror(
        get_driver=lambda: driver,
        get_parser=lambda: p,
        busy_fn=lambda: busy,
        prefer_url_fn=(lambda: prefer_url))
    return m, p


def test_applies_text():
    m, p = _mk(prefer_url="https://site/chat/1")
    r = m.apply(1, u"прив")
    assert r["ok"] and r["applied"], r
    assert p.calls == [(u"прив", "https://site/chat/1")], p.calls
    r2 = m.apply(2, u"привет")
    assert r2["applied"], r2
    assert p.calls[-1][0] == u"привет"


def test_stale_seq_skipped():
    m, p = _mk()
    assert m.apply(5, u"новый")["applied"]
    r = m.apply(3, u"старый")
    assert not r["applied"] and r["reason"] == "stale_seq", r
    assert len(p.calls) == 1


def test_same_text_skipped():
    m, p = _mk()
    assert m.apply(1, u"текст")["applied"]
    r = m.apply(2, u"текст")
    assert not r["applied"] and r["reason"] == "same_text", r
    assert len(p.calls) == 1
    assert m.apply(3, u"текст2")["applied"]


def test_busy_skipped():
    p = _FakeParser()
    busy = {"v": True}
    m = live_input.LiveInputMirror(
        get_driver=lambda: "drv", get_parser=lambda: p,
        busy_fn=lambda: busy["v"])
    r = m.apply(1, u"не мешаем конвейеру")
    assert not r["applied"] and r["reason"] == "busy", r
    assert p.calls == []
    busy["v"] = False
    assert m.apply(2, u"не мешаем конвейеру")["applied"]


def test_no_browser_skipped():
    p = _FakeParser()
    m = live_input.LiveInputMirror(
        get_driver=lambda: None, get_parser=lambda: p, busy_fn=lambda: False)
    r = m.apply(1, u"текст")
    assert not r["applied"] and r["reason"] == "no_browser", r
    assert p.calls == []


def test_parser_error_no_raise():
    p = _FakeParser(raise_exc=RuntimeError("boom"))
    m, _ = _mk(parser=p)
    r = m.apply(1, u"текст")
    assert not r["ok"] and not r["applied"] and "boom" in r["reason"], r
    p.raise_exc = None
    assert m.apply(2, u"текст")["applied"]


def test_no_input_field_not_cached():
    p = _FakeParser(ok=False)
    m, _ = _mk(parser=p)
    r = m.apply(1, u"текст")
    assert r["ok"] and not r["applied"] and r["reason"] == "no_input_field", r
    p.ok = True
    assert m.apply(2, u"текст")["applied"]


def test_bad_seq_and_none_text():
    m, p = _mk()
    r = m.apply("abc", None)
    assert r["applied"], r
    assert p.calls == [(u"", None)]


class _FakeEl(object):
    def __init__(self):
        self.value = u""
        self.keys_log = []

    def send_keys(self, *parts):
        for part in parts:
            s = part if isinstance(part, str) else str(part)
            self.keys_log.append(s)
            i = 0
            while i < len(s):
                if s[i] == Keys.CONTROL and i + 1 < len(s):
                    i += 2
                    continue
                ch = s[i]
                if ch == Keys.BACKSPACE:
                    self.value = self.value[:-1] if self.value else u""
                elif ch == Keys.CONTROL:
                    pass
                else:
                    self.value += ch
                i += 1

    def click(self):
        pass


class _FakeDriver(object):
    def __init__(self, el):
        self.el = el

    def execute_script(self, script, *args):
        el = args[0] if args else None
        if "setSelectionRange" in script or "createRange" in script or "focus()" in script:
            return None
        if el is not None and ("e.value" in script or "innerText" in script):
            return el.value
        return None


class _MirrorProbe(parser_base.BaseSiteParser):
    LOG_TAG = "probe"

    def __init__(self):
        self.input_el = _FakeEl()
        self.find_raises = False
        self.type_raises = False
        self.switched = []
        self.insert_calls = []

    def switch_to_site_window(self, driver, prefer_url=None):
        self.switched.append(prefer_url)

    def find_input(self, driver):
        if self.find_raises:
            raise RuntimeError("страница грузится")
        return self.input_el

    def insert_input(self, driver, el, prompt):
        self.insert_calls.append(prompt)
        raise AssertionError("mirror_input НЕ должен звать insert_input (v88.14)")

    def submit(self, driver, el):
        raise AssertionError("mirror_input НЕ должен отправлять сообщение")

    def extract_answer(self, driver):
        return {}

    def _mirror_type_human(self, driver, el, desired):
        if self.type_raises:
            raise RuntimeError("stale element")
        return parser_base.BaseSiteParser._mirror_type_human(self, driver, el, desired)


def test_base_mirror_input_types_with_keys_not_insert():
    p = _MirrorProbe()
    drv = _FakeDriver(p.input_el)
    ok = p.mirror_input(drv, u"пе", prefer_url="https://site/chat/2")
    assert ok is True
    assert p.input_el.value == u"пе", repr(p.input_el.value)
    assert p.insert_calls == [], p.insert_calls
    assert p.switched == ["https://site/chat/2"]
    ok2 = p.mirror_input(drv, u"печатаю")
    assert ok2 is True
    assert p.input_el.value == u"печатаю", repr(p.input_el.value)
    assert any(k for k in p.input_el.keys_log if k and k != Keys.CONTROL), p.input_el.keys_log


def test_base_mirror_input_backspace_on_delete():
    p = _MirrorProbe()
    drv = _FakeDriver(p.input_el)
    assert p.mirror_input(drv, u"abcd") is True
    assert p.input_el.value == u"abcd"
    assert p.mirror_input(drv, u"ab") is True
    assert p.input_el.value == u"ab", repr(p.input_el.value)


def test_base_mirror_input_no_field_fast_fail():
    p = _MirrorProbe()
    p.input_el = None
    assert p.mirror_input("drv", u"текст") is False
    p.input_el = _FakeEl()
    p.find_raises = True
    assert p.mirror_input("drv", u"текст") is False
    p.find_raises = False
    p.type_raises = True
    assert p.mirror_input(_FakeDriver(p.input_el), u"текст") is False


def test_exchange_flag():
    import server_state
    assert not server_state.exchange_active()
    server_state.begin_exchange()
    assert server_state.exchange_active()
    server_state.begin_exchange()
    server_state.end_exchange()
    assert server_state.exchange_active()
    server_state.end_exchange()
    assert not server_state.exchange_active()
    server_state.end_exchange()
    assert not server_state.exchange_active()


def _run_all():
    tests = [
        test_applies_text,
        test_stale_seq_skipped,
        test_same_text_skipped,
        test_busy_skipped,
        test_no_browser_skipped,
        test_parser_error_no_raise,
        test_no_input_field_not_cached,
        test_bad_seq_and_none_text,
        test_base_mirror_input_types_with_keys_not_insert,
        test_base_mirror_input_backspace_on_delete,
        test_base_mirror_input_no_field_fast_fail,
        test_exchange_flag,
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
    if failed:
        print("%d FAILED" % failed)
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    _run_all()
