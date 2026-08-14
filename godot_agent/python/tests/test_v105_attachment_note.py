# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v105: подпись к сообщению, которое сайт превратил во вложение.

Зачем: kimi превращает вставку >4000 байт в файл .txt (см.
KimiParser.count_composer_attachments). Механизм v104.4 это распознаёт и не
плодит дубли файлов, но сообщение при этом уходит БЕЗ единого символа в теле —
модель получает файл и никаких указаний, что с ним делать. К файлу модель
относится как к справочному материалу, а не как к инструкции, и протокол
agent_action может не соблюсти. Подпись даёт явное указание прочитать файл.

Здесь же закреплён фикс: ВТОРАЯ точка обнаружения вложения (в конвейере
отправки) раньше не выставляла _insert_became_attachment, из-за чего
контрольная сверка перед отправкой пыталась вставить промпт заново и могла
создать второй файл.
"""
import sys

import _fake_selenium
_fake_selenium.install()

import parser_base

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


class _El(object):
    def __init__(self, fail=False):
        self.typed = []
        self.fail = fail

    def send_keys(self, *args):
        if self.fail:
            raise RuntimeError("редактор не принимает клавиши")
        self.typed.append(u"".join(str(a) for a in args))


class _P(parser_base.BaseSiteParser):
    LOG_TAG = "t105n"
    WINDOW_URL_MATCH = ""

    def __init__(self):
        self.logs = []

    def _log(self, msg):
        self.logs.append(str(msg))

    def _focus_input_caret_end(self, driver, el):
        pass


# --- сама подпись -----------------------------------------------------------

_p = _P()
_el = _El()
_p._type_attachment_note(None, _el)

check("подпись набрана клавишами (isTrusted-события, а не value=)",
      len(_el.typed) == 1 and len(_el.typed[0]) > 20)
check("подпись БЕЗ переводов строк — иначе Enter отправит сообщение раньше времени",
      "\n" not in _el.typed[0] and "\r" not in _el.typed[0])
check("подпись явно велит прочитать приложенный файл",
      u"файл" in _el.typed[0].lower())
check("подпись многократно короче порога вложения kimi (4000 байт)",
      len(_el.typed[0].encode("utf-8")) < 1000)
check("подпись залогирована", any("v105" in m for m in _p.logs))


class _PEmpty(_P):
    ATTACHMENT_NOTE = u""


_pe = _PEmpty()
_ele = _El()
_pe._type_attachment_note(None, _ele)
check("ATTACHMENT_NOTE='' -> сайт может отказаться от подписи", _ele.typed == [])


class _PMulti(_P):
    ATTACHMENT_NOTE = u"первая строка\nвторая\r\nтретья"


_pm = _PMulti()
_elm = _El()
_pm._type_attachment_note(None, _elm)
check("многострочная подпись схлопывается в одну строку",
      len(_elm.typed) == 1
      and "\n" not in _elm.typed[0] and "\r" not in _elm.typed[0])

_pf = _P()
_elf = _El(fail=True)
try:
    _pf._type_attachment_note(None, _elf)
    _ok_fail = True
except Exception:
    _ok_fail = False
check("редактор не принял клавиши -> отправка НЕ падает (подпись не обязательна)",
      _ok_fail)
check("провал подписи виден в логе",
      any("не набралась" in m for m in _pf.logs))

check("у базового парсера подпись задана по умолчанию",
      bool(parser_base.BaseSiteParser.ATTACHMENT_NOTE))
check("подпись по умолчанию — одна строка",
      "\n" not in parser_base.BaseSiteParser.ATTACHMENT_NOTE)

# --- флаг вложения на ОБЕИХ точках обнаружения -------------------------------

_src = open(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)),
                          _os0.pardir, "parsers", "parser_base.py"),
            encoding="utf-8").read()
check("обе точки обнаружения вложения выставляют _insert_became_attachment",
      _src.count("self._insert_became_attachment = True") == 2)
check("подпись вызывается в конвейере отправки",
      "self._type_attachment_note(driver, el)" in _src)
check("подпись ставится ДО контрольной сверки перед отправкой",
      _src.index("self._type_attachment_note(driver, el)")
      < _src.index("поле изменилось после проверки"))

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
