# -*- coding: utf-8 -*-
"""Парсер Arena AI (arena.ai/text/direct) — v1.

Чтение ответа из СЕТИ (Vercel streaming protocol), как у Qwen.
Формат стрима:
  a0:"текст"      — append chunk (stream 0)
  ad:{"finishReason":"stop"} — done
"""
import json
import threading
from browser.net_monitor import BaseNetMonitor
from browser import qwen_net


def decode_arena_stream_lines(text):
    """Все события из Vercel-стрима: строки вида a0:... / ad:... / ...:"""
    events = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith(("a0:", "ad:")):
            prefix, payload = line.split(":", 1)
            events.append({"prefix": prefix, "payload": payload})
    return events


def decode_arena_stream_partial(raw_bytes):
    """Разбор НАЧАЛА буфера: полные строки (до последнего \n) разбираются,
    неполный хвост остаётся. Аналог qwen_net.decode_qwen_sse_partial."""
    raw = bytes(raw_bytes)
    idx = raw.rfind(b"\n")
    if idx < 0:
        return [], 0
    head = raw[:idx + 1]
    return decode_arena_stream_lines(head.decode("utf-8", "replace")), len(head)


class ArenaChatMonitor(BaseNetMonitor):
    """Живое состояние чата Arena из Network.* событий CDP."""

    CHAT_URL_SUBSTR = "/nextjs-api/stream/post-to-evaluation/"
    RESPONSE_MIME_SUBSTR = "text/event-stream"
    LOG_TAG = "arena_parser"

    def _reset_answer_state_locked(self):
        self._answer_text = ""
        self._finished = False
        self._counted_message = False

    def _decode_frames_partial(self, raw_bytes):
        return decode_arena_stream_partial(raw_bytes)

    def _decode_frames(self, raw_bytes):
        return decode_arena_stream_lines(raw_bytes.decode("utf-8", "replace"))

    def _answer_len_locked(self):
        return len(self._answer_text)

    def _apply_event(self, obj):
        prefix = obj.get("prefix")
        payload = obj.get("payload")
        if prefix == "a0":
            # append chunk
            if payload:
                self._answer_text += payload
                if not self._counted_message:
                    self._counted_message = True
                    self._assistant_message_count += 1
        elif prefix == "ad":
            # done
            try:
                meta = json.loads(payload)
                if meta.get("finishReason") == "stop":
                    self._finished = True
                    self._generating = False
                    self._message_status = "FINISHED"
            except Exception:
                pass

    def current_text(self):
        with self._lock:
            return self._answer_text

    def is_finished(self):
        with self._lock:
            return self._finished


# ---------------------------------------------------------------------------
# Парсер сайта
# ---------------------------------------------------------------------------
from parsers.parser_base import BaseSiteParser


class ArenaParser(BaseSiteParser):
    LOG_TAG = "arena_parser"
    WINDOW_URL_MATCH = "arena.ai"
    # ответ читается из сети → visibility spoof не нужен
    NEEDS_VISIBILITY_SPOOF = False

    _monitor = None
    _monitor_lock = threading.Lock()
    _monitor_next_retry = 0.0

    def _ensure_monitor(self):
        import time
        from browser.cdp_ws import CDPSession, find_page_ws_url
        with ArenaParser._monitor_lock:
            mon = ArenaParser._monitor
            try:
                if mon is not None and mon._cdp.is_alive():
                    return mon
            except Exception:
                pass
            now = time.time()
            if now < ArenaParser._monitor_next_retry:
                return None
            try:
                ws_url = find_page_ws_url(self.WINDOW_URL_MATCH)
                cdp = CDPSession(ws_url)
                new_mon = ArenaChatMonitor(cdp)
                if mon is not None:
                    new_mon._assistant_message_count = mon.assistant_message_count()
                    new_mon._chat_request_count = mon.chat_request_count()
                cdp.send_command("Network.enable")
                ArenaParser._monitor = new_mon
                print("[arena_parser] сетевой монитор подключён")
                return new_mon
            except Exception as e:
                ArenaParser._monitor_next_retry = now + 30.0
                print("[arena_parser] монитор недоступен (%s) — работаю только по DOM" % e)
                return None

    # --- DOM-хелперы (селекторы из arena_3_dom.json / ручного анализа) ---

    _JS_FIND_INPUT = r"""
        (function() {
            var ta = document.querySelector('textarea[name="message"]');
            return ta ? ta : null;
        })();
    """

    _JS_CLICK_SEND = r"""
        (function() {
            var ta = document.querySelector('textarea[name="message"]');
            if (!ta) return false;
            var form = ta.closest('form');
            if (!form) return false;
            var btn = form.querySelector('button[type="submit"], button[aria-label*="Send" i], button[aria-label*="Отправ" i]');
            if (btn) { btn.click(); return true; }
            return false;
        })();
    """

    _JS_GET_ANSWER = r"""
        (function() {
            // Ищем готовый ответ: контейнер с .prose и кнопкой Like
            var likeBtns = document.querySelectorAll('button[aria-label*="Like" i]');
            for (var i = 0; i < likeBtns.length; i++) {
                var container = likeBtns[i].closest('[data-code-block="true"], .prose, [class*="max-w-"]');
                if (container) {
                    // Берём текст до кнопки Like
                    var txt = container.innerText || container.textContent;
                    return txt.trim();
                }
            }
            return "";
        })();
    """

    _JS_COUNT_ANSWERS = r"""
        (function() {
            return document.querySelectorAll('button[aria-label*="Like" i]').length;
        })();
    """

    _JS_IS_GENERATING = r"""
        (function() {
            var stopBtn = document.querySelector('button[aria-label*="Stop" i], button[aria-label*="Остан" i]');
            return !!stopBtn;
        })();
    """

    # --- BaseSiteParser hooks ---

    def count_answers(self, driver):
        try:
            return int(driver.execute_script(self._JS_COUNT_ANSWERS) or 0)
        except Exception:
            return 0

    def answer_len(self, driver):
        mon = self._ensure_monitor()
        if mon is not None and mon.is_generating():
            return len(mon.current_text())
        try:
            txt = driver.execute_script(self._JS_GET_ANSWER) or ""
            return len(txt)
        except Exception:
            return 0

    def extract_answer(self, driver):
        # Сеть опережает DOM — если монитор жив, берём оттуда
        mon = self._ensure_monitor()
        if mon is not None and mon.is_generating():
            return mon.current_text()
        try:
            return driver.execute_script(self._JS_GET_ANSWER) or ""
        except Exception:
            return ""

    def find_input(self, driver):
        return driver.execute_script(self._JS_FIND_INPUT)

    def insert_input(self, driver, element, text):
        # Простая вставка через value + input event
        driver.execute_script("""
            var el = arguments[0];
            el.value = arguments[1];
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
        """, element, text)
        return True

    def submit(self, driver):
        return driver.execute_script(self._JS_CLICK_SEND)

    def is_generating(self, driver):
        mon = self._ensure_monitor()
        if mon is not None:
            return mon.is_generating()
        try:
            return bool(driver.execute_script(self._JS_IS_GENERATING))
        except Exception:
            return False

    def try_regenerate(self, driver):
        # На arena.ai нет явной кнопки регенерации в прямом чате
        return False


# module-level singleton + wrapper
PARSER = ArenaParser()


def send_message_and_get_response(driver, prompt, attachments=None, **kwargs):
    return PARSER.send_message_and_get_response(driver, prompt, attachments=attachments, **kwargs)