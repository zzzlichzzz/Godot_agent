# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v88.12: лечение вечного «жду начала ответа» у qwen.

Сценарий бага: базовый снимок «что было ДО отправки» читался ПОЛНЫМ
extract_answer ПОСЛЕ submit — у qwen тот блокировался на весь цикл генерации
и записывал в снимок уже НОВЫЙ ответ (через сетевой фолбэк v88.6).
Сторожевой таймер потом отбрасывал настоящий ответ как «старый»
(sig == baseline), счётчик DOM-реплик не рос, генерация уже кончилась —
панель бесконечно показывала «модель думает…».

Проверяем:
1) net_answer_ready=True -> сторожевой таймер принимает ответ сразу,
   даже если базовый снимок «отравлен» новым ответом (реплей инцидента);
2) baseline= снимок ДО submit пробрасывается в wait_for_new_answer и
   не даёт отбросить новый ответ (двойное подтверждение без сети);
3) без сетевого подтверждения СТАРЫЙ ответ (sig == baseline) по-прежнему
   НЕ принимается (анти-дубль не сломан) -> TimeoutError;
4) несбалансированный JSON действия не принимается даже при net-подтверждении;
5) QwenParser.net_answer_ready: свежесть по счётчику POST + is_finished.

Время в parser_base подменяется фейком — тесты мгновенны, без реальных
ожиданий по 20 с.
"""
import sys
import time as _real_time
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

import parser_base  # noqa: E402


class _FakeTime(object):
    """Фейковое время: каждый time() двигает часы на 0.5 с, sleep — на свою длительность."""

    def __init__(self):
        self.t = 1000000.0

    def time(self):
        self.t += 0.5
        return self.t

    def sleep(self, s):
        self.t += max(0.0, float(s))


class _StuckSite(parser_base.BaseSiteParser):
    """Реплей инцидента: счётчик реплик НЕ растёт, генерация уже кончилась,
    extract_answer всегда возвращает уже ГОТОВЫЙ новый ответ (из сети)."""

    LOG_TAG = "fake_v88_12"

    def __init__(self, answer, net_ready=False):
        self.answer = dict(answer)
        self.net_ready = net_ready

    def count_answers(self, driver):
        return 11  # DOM виртуализирован — счётчик не меняется

    def answer_len(self, driver):
        return len(self.answer.get("text") or "")

    def is_generating(self, driver):
        return False  # стрим уже FINISHED

    def extract_answer(self, driver):
        return dict(self.answer)

    def extract_answer_snapshot(self, driver):
        # «Отравленный» снимок: к моменту чтения на странице/в сети уже НОВЫЙ ответ.
        return dict(self.answer)

    def net_answer_ready(self, driver):
        return self.net_ready

    def find_input(self, driver):
        return "el"

    def insert_input(self, driver, el, prompt):
        pass

    def submit(self, driver, el):
        pass


def _with_fake_time(fn):
    ft = _FakeTime()
    parser_base.time = ft
    try:
        return fn()
    finally:
        parser_base.time = _real_time


NEW_ANSWER = {"text": u"Готово, дописал код.",
              "actionRaw": u'{"action": "create_script", "path": "res://a.gd"}',
              "error": None}


def test_incident_replay_net_confirmed():
    # Базовый снимок НЕ передан (как до фикса) и «отравлен» новым ответом,
    # но сеть подтверждает свежий завершённый ответ -> принимаем, а не висим.
    def run():
        p = _StuckSite(NEW_ANSWER, net_ready=True)
        return p.wait_for_new_answer("drv", 11, timeout=300, poll_interval=0.01)
    r = _with_fake_time(run)
    assert r is not None and r.get("text") == NEW_ANSWER["text"], r
    assert r.get("actionRaw") == NEW_ANSWER["actionRaw"]


def test_presend_baseline_unsticks_without_net():
    # Сетевого подтверждения нет, но конвейер передал снимок, снятый ДО
    # submit (старый текст) -> новый ответ больше не считается «старым» и
    # сторожевой таймер забирает его штатным двойным подтверждением.
    def run():
        p = _StuckSite(NEW_ANSWER, net_ready=False)
        return p.wait_for_new_answer(
            "drv", 11, timeout=300, poll_interval=0.01,
            baseline={"text": u"старый ответ", "actionRaw": None})
    r = _with_fake_time(run)
    assert r is not None and r.get("text") == NEW_ANSWER["text"], r


def test_stale_answer_still_rejected():
    # Анти-дубль не сломан: без сетевого подтверждения ответ, совпадающий
    # со снимком ДО отправки (модель НЕ ответила), НЕ принимается -> таймаут.
    def run():
        p = _StuckSite(NEW_ANSWER, net_ready=False)
        try:
            p.wait_for_new_answer("drv", 11, timeout=120, poll_interval=0.01,
                                  baseline=dict(NEW_ANSWER))
        except TimeoutError:
            return "timeout"
        return "accepted"
    assert _with_fake_time(run) == "timeout"


def test_net_confirm_requires_balanced_json():
    # Даже при сетевом подтверждении оборванный JSON действия не принимается
    # мгновенно (защита от полузаписанного буфера) -> таймаут при совпадении с baseline.
    bad = {"text": u"текст", "actionRaw": u'{"action": "create_script", "path":',
           "error": None}
    def run():
        p = _StuckSite(bad, net_ready=True)
        try:
            p.wait_for_new_answer("drv", 11, timeout=120, poll_interval=0.01,
                                  baseline=dict(bad))
        except TimeoutError:
            return "timeout"
        return "accepted"
    assert _with_fake_time(run) == "timeout"


def test_qwen_net_answer_ready_gates():
    import qwen_parser

    class _Cdp(object):
        def __init__(self, alive=True):
            self.alive = alive
        def is_alive(self):
            return self.alive

    class _Mon(object):
        def __init__(self, cnt, fin, alive=True):
            self._cdp = _Cdp(alive)
            self.cnt = cnt
            self.fin = fin
        def answer_request_count(self):
            return self.cnt
        def is_finished(self):
            return self.fin

    P = qwen_parser.QwenParser
    old_mon = P._monitor
    old_before = P._req_count_before_send
    try:
        p = qwen_parser.PARSER
        P._monitor = None
        assert p.net_answer_ready(None) is False  # нет монитора
        P._req_count_before_send = 5
        P._monitor = _Mon(5, True)
        assert p.net_answer_ready(None) is False  # POST ещё не ушёл/ответ старый
        P._monitor = _Mon(6, False)
        assert p.net_answer_ready(None) is False  # стрим ещё не FINISHED
        P._monitor = _Mon(6, True)
        assert p.net_answer_ready(None) is True   # свежий + завершён
        P._monitor = _Mon(6, True, alive=False)
        assert p.net_answer_ready(None) is False  # CDP отвалился
    finally:
        P._monitor = old_mon
        P._req_count_before_send = old_before


def _run_all():
    tests = [
        test_incident_replay_net_confirmed,
        test_presend_baseline_unsticks_without_net,
        test_stale_answer_still_rejected,
        test_net_confirm_requires_balanced_json,
        test_qwen_net_answer_ready_gates,
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
