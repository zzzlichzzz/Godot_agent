# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v87.9: авто-«Сгенерировать заново» в BaseSiteParser.

Сценарии:
  A. Ответ не дождались (таймаут ожидания) -> try_regenerate нажал кнопку ->
     повтор генерации дал нормальный ответ -> конвейер вернул его.
  B. Ответ пришёл ПУСТЫМ -> try_regenerate -> нормальный ответ.
  C. Сайт не умеет регенерацию (try_regenerate по умолчанию False) ->
     поведение прежнее: таймаут пробрасывается наверх.

Запуск: python3 test_v87_9_regen.py
"""
import os
import sys
import time
import types

# --- заглушка selenium (как в test_v87_1_kimi_cdp.py): боевого браузера нет ---
_selenium = types.ModuleType("selenium")
_webdriver = types.ModuleType("selenium.webdriver")
_common = types.ModuleType("selenium.webdriver.common")
_keys_mod = types.ModuleType("selenium.webdriver.common.keys")
_exc_mod = types.ModuleType("selenium.common.exceptions")
_common_pkg = types.ModuleType("selenium.common")


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

# заглушка browser_manager (импортируется внутри send_message_and_get_response)
_bm = types.ModuleType("browser_manager")
_bm.harden_background_tab = lambda driver: None
sys.modules.setdefault("browser_manager", _bm)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser_base import BaseSiteParser  # noqa: E402


class _FakeDriver(object):
    current_url = "https://chat.qwen.ai/c/test"
    window_handles = ["w1"]

    def execute_script(self, *a, **k):
        # используется только проверкой «текст вставился» — вернём непустое.
        return "x"


class _FakeRegenParser(BaseSiteParser):
    """Управляемый парсер: страница эмулируется полями n/text."""

    LOG_TAG = "fake_regen"
    WINDOW_URL_MATCH = "chat.qwen.ai"
    TIMEOUT = 1.0
    QUIET_PERIOD = 0.2
    HARD_QUIET_PERIOD = 0.5
    POLL_INTERVAL = 0.05
    POST_QUIET_GRACE = 0.2
    SEND_RETRIES = 0

    def __init__(self):
        self.n = 1              # ответов модели на странице
        self.text = ""          # текст последнего ответа
        self.regen_clicks = 0

    # --- сайт-специфика ---
    def count_answers(self, driver):
        return self.n

    def answer_len(self, driver):
        return len(self.text)

    def answer_preview(self, driver):
        return self.text[-50:]

    def answer_stream(self, driver):
        return self.text

    def is_generating(self, driver):
        return False

    def extract_answer(self, driver):
        return {"text": self.text, "actionRaw": None, "error": None}

    def find_input(self, driver):
        return object()

    def insert_input(self, driver, el, prompt):
        pass

    def submit(self, driver, el):
        pass

    # --- кнопка «Сгенерировать заново» ---
    def try_regenerate(self, driver):
        self.regen_clicks += 1
        # повтор генерации: появляется НОВЫЙ нормальный ответ
        self.n += 1
        self.text = "нормальный ответ после повтора"
        return True


def test_regen_after_timeout():
    """A: новый ответ так и не появился -> таймаут -> клик -> ответ пришёл."""
    p = _FakeRegenParser()
    d = _FakeDriver()
    res = p.send_message_and_get_response(d, "привет")
    assert p.regen_clicks == 1, "кнопка должна быть нажата ровно один раз, а не %d" % p.regen_clicks
    assert "нормальный ответ после повтора" in (res.get("text") or ""), res


class _FakeRegenAfterEmptyParser(_FakeRegenParser):
    """B: первое ожидание вернуло ПУСТОЙ ответ (сайт сбоил без таймаута)."""

    def wait_for_new_answer(self, driver, initial_count, **kwargs):
        if not self.regen_clicks:
            return {"text": "", "actionRaw": None, "error": None}
        return BaseSiteParser.wait_for_new_answer(self, driver, initial_count, **kwargs)


def test_regen_after_empty_answer():
    p = _FakeRegenAfterEmptyParser()
    d = _FakeDriver()
    res = p.send_message_and_get_response(d, "привет")
    assert p.regen_clicks == 1, "кнопка должна быть нажата ровно один раз, а не %d" % p.regen_clicks
    assert "нормальный ответ после повтора" in (res.get("text") or ""), res


class _FakeNoRegenParser(_FakeRegenParser):
    """C: сайт без кнопки повтора — поведение прежнее (таймаут наверх)."""

    def try_regenerate(self, driver):
        return BaseSiteParser.try_regenerate(self, driver)  # False


def test_no_regen_keeps_old_timeout_behavior():
    p = _FakeNoRegenParser()
    d = _FakeDriver()
    try:
        p.send_message_and_get_response(d, "привет")
    except TimeoutError:
        return
    raise AssertionError("ожидался TimeoutError, как до v87.9")


def _run_all():
    tests = [
        test_regen_after_timeout,
        test_regen_after_empty_answer,
        test_no_regen_keeps_old_timeout_behavior,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK   %s" % t.__name__)
        except Exception as e:
            failed += 1
            print("FAIL %s -> %r" % (t.__name__, e))
    if failed:
        print("%d test(s) FAILED" % failed)
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    _run_all()
