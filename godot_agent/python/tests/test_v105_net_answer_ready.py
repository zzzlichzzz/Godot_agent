# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v105: net_answer_ready у AI Studio и Kimi (быстрый путь v88.12).

Зачем: сторожевой таймер в parser_base принимает ответ СРАЗУ, если
net_answer_ready() подтверждает «сеть достримила ответ именно на НАШ запрос».
Метод переопределял ТОЛЬКО qwen — AI Studio и kimi наследовали базовый
return False и выезжали на медленном пути «один и тот же ответ должен быть
увиден дважды». В свёрнутом окне, где DOM пуст, это давало заметную задержку
(в логе — «готовый ответ найден на странице» вместо «сеть подтвердила
готовый НОВЫЙ ответ»).

Критично: сверка идёт с answer_request_count() — номером POST, чей ответ
РЕАЛЬНО лежит в буфере. chat_request_count() растёт уже на
requestWillBeSent, и сверка с ним пропускала бы ПРОШЛЫЙ ответ как готовый
(дубль; урок v88.10).
"""
import sys

import _fake_selenium
_fake_selenium.install()

import ai_parser
import kimi_parser
import qwen_parser
import parser_base

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


class _Mon(object):
    """Минимальный монитор: счётчик ответного POST + признак завершения."""

    def __init__(self, answer_cnt, finished=False, status=None, alive=True):
        self._a = answer_cnt
        self._f = finished
        self._s = status
        self._cdp = type("C", (), {"is_alive": lambda s: alive})()

    def answer_request_count(self):
        return self._a

    def is_finished(self):
        return self._f

    def message_status(self):
        return self._s


class _BrokenMon(object):
    @property
    def _cdp(self):
        raise RuntimeError("CDP-сессия развалилась")


# --- база: заглушка на месте -------------------------------------------------

check("базовый парсер по-прежнему отвечает False (сайты без сети не затронуты)",
      parser_base.BaseSiteParser.net_answer_ready(
          parser_base.BaseSiteParser(), None) is False)

# --- AI Studio --------------------------------------------------------------

_AP = ai_parser.AiStudioParser
_ap = _AP()


def _ai(mon, before):
    _AP._monitor = mon
    _AP._req_count_before_send = before
    return _ap.net_answer_ready(None)


check("AI Studio: метод переопределён",
      _AP.net_answer_ready is not parser_base.BaseSiteParser.net_answer_ready)
check("AI Studio: наш POST + стрим завершён -> True",
      _ai(_Mon(4, finished=True), 3) is True)
check("AI Studio: буфер от ПРОШЛОГО POST -> False (дубля не примем)",
      _ai(_Mon(3, finished=True), 3) is False)
check("AI Studio: наш POST, но стрим НЕ завершён -> False",
      _ai(_Mon(4, finished=False), 3) is False)
check("AI Studio: мёртвая CDP-сессия -> False",
      _ai(_Mon(9, finished=True, alive=False), 3) is False)
check("AI Studio: монитора нет -> False", _ai(None, 3) is False)
check("AI Studio: счётчика нет + завершён -> True",
      _ai(_Mon(1, finished=True), None) is True)
check("AI Studio: сломанный монитор -> False без исключения",
      _ai(_BrokenMon(), 3) is False)

# --- Kimi -------------------------------------------------------------------

_KP = kimi_parser.KimiParser
_kp = _KP()


def _ki(mon, before):
    _KP._monitor = mon
    _kp._req_count_before_send = before
    return _kp.net_answer_ready(None)


check("Kimi: метод переопределён",
      _KP.net_answer_ready is not parser_base.BaseSiteParser.net_answer_ready)
check("Kimi: наш POST + MESSAGE_STATUS_COMPLETED -> True",
      _ki(_Mon(4, status="MESSAGE_STATUS_COMPLETED"), 3) is True)
check("Kimi: буфер от ПРОШЛОГО POST -> False (дубля не примем)",
      _ki(_Mon(3, status="MESSAGE_STATUS_COMPLETED"), 3) is False)
check("Kimi: ещё генерирует -> False",
      _ki(_Mon(4, status="MESSAGE_STATUS_GENERATING"), 3) is False)
check("Kimi: статуса ещё нет -> False",
      _ki(_Mon(4, status=None), 3) is False)
check("Kimi: мёртвая CDP-сессия -> False",
      _ki(_Mon(9, status="MESSAGE_STATUS_COMPLETED", alive=False), 3) is False)
check("Kimi: монитора нет -> False", _ki(None, 3) is False)
check("Kimi: счётчика нет + COMPLETED -> True",
      _ki(_Mon(1, status="MESSAGE_STATUS_COMPLETED"), None) is True)
check("Kimi: сломанный монитор -> False без исключения",
      _ki(_BrokenMon(), 3) is False)

# --- Qwen не тронут ---------------------------------------------------------

check("Qwen сохранил свою реализацию",
      qwen_parser.QwenParser.net_answer_ready
      is not parser_base.BaseSiteParser.net_answer_ready)

# --- пустой ответ отсекается ДО net_answer_ready -----------------------------

_src = open(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)),
                           _os0.pardir, "parsers", "parser_base.py"),
            encoding="utf-8").read()
check("пустой ответ отбрасывается РАНЬШЕ, чем спрашивается net_answer_ready "
      "(иначе быстрый путь принял бы пустоту)",
      _src.index('if not sig.replace("\\x00", "").strip():')
      < _src.index("_net_ok = bool(self.net_answer_ready(driver))"))

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
