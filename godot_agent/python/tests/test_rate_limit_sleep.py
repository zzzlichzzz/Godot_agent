# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты v104.12: детект лимита запросов (429/баннеры) + спящий режим."""
import sys

import _fake_selenium
_fake_selenium.install()

import rate_limit
import parser_base
from net_monitor import BaseNetMonitor

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


# --- текстовые маркеры ---
check("баннер кими «Высокая нагрузка» детектится",
      bool(rate_limit.reason_from_text(u"Высокая нагрузка на сервер. Попробуйте позже.")))
check("too many requests детектится",
      bool(rate_limit.reason_from_text(u"Error: Too Many Requests")))
long_text = (u"Вот как устроен rate limit в нашем агенте... " * 20)
check("длинный настоящий ответ про rate limit — НЕ лимит",
      rate_limit.reason_from_text(long_text) is None)
check("короткий ответ С действием — НЕ лимит",
      rate_limit.reason_from_text(u"rate limit", {"action": "create_file"}) is None)
check("обычный короткий ответ — НЕ лимит",
      rate_limit.reason_from_text(u"Готово, задача выполнена.") is None)
check("пустой текст — НЕ лимит", rate_limit.reason_from_text(u"") is None)
mid_text = (u"Готово. Я добавил обработку ошибок в hud.gd. Если сайт снова напишет "
            u"про лимит — попробуйте позже повторить запрос или открыть новый чат, "
            u"это обычно помогает при перегрузке сервера в часы пик.")
check("ответ средней длины с маркером — НЕ лимит (порог 160, v104.13)",
      len(mid_text) > 160 and rate_limit.reason_from_text(mid_text) is None)
check("порог ужат до 160 симв.", rate_limit.MAX_TEXT_LEN_FOR_MARKERS == 160)

# --- HTTP-статусы ---
check("429 -> лимит", bool(rate_limit.reason_from_status(429)))
check("503 -> лимит", bool(rate_limit.reason_from_status(503)))
check("200 -> не лимит", rate_limit.reason_from_status(200) is None)
check("None -> не лимит", rate_limit.reason_from_status(None) is None)

# --- расписание сна ---
check("паузы нарастают 30/60/120/300",
      [rate_limit.sleep_seconds(i) for i in range(4)] == [30, 60, 120, 300])
check("после исчерпания — остановка (None)",
      rate_limit.sleep_seconds(4) is None and rate_limit.sleep_seconds(-1) is None)


# --- перехват статуса в мониторе ---
class FakeCdp(object):
    def on_event(self, name, fn):
        pass

    def send_command(self, *a, **k):
        return {}


class Mon(BaseNetMonitor):
    CHAT_URL_SUBSTR = "/api/v2/chat/completions"
    RESPONSE_MIME_SUBSTR = "text/event-stream"
    LOG_TAG = "test"

    def _decode_frames_partial(self, raw):
        return [], 0

    def _decode_frames(self, raw):
        return []

    def _apply_event(self, obj):
        pass

    def _reset_answer_state_locked(self):
        pass

    def current_text(self):
        return ""


mon = Mon(FakeCdp())
mon._on_response_received({"requestId": "r1", "response": {
    "url": "https://chat.qwen.ai/api/v2/chat/completions",
    "status": 429, "mimeType": "text/html"}})
check("монитор поймал 429 на чат-эндпоинте", mon.pop_http_error() == 429)
check("статус читается один раз (pop)", mon.pop_http_error() is None)

mon._on_response_received({"requestId": "r2", "response": {
    "url": "https://chat.qwen.ai/api/v2/chat/completions",
    "status": 200, "mimeType": "application/json"}})
check("200 не считается ошибкой", mon.pop_http_error() is None)

mon._on_response_received({"requestId": "r3", "response": {
    "url": "https://chat.qwen.ai/static/logo.png",
    "status": 429, "mimeType": "text/html"}})
check("429 на ЧУЖОМ url игнорируется", mon.pop_http_error() is None)


# --- доступ из парсера ---
class P(parser_base.BaseSiteParser):
    def __init__(self):
        pass


class FakeMonPop(object):
    def pop_http_error(self):
        return 429


p = P()
check("парсер без монитора (DeepSeek) -> None",
      p.pop_rate_limit_network_status() is None)
P._monitor = FakeMonPop()
check("парсер с монитором -> 429", p.pop_rate_limit_network_status() == 429)

n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
