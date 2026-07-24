# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v104.9: живое зеркало печатает перевод строки как Shift+Enter.

Репорт 24.07: Ctrl+V многострочного текста в панель агента — зеркало
напечатало текст на сайте, и на первом же \\n (send_keys = голый Enter)
сайт ОТПРАВИЛ сообщение, хотя в агенте ничего не отправляли.
"""
import sys

import _fake_selenium
_fake_selenium.install()

from selenium.webdriver.common.keys import Keys

import parser_base

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


class FakeEl(object):
    def __init__(self):
        self.calls = []  # список кортежей аргументов send_keys

    def send_keys(self, *args):
        self.calls.append(args)


class MirrorParser(parser_base.BaseSiteParser):
    LOG_TAG = "test"

    def __init__(self, desired):
        self._reads = 0
        self._desired = desired
        self.logs = []

    def _log(self, msg):
        self.logs.append(str(msg))

    def _focus_input_caret_end(self, driver, el):
        pass

    def _read_input_text(self, driver, el):
        self._reads += 1
        return u"" if self._reads == 1 else self._desired


MULTILINE = u"первая строка\nвторая строка\n\nчетвёртая после пустой"

# 1) многострочный текст (как при Ctrl+V в панель)
p = MirrorParser(MULTILINE)
el = FakeEl()
ok = p._mirror_type_human(None, el, MULTILINE)
check("многострочный текст набран успешно", ok is True)

typed_chunks = [a[0] for a in el.calls if len(a) == 1 and isinstance(a[0], str)]
check("ни один печатаемый кусок не содержит \\n (голого Enter)",
      all(u"\n" not in c and Keys.ENTER not in c for c in typed_chunks))

enter_calls = [a for a in el.calls if any(x == Keys.ENTER for x in a)]
check("все Enter — только в паре с Shift (мягкий перенос)",
      len(enter_calls) > 0 and all(a == (Keys.SHIFT, Keys.ENTER) for a in enter_calls))
check("число Shift+Enter == числу переводов строки (3)",
      len(enter_calls) == MULTILINE.count(u"\n"))
check("сам текст передан полностью (без съеденных строк)",
      u"".join(typed_chunks) == MULTILINE.replace(u"\n", u""))

# 2) однострочный текст — никаких Enter вообще
p2 = MirrorParser(u"просто строка")
el2 = FakeEl()
ok2 = p2._mirror_type_human(None, el2, u"просто строка")
check("однострочный текст набран успешно", ok2 is True)
check("для однострочного — ни одного Enter",
      all(not any(x == Keys.ENTER for x in a) for a in el2.calls))

# 3) CRLF нормализуется (Windows-буфер обмена)
p3 = MirrorParser(u"a\r\nb")
el3 = FakeEl()
p3._type_text_soft_newlines(el3, u"a\r\nb")
enters3 = [a for a in el3.calls if any(x == Keys.ENTER for x in a)]
check("CRLF -> ровно один Shift+Enter",
      len(enters3) == 1 and enters3[0] == (Keys.SHIFT, Keys.ENTER))
check("CRLF: \\r не печатается как символ",
      all(u"\r" not in (a[0] if len(a) == 1 and isinstance(a[0], str) else u"") for a in el3.calls))

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
