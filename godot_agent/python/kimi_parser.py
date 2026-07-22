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

from cdp_ws import CDPSession, decode_connect_frames, find_page_ws_url


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

class KimiChatMonitor:
    """Tracks the live chat state of www.kimi.com purely from network
    events (no DOM access at all)."""

    CHAT_URL_SUBSTR = "ChatService/Chat"

    def __init__(self, cdp):
        self._cdp = cdp
        self._lock = threading.Lock()
        self._active_request_id = None
        self._blocks = {}
        self._block_order = []
        self._message_status = None
        self._current_message_id = None
        self._assistant_message_count = 0
        self._generating = False
        cdp.on_event("Network.responseReceived", self._on_response_received)
        cdp.on_event("Network.loadingFinished", self._on_loading_finished)

    def _on_response_received(self, params):
        try:
            resp = params.get("response") or {}
            url = resp.get("url") or ""
            mime = resp.get("mimeType") or ""
        except Exception:
            return
        if self.CHAT_URL_SUBSTR in url and "connect+json" in mime:
            with self._lock:
                self._active_request_id = params.get("requestId")
                self._generating = True
                self._blocks = {}
                self._block_order = []
                self._message_status = None
                self._current_message_id = None

    def _on_loading_finished(self, params):
        req_id = params.get("requestId")
        with self._lock:
            if req_id != self._active_request_id:
                return
        try:
            body = self._cdp.send_command("Network.getResponseBody", {"requestId": req_id})
        except Exception as e:
            print("[kimi_parser] Network.getResponseBody failed: %s" % e)
            return
        raw = body.get("body") or ""
        if body.get("base64Encoded"):
            try:
                raw_bytes = base64.b64decode(raw)
            except Exception as e:
                print("[kimi_parser] could not base64-decode response body: %s" % e)
                return
        else:
            raw_bytes = raw.encode("utf-8")
        frames = decode_connect_frames(raw_bytes)
        with self._lock:
            for _flags, obj in frames:
                self._apply_event(obj)
            self._active_request_id = None

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

    def is_generating(self):
        with self._lock:
            return bool(self._generating or self._active_request_id is not None)

    def assistant_message_count(self):
        with self._lock:
            return self._assistant_message_count

    def message_status(self):
        with self._lock:
            return self._message_status


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
            if KimiParser._monitor is not None:
                return KimiParser._monitor
            ws_url = find_page_ws_url("kimi.com")
            if not ws_url:
                raise Exception(
                    "kimi.com tab not found for CDP attach (Network domain "
                    "needed to read the streamed answer).")
            cdp = CDPSession(ws_url)
            cdp.send_command("Network.enable")
            monitor = KimiChatMonitor(cdp)
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
        btn = _safe_execute(driver, JS_FIND_SEND_BUTTON, default=None)
        if btn is not None:
            driver.execute_script("arguments[0].click();", btn)
        else:
            from selenium.webdriver.common.keys import Keys
            el.send_keys(Keys.ENTER)

    def confirm_sent(self, driver, el):
        time.sleep(0.3)
        val = _safe_execute(
            driver,
            "var e=arguments[0]; return (e.innerText||e.textContent||'').trim();",
            el, default="")
        return not bool((val or "").strip())
