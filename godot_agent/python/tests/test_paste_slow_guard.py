# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v104.8: защита от медленной («поздней») вставки.

Репорт 24.07 (qwen): вставка мега-промпта доехала уже ПОСЛЕ отправки —
первым ушло голое задание из поля (путь «отправляю как есть» v88.4),
вторым сообщением — сам мега-промпт.
"""
import sys
import time

import _fake_selenium
_fake_selenium.install()

import parser_base

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


class SlowFieldParser(parser_base.BaseSiteParser):
    """Поле, в котором текст «материализуется» через fill_after секунд."""
    LOG_TAG = "test"

    def __init__(self, fill_after, text):
        self._t0 = time.time()
        self._fill_after = fill_after
        self._text = text
        self.logs = []

    def _log(self, msg):
        self.logs.append(str(msg))

    def _read_field_text_quick(self, driver, el):
        if time.time() - self._t0 >= self._fill_after:
            return self._text
        return u""


BIG = u"м" * 11200

# 1) _field_text_too_short: кого можно и кого нельзя отправлять «как есть»
p = SlowFieldParser(0, BIG)
check("too_short: голое задание вместо мега-промпта -> True",
      p._field_text_too_short(u"как можно улучшить игру ?", BIG) is True)
check("too_short: тот же текст с другими пробелами -> False",
      p._field_text_too_short(BIG[:5600] + u"\n \u00a0" + BIG[5600:], BIG) is False)
check("too_short: 95%% длины (разметка съела чуть-чуть) -> False",
      p._field_text_too_short(BIG[: int(11200 * 0.95)], BIG) is False)
check("too_short: половина текста -> True",
      p._field_text_too_short(BIG[:5600], BIG) is True)
check("too_short: пустой prompt -> False",
      p._field_text_too_short(u"что-то", u"") is False)
check("too_short: пустое поле при непустом prompt -> True",
      p._field_text_too_short(u"", BIG) is True)

# 2) новый таймаут: медленный редактор «дожёвывает» вставку 6 секунд
wait_s = min(30.0, 2.0 + len(BIG) / 1500.0)
check("wait_s для 11200 симв. >= 9 с (старый лимит был ~3.8 с)", wait_s >= 9.0)
slow = SlowFieldParser(6.0, BIG)
_t0 = time.time()
ok = slow._wait_field_matches(None, None, BIG, wait_s)
_dt = time.time() - _t0
check("медленная вставка (6 с) дожидается совпадения", ok is True)
check("дождались раньше жёсткого потолка (< 20 с)", _dt < 20.0)

# 3) вставка так и не появилась: выходим по таймауту, без вечного зависания
never = SlowFieldParser(9999.0, BIG)
_t0 = time.time()
ok = never._wait_field_matches(None, None, BIG, 1.0)
_dt = time.time() - _t0
check("несовпадение без роста поля -> False", ok is False)
check("выход близко к базовому таймауту, без зависания (< 7 с)", _dt < 7.0)

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
