# -*- coding: utf-8 -*-
"""Парсер сайта Qwen (chat.qwen.ai) — ЗАГОТОВКА (v71).

Интерфейс модуля тот же, что у ai_parser/deepseek_parser:
  send_message_and_get_response(driver, prompt, ...) -> {"text", "action"}

ВАЖНО: селекторы ниже ПРЕДПОЛОЖИТЕЛЬНЫЕ — они не проверялись на реальной
странице chat.qwen.ai. Открой сайт, проверь DOM (F12) и уточни селекторы
ответа и поля ввода. Каркас (ожидание ответа, отправка, ретраи) рабочий.
"""
import time

from selenium.webdriver.common.keys import Keys

from parser_base import BaseSiteParser, _safe_execute

_BLOCKS_JS = r"""
function __qwenBlocks() {
    var sels = [
        'div.markdown-content-container',
        'div[class*="assistant"] div[class*="markdown"]',
        'div[class*="message"] div[class*="markdown"]',
        'div[class*="markdown"]'
    ];
    for (var s = 0; s < sels.length; s++) {
        var found = [];
        var all = document.querySelectorAll(sels[s]);
        for (var i = 0; i < all.length; i++) {
            var el = all[i];
            try {
                if (el.closest('[class*="think"], [class*="reasoning"]')) continue;
                if (el.closest('[class*="user-message"], [class*="user_message"]')) continue;
                if (el.parentElement && el.parentElement.closest(sels[s])) continue;
            } catch (e) {}
            found.push(el);
        }
        if (found.length) return found;
    }
    return [];
}
"""

JS_COUNT_ANSWERS = _BLOCKS_JS + "return __qwenBlocks().length;"
JS_ANSWER_LEN = _BLOCKS_JS + "var b = __qwenBlocks(); return b.length ? (b[b.length-1].innerText || '').length : -1;"
JS_ANSWER_TEXT = _BLOCKS_JS + "var b = __qwenBlocks(); return b.length ? (b[b.length-1].innerText || '') : '';"
JS_IS_GENERATING = ("return !!document.querySelector('button[aria-label*=\"Stop\"],"
                    " [class*=\"stop\"] button, button[class*=\"stop\"]');")
JS_FIND_INPUT = ("return document.querySelector('textarea#chat-input')"
                 " || document.querySelector('textarea[placeholder]')"
                 " || document.querySelector('textarea')"
                 " || document.querySelector('[contenteditable=\"true\"]');")
JS_SET_INPUT = ("var el = arguments[0], text = arguments[1];"
                " if (el.tagName && el.tagName.toLowerCase() === 'textarea') {"
                "   var proto = Object.getPrototypeOf(el);"
                "   var desc = Object.getOwnPropertyDescriptor(proto, 'value');"
                "   if (desc && desc.set) { desc.set.call(el, text); } else { el.value = text; }"
                "   el.dispatchEvent(new Event('input', {bubbles: true}));"
                " } else {"
                "   el.focus(); el.innerText = text;"
                "   el.dispatchEvent(new InputEvent('input', {bubbles: true}));"
                " }")
JS_DISPATCH_ENTER = ("var el = arguments[0];"
                     " var ev = new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter',"
                     " keyCode: 13, which: 13, bubbles: true});"
                     " el.dispatchEvent(ev);")
JS_CLICK_SEND = ("var b = document.querySelector('button[id*=\"send\"],"
                 " button[class*=\"send\"], button[type=\"submit\"]');"
                 " if (b) { b.click(); return true; } return false;")


def count_answers(driver):
    return _safe_execute(driver, JS_COUNT_ANSWERS, default=0) or 0


def answer_len(driver):
    val = _safe_execute(driver, JS_ANSWER_LEN, default=-1)
    return val if val is not None else -1


def answer_stream(driver):
    val = _safe_execute(driver, JS_ANSWER_TEXT, default="")
    return val if isinstance(val, str) else ""


def answer_preview(driver):
    return answer_stream(driver)[-160:]


def is_generating(driver):
    return bool(_safe_execute(driver, JS_IS_GENERATING, default=False))


def extract_answer(driver):
    text = answer_stream(driver)
    if not text:
        return {"text": "", "actionRaw": None, "error": "пустой ответ — заготовка qwen: уточни селекторы"}
    return {"text": text, "actionRaw": None, "error": None}


class QwenParser(BaseSiteParser):
    """Qwen: сайт-специфичная часть поверх BaseSiteParser (ЗАГОТОВКА)."""

    LOG_TAG = "qwen_parser"
    WINDOW_URL_MATCH = "chat.qwen.ai"
    START_PHASE = "модель думает…"
    QUIET_PERIOD = 4.0
    POLL_INTERVAL = 0.3

    def count_answers(self, driver):
        return count_answers(driver)

    def answer_len(self, driver):
        return answer_len(driver)

    def answer_preview(self, driver):
        return answer_preview(driver)

    def answer_stream(self, driver):
        return answer_stream(driver)

    def is_generating(self, driver):
        return is_generating(driver)

    def extract_answer(self, driver):
        return extract_answer(driver)

    def find_input(self, driver):
        return driver.execute_script(JS_FIND_INPUT)

    def insert_input(self, driver, el, prompt):
        driver.execute_script(JS_SET_INPUT, el, prompt)

    def before_submit(self, driver, el):
        time.sleep(0.4)

    def submit(self, driver, el):
        el.send_keys(Keys.ENTER)

    def _input_leftover(self, driver, el):
        try:
            val = driver.execute_script(
                "var el = arguments[0];"
                " if (el.tagName && el.tagName.toLowerCase() === 'textarea') return el.value;"
                " return el.innerText;", el)
        except Exception:
            val = ""
        return (val or "").strip()

    def after_submit(self, driver, el):
        time.sleep(1.2)
        if not self._input_leftover(driver, el):
            return
        try:
            driver.execute_script(JS_DISPATCH_ENTER, el)
        except Exception:
            pass
        time.sleep(1.0)
        if not self._input_leftover(driver, el):
            return
        _safe_execute(driver, JS_CLICK_SEND, default=False)
        time.sleep(1.0)

    def confirm_sent(self, driver, el):
        return not self._input_leftover(driver, el)


PARSER = QwenParser()


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
