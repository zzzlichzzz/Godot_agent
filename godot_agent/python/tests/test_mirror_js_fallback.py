# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v104.10: живой ввод — фолбэк на программную вставку.

Репорт 24.07: на qwen живой ввод не работал — редактор игнорирует
клавишную печать send_keys, но программная вставка (план Б отправки)
там работает — теперь зеркало ей страхуется.
"""
import sys

import _fake_selenium
_fake_selenium.install()

import parser_base

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


class FakeEl(object):
    def send_keys(self, *args):
        pass  # сайт игнорирует синтетический набор (как qwen)


class QwenLikeParser(parser_base.BaseSiteParser):
    """Клавишная печать игнорируется, программная вставка работает."""
    LOG_TAG = "test"
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
        return FakeEl()

    def _read_input_text(self, driver, el):
        return self.field

    def insert_input(self, driver, el, prompt):
        self.insert_calls += 1
        self.field = prompt


class TypingWorksParser(QwenLikeParser):
    """Клавишная печать работает — фолбэк не нужен."""

    def _mirror_type_human(self, driver, el, desired):
        self.field = desired
        return True


class AllBrokenParser(QwenLikeParser):
    """Не работает ничего — зеркало честно возвращает False."""

    def insert_input(self, driver, el, prompt):
        raise RuntimeError("сайт сломан")


# 1) qwen-сценарий: печать игнорируется -> фолбэк спасает
p = QwenLikeParser()
ok = p.mirror_input(None, u"привет мир")
check("печать игнорируется -> зеркало спасено фолбэком", ok is True)
check("текст доехал в поле", p.field == u"привет мир")
check("фолбэк залогирован (v104.10)",
      any(u"v104.10" in m for m in p.logs))
n_logs = len(p.logs)
ok2 = p.mirror_input(None, u"привет мир ещё")
check("второй вызов тоже работает", ok2 is True and p.field == u"привет мир ещё")
check("лог фолбэка не спамит (один раз за сессию)", len(p.logs) == n_logs)

# 2) печать работает -> программная вставка НЕ вызывается
t = TypingWorksParser()
ok = t.mirror_input(None, u"обычный набор")
check("печать работает -> успех без фолбэка",
      ok is True and t.insert_calls == 0 and not t.logs)

# 3) сломано всё -> False без исключений
b = AllBrokenParser()
ok = b.mirror_input(None, u"текст")
check("сломано всё -> False без исключений", ok is False)

# 4) пустой текст (очистка поля) через фолбэк
p4 = QwenLikeParser()
p4.field = u"старый текст"
ok = p4.mirror_input(None, u"")
check("очистка поля через фолбэк", ok is True and p4.field == u"")

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
