# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v105: подмена видимости стала ПЕР-САЙТОВОЙ + запрет JS-фолбэка зеркала.

Зачем эти тесты существуют: подмена document.visibilityState/hidden — самый
заметный след автоматизации из всего, что делает агент (страница видит её одной
строкой JS). Раньше она ставилась при КАЖДОЙ отправке ЛЮБОМУ сайту, включая те,
что читают ответ из сети и в рендере не нуждаются. Тесты фиксируют, что след
ставится только там, где без него ломается чтение ответа, — чтобы рефакторинг
не вернул его молча всем сайтам сразу.
"""
import sys

import _fake_selenium
_fake_selenium.install()

import browser_manager
import parser_base
import sites

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


# --- реестр сайтов ----------------------------------------------------------

check("kimi (ответ целиком из сети) спуф НЕ запрашивает",
      sites.needs_visibility_spoof(site_id="kimi") is False)
check("deepseek (чистый DOM) спуф запрашивает",
      sites.needs_visibility_spoof(site_id="deepseek") is True)
check("aistudio (гибрид DOM+сеть) спуф запрашивает",
      sites.needs_visibility_spoof(site_id="aistudio") is True)
check("qwen (DOM + сеть-страховка) спуф запрашивает",
      sites.needs_visibility_spoof(site_id="qwen") is True)
check("НЕИЗВЕСТНЫЙ сайт спуфа не получает (безопасное значение по умолчанию)",
      sites.needs_visibility_spoof(url="https://lmarena.ai/") is False)
check("без аргументов — тоже False",
      sites.needs_visibility_spoof() is False)
check("решение по URL совпадает с решением по id",
      sites.needs_visibility_spoof(url="https://www.kimi.com/chat/1") is False
      and sites.needs_visibility_spoof(url="https://chat.qwen.ai/c/1") is True)

# --- сам JS -----------------------------------------------------------------

_js = browser_manager.VISIBILITY_SPOOF_JS
check("свойства ставятся на Document.prototype, а не на экземпляр document",
      "Document.prototype" in _js
      and "Object.defineProperty(document," not in _js.replace(" ", ""))
check("hasFocus больше НЕ подменяется (палился через toString)",
      "hasFocus" not in _js.split("//")[0] or "defineProperty(proto, 'hasFocus'" not in _js)
check("скрипт идемпотентен (повторный запуск не плодит слушателей)",
      "getOwnPropertyDescriptor" in _js and "return;" in _js)
check("идемпотентность БЕЗ своего свойства на window",
      "window.__" not in _js)

# --- кому ставится спуф -----------------------------------------------------

calls = []
_real_harden = browser_manager.harden_background_tab
browser_manager.harden_background_tab = lambda drv: calls.append(drv)


class _Drv(object):
    def __init__(self, url):
        self.current_url = url


class _P(parser_base.BaseSiteParser):
    LOG_TAG = "t105"
    WINDOW_URL_MATCH = ""

    def _log(self, msg):
        pass


_p = _P()

del calls[:]
_p._maybe_harden_background_tab(_Drv("https://chat.deepseek.com/a/chat/s/1"))
check("DOM-сайт получает спуф", len(calls) == 1)

del calls[:]
_p._maybe_harden_background_tab(_Drv("https://www.kimi.com/chat/1"))
check("сетевой сайт спуф НЕ получает", len(calls) == 0)

del calls[:]
_p._maybe_harden_background_tab(_Drv("https://lmarena.ai/"))
check("незарегистрированный сайт спуф НЕ получает", len(calls) == 0)


class _POff(_P):
    NEEDS_VISIBILITY_SPOOF = False


del calls[:]
_POff()._maybe_harden_background_tab(_Drv("https://chat.deepseek.com/"))
check("NEEDS_VISIBILITY_SPOOF=False перебивает реестр", len(calls) == 0)


class _POn(_P):
    NEEDS_VISIBILITY_SPOOF = True


del calls[:]
_POn()._maybe_harden_background_tab(_Drv("https://lmarena.ai/"))
check("NEEDS_VISIBILITY_SPOOF=True перебивает реестр", len(calls) == 1)


class _BadDrv(object):
    @property
    def current_url(self):
        raise RuntimeError("вкладка потеряна")


del calls[:]
try:
    _p._maybe_harden_background_tab(_BadDrv())
    _ok_bad = True
except Exception:
    _ok_bad = False
check("сломанный driver не роняет отправку промпта", _ok_bad)

browser_manager.harden_background_tab = _real_harden

# --- kimi объявляет отказ от спуфа явно -------------------------------------

import kimi_parser as _kp
check("kimi_parser объявляет NEEDS_VISIBILITY_SPOOF = False",
      _kp.KimiParser.NEEDS_VISIBILITY_SPOOF is False)

# --- запрет JS-фолбэка живого ввода -----------------------------------------


class _FakeEl(object):
    def send_keys(self, *a):
        pass  # сайт игнорирует клавишную печать (как редактор qwen)


class _QwenLike(parser_base.BaseSiteParser):
    LOG_TAG = "t105"
    WINDOW_URL_MATCH = ""

    def __init__(self):
        self.field = u""
        self.insert_calls = 0
        self.logs = []

    def _log(self, msg):
        self.logs.append(str(msg))

    def _focus_input_caret_end(self, driver, el):
        pass

    def find_input(self, driver):
        return _FakeEl()

    def _read_input_text(self, driver, el):
        return self.field

    def insert_input(self, driver, el, prompt):
        self.insert_calls += 1
        self.field = prompt


class _Strict(_QwenLike):
    ALLOW_MIRROR_JS_FALLBACK = False


check("по умолчанию фолбэк разрешён (живой ввод qwen не сломан)",
      parser_base.BaseSiteParser.ALLOW_MIRROR_JS_FALLBACK is True)

_a = _QwenLike()
check("фолбэк спасает зеркало там, где он разрешён",
      _a.mirror_input(None, u"привет") is True and _a.insert_calls == 1)

_b = _Strict()
check("при запрете: False и НИ ОДНОЙ программной вставки (isTrusted=false не уходит)",
      _b.mirror_input(None, u"привет") is False and _b.insert_calls == 0)
check("запрет залогирован один раз",
      sum(1 for m in _b.logs if "v105" in m) == 1)
_b.mirror_input(None, u"ещё")
check("лог запрета не спамит при каждом зеркалировании",
      sum(1 for m in _b.logs if "v105" in m) == 1 and _b.insert_calls == 0)

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
