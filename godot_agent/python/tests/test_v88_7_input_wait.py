# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v88.7: терпеливое ожидание поля ввода (_wait_for_input) и
диагностика страницы в ошибке «Поле ввода не найдено».
Сценарий из реального бага: авто-инициализация шлёт мега-промпт сразу
после открытия chat.qwen.ai — страница ещё грузится, старые 3x0.5 с
роняли шаг с «Поле ввода не найдено (qwen_parser)».
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
from parser_base import BaseSiteParser  # noqa: E402


class _FakeDriver(object):
    """execute_script нужен только для _input_diagnostics."""

    def execute_script(self, script, *a):
        return {"href": "https://chat.qwen.ai/", "state": "loading",
                "ta": 0, "ce": 0, "fr": 1, "head": "Loading..."}


class _LateInputParser(BaseSiteParser):
    """Поле «появляется» только с N-го вызова find_input (долгая загрузка)."""
    LOG_TAG = "fake_wait"
    INPUT_WAIT_TIMEOUT = 5.0  # чтобы тест не ждал 45 с

    def __init__(self, appear_after):
        self.calls = 0
        self.appear_after = appear_after

    def find_input(self, driver):
        self.calls += 1
        if self.calls >= self.appear_after:
            return {"fake": "element"}
        return None


def test_input_appears_late_is_found():
    # старое поведение: 3 попытки и ошибка; теперь поле с 7-го вызова — ОК
    p = _LateInputParser(appear_after=7)
    el = p._wait_for_input(_FakeDriver(), retries=3)
    assert el == {"fake": "element"}
    assert p.calls >= 7, p.calls


def test_input_immediate_no_extra_wait():
    p = _LateInputParser(appear_after=1)
    el = p._wait_for_input(_FakeDriver(), retries=3)
    assert el == {"fake": "element"}
    assert p.calls == 1, p.calls  # без лишних ожиданий


def test_input_never_appears_raises_with_diagnostics():
    p = _LateInputParser(appear_after=10 ** 9)
    p.INPUT_WAIT_TIMEOUT = 1.0
    try:
        p._wait_for_input(_FakeDriver(), retries=2)
    except Exception as e:
        msg = str(e)
        assert u"Поле ввода не найдено" in msg, msg
        assert "chat.qwen.ai" in msg and "readyState=loading" in msg, msg
        assert "textarea=0" in msg and "iframe=1" in msg, msg
    else:
        raise AssertionError(u"ожидалась ошибка")


def test_find_input_exception_treated_as_absent():
    class _Flaky(_LateInputParser):
        def find_input(self, driver):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("page is reloading")
            return {"fake": "element"}

    p = _Flaky(appear_after=0)
    el = p._wait_for_input(_FakeDriver(), retries=2)
    assert el == {"fake": "element"}


def test_qwen_find_input_js_has_shadow_walk():
    import qwen_parser
    js = qwen_parser.JS_FIND_INPUT
    assert "shadowRoot" in js, u"нет обхода shadow DOM"
    assert "message-input-textarea" in js  # старый быстрый селектор на месте
    assert "contenteditable" in js


def _run_all():
    tests = [
        test_input_appears_late_is_found,
        test_input_immediate_no_extra_wait,
        test_input_never_appears_raises_with_diagnostics,
        test_find_input_exception_treated_as_absent,
        test_qwen_find_input_js_has_shadow_walk,
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
