# -*- coding: utf-8 -*-
"""Kimi (www.kimi.com) parser - v87.1 pilot.

Unlike qwen/deepseek/ai_parser, this parser does NOT read the answer from
the DOM. Instead it reads the model's answer directly from the network:
kimi.com answers POST .../ChatService/Chat with a Connect-RPC stream
(content-type application/connect+json) containing structured JSON events
such as:

  {"op": "set",    "mask": "block.text",         "block": {"id": "1", "text": {"content": "..."}}}
  {"op": "append", "mask": "block.text.content", "block": {"id": "1", "text": {"content": "..."}}}
  {"op": "set",    "mask": "message.status",     "message": {"id": "...", "status": "MESSAGE_STATUS_COMPLETED"}}

This is much more reliable than DOM/height heuristics (v86.19-27): each
event says explicitly what changed, and MESSAGE_STATUS_COMPLETED is an
explicit end-of-generation signal instead of a guess. Schema was reverse
engineered from two real HAR captures of www.kimi.com taken 2026-07-22
(one plain-text answer, one with a tool call + an ```agent_action code
fence) - see README_CHANGES.txt, v87.1, for details.

Selenium's execute_cdp_cmd cannot receive these push events, so a separate
raw WebSocket connection to the same browser debug port is used (cdp_ws.py).

DOM is still used for the parts network capture cannot help with: typing
the prompt into the input box and clicking send. Selectors below come from
HTML snippets of www.kimi.com supplied by the user on 2026-07-22 and are
BEST-EFFORT - they still need to be confirmed against the live site.
"""
import base64
import re
import threading
import time

from parser_base import BaseSiteParser, _safe_execute

from cdp_ws import (CDPSession, decode_connect_frames,
                    decode_connect_frames_partial, find_page_ws_url)

from net_monitor import BaseNetMonitor


# ---------------------------------------------------------------------------
# Extraction of the agent_action fence from already-assembled markdown text.
# Unlike other sites, this runs on plain text (no DOM/JS needed) because the
# network stream already delivers ready markdown, including the
# ```agent_action fence, verbatim.
# ---------------------------------------------------------------------------

_AGENT_ACTION_FENCE_RE = re.compile(r"```agent_action\s*\n(.*?)\n?```", re.DOTALL)
_DONE_MARKER_RE = re.compile(r"={2,}\s*DONE\s*={2,}", re.IGNORECASE)


def split_text_and_action(full_text):
    """Splits off the LAST ```agent_action fenced block from full_text and
    strips the ===DONE=== marker. Returns (text, action_raw_or_None)."""
    if not full_text:
        return full_text, None
    text = full_text
    action_raw = None
    matches = list(_AGENT_ACTION_FENCE_RE.finditer(text))
    if matches:
        m = matches[-1]
        action_raw = m.group(1)
        text = (text[:m.start()] + text[m.end():])
    text = _DONE_MARKER_RE.sub("", text).strip()
    return text, action_raw


# ---------------------------------------------------------------------------
# Live state assembled from Network.* events - see README_CHANGES.txt v87.1
# for the schema this is based on.
# ---------------------------------------------------------------------------

class KimiChatMonitor(BaseNetMonitor):
    """Tracks the live chat state of www.kimi.com purely from network
    events (no DOM access at all).

    v87.10: вся общая механика (живой стрим тела, защита от устаревших
    запросов, сбросы generating, дедлок-безопасное завершение, счётчик
    исходящих POST для confirm_sent) переехала в net_monitor.BaseNetMonitor и
    переиспользуется новыми парсерами. Здесь остался только формат Kimi:
    Connect-RPC кадры и схема событий block/message (см. шапку файла).
    """

    CHAT_URL_SUBSTR = "ChatService/Chat"
    RESPONSE_MIME_SUBSTR = "connect+json"
    LOG_TAG = "kimi_parser"

    def _reset_answer_state_locked(self):
        self._blocks = {}
        self._block_order = []
        self._message_status = None
        self._current_message_id = None

    def _decode_frames_partial(self, raw_bytes):
        frames, consumed = decode_connect_frames_partial(raw_bytes)
        return [obj for _flags, obj in frames], consumed

    def _decode_frames(self, raw_bytes):
        return [obj for _flags, obj in decode_connect_frames(raw_bytes)]

    def _answer_len_locked(self):
        return sum(len(v) for v in self._blocks.values())

    def _apply_event(self, obj):
        if not isinstance(obj, dict):
            return
        op = obj.get("op")
        msg = obj.get("message")
        if isinstance(msg, dict):
            role = msg.get("role")
            status = msg.get("status")
            mid = msg.get("id")
            # The initial "set message" event carries role+id for a new
            # assistant message; later "set message.status" events for the
            # SAME message only repeat id+status, without role - so a
            # message is tracked as "assistant" once its id has been seen
            # with role == "assistant", not by re-checking role every time.
            if role == "assistant" and mid and mid != self._current_message_id:
                self._current_message_id = mid
                self._assistant_message_count += 1
            if status and mid and mid == self._current_message_id:
                self._message_status = status
                self._generating = (status == "MESSAGE_STATUS_GENERATING")
        block = obj.get("block")
        if isinstance(block, dict):
            bid = block.get("id")
            text_obj = block.get("text")
            if block.get("tool") is None and isinstance(text_obj, dict):
                content = text_obj.get("content")
                if content is not None:
                    if op == "set" or bid not in self._blocks:
                        self._blocks[bid] = content
                        if bid not in self._block_order:
                            self._block_order.append(bid)
                    else:
                        self._blocks[bid] = self._blocks.get(bid, "") + content

    def current_text(self):
        with self._lock:
            def _key(bid):
                try:
                    return int(bid)
                except Exception:
                    return 0
            ordered = sorted(self._block_order, key=_key)
            return "".join(self._blocks[b] for b in ordered)


# ---------------------------------------------------------------------------
# DOM-side: only used for typing the prompt and clicking send. Selectors are
# best-effort from the HTML snippets supplied 2026-07-22, need live checking.
# ---------------------------------------------------------------------------

JS_FIND_INPUT = r"""
return document.querySelector('div.chat-input-editor[contenteditable="true"]');
"""

JS_SET_INPUT = r"""
var el = arguments[0], text = arguments[1];
el.focus();
document.execCommand('selectAll', false, null);
document.execCommand('insertText', false, text);
"""

JS_FIND_SEND_BUTTON = r"""
var el = document.querySelector('div.send-button-container');
if (el && !el.classList.contains('disabled')) return el;
return null;
"""


class KimiParser(BaseSiteParser):
    """www.kimi.com: DOM only for typing/sending, network (CDP) for reading."""

    LOG_TAG = "kimi_parser"
    WINDOW_URL_MATCH = "kimi.com"
    START_PHASE = u"\u043c\u043e\u0434\u0435\u043b\u044c \u0434\u0443\u043c\u0430\u0435\u0442\u2026"
    QUIET_PERIOD = 4.0
    POLL_INTERVAL = 0.3

    _monitor = None
    _monitor_lock = threading.Lock()

    def _ensure_monitor(self, driver):
        with KimiParser._monitor_lock:
            old = KimiParser._monitor
            if old is not None:
                # v87.7: раньше синглтон возвращался без проверки живости:
                # если CDP-соединение умерл�� (тишина в сокете до v87.7,
                # перезапуск/закрытие вкладки, обрыв сокета), монитор
                # навсегда глох (ни событий, ни тел) до перезапуска сервера.
                if old._cdp.is_alive():
                    return old
                print("[kimi_parser] CDP-сессия мертва - переподключаюсь к вкладке kimi.com...")
                try:
                    old._cdp.close()
                except Exception:
                    pass
                KimiParser._monitor = None
            ws_url = find_page_ws_url("kimi.com")
            if not ws_url:
                raise Exception(
                    "kimi.com tab not found for CDP attach (Network domain "
                    "needed to read the streamed answer).")
            cdp = CDPSession(ws_url)
            # v87.7: подписки монитора регистрируются ДО Network.enable -
            # раньше события, пришедшие между enable и созданием монитора,
            # молча терялись.
            monitor = KimiChatMonitor(cdp)
            cdp.send_command("Network.enable")
            if old is not None:
                # переносим накопленные счётчики, чтобы initial_count в
                # идущем ожидании не «прыгал» после переподключения.
                monitor._assistant_message_count = old.assistant_message_count()
                monitor._chat_request_count = old.chat_request_count()
            KimiParser._monitor = monitor
            return monitor

    def count_answers(self, driver):
        return self._ensure_monitor(driver).assistant_message_count()

    def answer_len(self, driver):
        return len(self._ensure_monitor(driver).current_text())

    def answer_stream(self, driver):
        return self._ensure_monitor(driver).current_text()

    def is_generating(self, driver):
        return self._ensure_monitor(driver).is_generating()

    def extract_answer(self, driver):
        monitor = self._ensure_monitor(driver)
        full_text = monitor.current_text()
        text, action_raw = split_text_and_action(full_text)
        return {"text": text, "actionRaw": action_raw, "error": None}

    def find_input(self, driver):
        return _safe_execute(driver, JS_FIND_INPUT, default=None)

    def insert_input(self, driver, el, prompt):
        driver.execute_script(JS_SET_INPUT, el, prompt)

    def submit(self, driver, el):
        # v87.7: снимок счётчика исходящих POST ДО клика: confirm_sent считает
        # сообщение ушедшим, если после клика появился новый POST к
        # ChatService/Chat - это надёжнее, чем гадать по остатку текста
        # в поле ввода (ложные «не ушло» порождали реальные дубли POST,
        # обрывавшие чтение настоящего ответа - гипотеза v87.6
        # подтверждена разбором кода: см. README v87.7).
        mon = KimiParser._monitor
        self._req_count_before_send = (
            mon.chat_request_count() if mon is not None else None)
        btn = _safe_execute(driver, JS_FIND_SEND_BUTTON, default=None)
        if btn is not None:
            driver.execute_script("arguments[0].click();", btn)
        else:
            from selenium.webdriver.common.keys import Keys
            el.send_keys(Keys.ENTER)

    def _input_leftover(self, driver, el):
        """текст, оставшийся в поле ввода (пусто => сообщение отправлено).
        v87.3: _safe_execute НЕ умеет передавать аргументы в execute_script (и
eго retries позиционно перекрывается WebElement'ом, если его передать
после script) - для скриптов с arguments[0] надо звать driver.execute_script(...)
наврямую, как в deepseek_parser.py._input_leftover."""
        try:
            val = driver.execute_script(
                "var e=arguments[0];"
                " return (e.innerText||e.textContent||'').trim();", el)
        except Exception:
            val = ""
        return (val or "").strip()

    def confirm_sent(self, driver, el):
        # v87.7: главный критерий «ушло/не ушло» - СЕТЬ, а не DOM:
        # если после клика появился новый POST к ChatService/Chat
        # (Network.requestWillBeSent), сообщение точно отправлено -
        # даже если сайт ещё не очистил поле ввода (именно ложные
        # «не ушло» вызывали повторные реальные POST - гипотеза v87.6).
        # DOM-проверка остаётся запасным критерием (если монитора нет).
        before = getattr(self, "_req_count_before_send", None)
        deadline = time.time() + 5.0
        while True:
            mon = KimiParser._monitor
            if (before is not None and mon is not None
                    and mon.chat_request_count() > before):
                return True
            leftover = self._input_leftover(driver, el)
            if not leftover:
                return True
            if time.time() >= deadline:
                break
            time.sleep(0.3)
        # v87.6: диагностика - видим, что именно осталось в поле ввода,
        # когда confirm_sent решает, что сообщение не ушло и надо повторить
        # отправку (повтор теперь возможен только если за 5с не было
        # НИ нового POST в сети, НИ очистки поля - т.е. реальный сбой).
        print("[kimi_parser] confirm_sent: после отправки в поле осталось: %r (%d симв.), новых POST не было - считаю, что не ушло"
              % (leftover[:120], len(leftover)))
        return False


PARSER = KimiParser()


# --- Модульные обёртки для main.py/selfcheck.py: они вызывают эти имена
# На САСАМОМ модуле (как sites.get_parser_module() возвращает модуль, а не
# экземпляр класса), точно так же, как в deepseek_parser.py/ai_parser.py/
# qwen_parser.py. Из-за отсутствия этих обёрток в v87.1 падал send_message_and_
# get_response - исправлено в v87.2.

def count_answers(driver):
    return PARSER.count_answers(driver)


def answer_len(driver):
    return PARSER.answer_len(driver)


def answer_stream(driver):
    return PARSER.answer_stream(driver)


def is_generating(driver):
    return PARSER.is_generating(driver)


def extract_answer(driver):
    return PARSER.extract_answer(driver)


def wait_for_new_answer(driver, initial_count, timeout=900, quiet_period=4.0,
                        hard_quiet_period=45.0, poll_interval=0.3,
                        post_quiet_grace=6.0, progress_cb=None):
    return PARSER.wait_for_new_answer(
        driver, initial_count, timeout=timeout, quiet_period=quiet_period,
        hard_quiet_period=hard_quiet_period, poll_interval=poll_interval,
        post_quiet_grace=post_quiet_grace, progress_cb=progress_cb)


def send_message_and_get_response(driver, prompt, input_retries=3, progress_cb=None, cancel_cb=None, prefer_url=None):
    return PARSER.send_message_and_get_response(
        driver, prompt, input_retries=input_retries, progress_cb=progress_cb,
        cancel_cb=cancel_cb, prefer_url=prefer_url)
