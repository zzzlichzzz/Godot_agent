# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v104.7: kimi K2.6-Мгновенный + веб-поиск кладёт текст в tool-блоки:
живой стрим берётся из live_text (tool-ведро как запасной источник),
финальный ответ при пустом current_text спасает DOM-фолбэк (репорт 24.07)."""
import threading

import _fake_selenium
_fake_selenium.install()

import kimi_parser

results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL") + ": " + name)


def make_monitor():
    mon = object.__new__(kimi_parser.KimiChatMonitor)
    mon._lock = threading.RLock()
    mon._assistant_message_count = 0
    mon._generating = False
    mon._reset_answer_state_locked()
    return mon


# --- 1. обычные текстовые блоки (регресс): current_text и live_text совпадают ---
mon = make_monitor()
mon._apply_event({"op": "set", "block": {"id": "1", "text": {"content": "При"}}})
mon._apply_event({"op": "append", "block": {"id": "1", "text": {"content": "вет"}}})
check("обычный текст: current_text", mon.current_text() == "Привет")
check("обычный текст: live_text", mon.live_text() == "Привет")

# --- 2. только tool-блоки (K2.6+поиск): current_text пуст, live_text видит текст ---
mon = make_monitor()
mon._apply_event({"op": "set", "block": {"id": "2", "tool": {"name": "search"}, "text": {"content": "Ответ из tool-блока"}}})
check("tool-блоки: current_text пуст (не подмешиваем)", mon.current_text() == "")
check("tool-блоки: live_text отдаёт текст", mon.live_text() == "Ответ из tool-блока")

# --- 3. при появлении обычных блоков live_text переключается на них ---
mon._apply_event({"op": "set", "block": {"id": "3", "text": {"content": "Финал"}}})
check("смешанно: live_text = обычный текст", mon.live_text() == "Финал")
check("смешанно: current_text = обычный текст", mon.current_text() == "Финал")

# --- 4. text строкой, а не объектом ---
mon = make_monitor()
mon._apply_event({"op": "set", "block": {"id": "1", "text": "строка"}})
check("text-строка попадает в ответ", mon.current_text() == "строка")

# --- 5. сырые события копятся для дампа и сбрасываются новым запросом ---
check("события накоплены", len(mon._debug_events) == 1)
mon._reset_answer_state_locked()
check("сброс чистит события и tool-ведро",
      mon._debug_events == [] and mon._tool_blocks == {} and mon.live_text() == "")

# --- 6. extract_raw_fallback: текст из DOM + вырезание ===DONE=== ---
class FakeDriver(object):
    def execute_script(self, script, *args):
        return "Ответ модели из DOM\n===DONE==="

p = kimi_parser.KimiParser()
raw = p.extract_raw_fallback(FakeDriver())
check("DOM-фолбэк: текст без DONE", raw and raw["text"] == "Ответ модели из DOM" and raw["actionRaw"] is None)

class EmptyDriver(object):
    def execute_script(self, script, *args):
        return ""

check("DOM-фолбэк: пустой DOM -> None", p.extract_raw_fallback(EmptyDriver()) is None)

failed = [n for n, ok in results if not ok]
print("\n%d/%d PASS" % (len(results) - len(failed), len(results)))
import sys
sys.exit(1 if failed else 0)
