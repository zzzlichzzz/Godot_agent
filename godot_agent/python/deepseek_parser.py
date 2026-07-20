# -*- coding: utf-8 -*-
"""Парсер сайта DeepSeek (chat.deepseek.com).

Наследник общего менеджера парсинга (parser_base.BaseSiteParser).
Интерфейс модуля тот же, что у ai_parser (Google AI Studio):
  send_message_and_get_response(driver, prompt, progress_cb) ->
      {"text": <BBCode-текст ответа>, "action": <dict agent_action | None>}

Особенности DeepSeek:
  - ответ модели: div.ds-markdown.ds-assistant-message-main-content;
  - блок размышлений — div.ds-markdown ВНУТРИ .ds-think-content и БЕЗ класса
    ds-assistant-message-main-content, поэтому исключается сам собой;
  - поле ввода — textarea (React): значение ставим через нативный сеттер
    + событие input, иначе React не увидит текст;
  - отправка — Enter (текст с переносами вставляем через JS, поэтому
    Enter безопасен); запасной путь — клик по кнопке отправки;
  - классы вида _27c9245/fbb737a4 — хеши, они меняются при обновлениях
    сайта — опираемся только на стабильные ds-* имена дизайн-системы.
"""
import time

from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException

from parser_base import (
    BaseSiteParser,
    _safe_execute,
    _looks_json_balanced,
    _extract_json_object,
    _strip_code_fences,
    parse_action_json,
)

ANSWER_SEL = "div.ds-markdown.ds-assistant-message-main-content"

# Универсальный сборщик блоков ответа. У «думающих» моделей DeepSeek
# класс основного контента может ОТЛИЧАТЬСЯ от ds-assistant-message-main-content
# (из-за этого агент «вечно думал», хотя ответ уже был на странице),
# поэтому берём ВСЕ верхнеуровневые div.ds-markdown, исключая блок
# «размышлений» и вложенные дубликаты.
_BLOCKS_JS = r"""
function __answerBlocks() {
    var out = [];
    var all = document.querySelectorAll('div.ds-markdown');
    for (var i = 0; i < all.length; i++) {
        var el = all[i];
        try {
            if (el.closest('.ds-think-content, [class*="think-content"], [class*="thinking"]')) continue;
            if (el.parentElement && el.parentElement.closest('div.ds-markdown')) continue;
        } catch (e) {}
        out.push(el);
    }
    return out;
}
"""

JS_COUNT_ANSWERS = _BLOCKS_JS + "return __answerBlocks().length;"

JS_ANSWER_LEN = _BLOCKS_JS + """try {
    var b = __answerBlocks();
    if (!b.length) return 0;
    return (b[b.length - 1].textContent || '').length;
} catch (e) { return -1; }"""

JS_ANSWER_PREVIEW = _BLOCKS_JS + r"""try {
    var b = __answerBlocks();
    if (!b.length) return '';
    var t = (b[b.length - 1].textContent || '').replace(/\s+/g, ' ').trim();
    return t.slice(-260);
} catch (e) { return ''; }"""

JS_ANSWER_STREAM = _BLOCKS_JS + """try {
    var b = __answerBlocks();
    if (!b.length) return '';
    var t = b[b.length - 1].innerText || b[b.length - 1].textContent || '';
    if (t.length > 30000) t = t.slice(0, 30000);
    return t;
} catch (e) { return ''; }"""

# Признак «идёт генерация»: кнопка отправки превращается в «стоп».
# Надёжного стабильного класса нет — это только подстраховка,
# основной критерий завершения — стабилизация длины текста ответа.
JS_IS_GENERATING = """try {
    if (document.querySelector('div[role="button"][aria-label*="Stop" i], div[role="button"][aria-label*="стоп" i], button[aria-label*="Stop" i]')) return true;
    if (document.querySelector('div[role="button"].ds-button--primary .ds-icon rect')) return true;
    return false;
} catch (e) { return false; }"""

JS_EXTRACT = _BLOCKS_JS + r"""try {
    var blocks = __answerBlocks();
    if (!blocks.length) return { text: '', actionRaw: null, error: null };
    var root = blocks[blocks.length - 1];
    var actionRaw = null;
    function esc(t) {
        return t.replace(/[\[\]]/g, function (ch) { return ch === '[' ? '[lb]' : '[rb]'; });
    }
    function codeLang(pre) {
        try {
            var wrap = pre.closest('[class*="code-block"]') || pre.parentElement;
            if (wrap && wrap !== pre) {
                var banner = wrap.querySelector('[class*="banner"], [class*="header"], [class*="lang"]');
                if (banner) {
                    var m = (banner.textContent || '').trim().toLowerCase().match(/[a-z0-9_+#-]+/);
                    if (m) return m[0];
                }
            }
            var code = pre.querySelector('code');
            if (code && code.className) {
                var m2 = String(code.className).match(/language-([a-z0-9_+#-]+)/i);
                if (m2) return m2[1].toLowerCase();
            }
        } catch (e) {}
        return '';
    }
    function walk(node) {
        try {
            if (node.nodeType === 3) return esc(node.textContent);
            if (node.nodeType !== 1) return '';
            var tag = node.tagName.toLowerCase();
            if (tag === 'svg' || tag === 'button' || tag === 'style' || tag === 'script') return '';
            if (tag === 'pre') {
                var codeEl = node.querySelector('code');
                var raw = (codeEl || node).textContent || '';
                var lang = codeLang(node);
                var head = raw.trim();
                if (lang === 'agent_action' || (head.charAt(0) === '{' && head.indexOf('"action"') !== -1)) {
                    actionRaw = raw;
                    return '\n[color=#888888]— агент предлагает действие (см. ниже) —[/color]\n';
                }
                var header = '[bgcolor=#1f2430][color=#8ab4f8] ▸ ' + (lang ? esc(lang) : 'код') + ' [/color][/bgcolor]\n';
                return '\n' + header + '[bgcolor=#2b2b2b][code]' + esc(raw) + '[/code][/bgcolor]\n';
            }
            if (tag === 'ol' || tag === 'ul') {
                var out = '';
                var idx = 1;
                for (var i = 0; i < node.children.length; i++) {
                    var li = node.children[i];
                    if (li.tagName.toLowerCase() !== 'li') continue;
                    out += (tag === 'ol' ? (idx + '. ') : '•  ') + walk(li).trim() + '\n';
                    idx++;
                }
                return out + '\n';
            }
            var inner = '';
            for (var j = 0; j < node.childNodes.length; j++) inner += walk(node.childNodes[j]);
            if (tag === 'strong' || tag === 'b') return '[b]' + inner + '[/b]';
            if (tag === 'em' || tag === 'i') return '[i]' + inner + '[/i]';
            if (tag === 'code') {
                var rawInline = node.textContent || '';
                var headInline = rawInline.trim();
                if (headInline.charAt(0) === '{' && headInline.indexOf('"action"') !== -1) {
                    actionRaw = rawInline;
                    return '\n[color=#888888]— агент предлагает действие (см. ниже) —[/color]\n';
                }
                return '[code]' + inner + '[/code]';
            }
            if (tag === 'h1' || tag === 'h2' || tag === 'h3' || tag === 'h4') return '[b][font_size=20]' + inner + '[/font_size][/b]\n';
            if (tag === 'p') return inner + '\n';
            if (tag === 'br') return '\n';
            if (tag === 'hr') return '\n―――――――――――\n';
            if (tag === 'li') return inner;
            if (tag === 'table') { return '\n' + esc(node.innerText || '') + '\n'; }
            return inner;
        } catch (e) { return ''; }
    }
    var text = walk(root).replace(/\n{3,}/g, '\n\n').trim();
    return { text: text, actionRaw: actionRaw, error: null };
} catch (e) {
    return { text: '', actionRaw: null, error: String(e && e.message || e) };
}""".replace("__SEL__", ANSWER_SEL)

JS_FIND_INPUT = """
return document.querySelector('#chat-input')
    || document.querySelector('textarea[name="search"]')
    || document.querySelector('textarea');
"""

# React-совместимая вставка текста: нативный сеттер value + событие input.
JS_SET_INPUT = """
var el = arguments[0], text = arguments[1];
var proto = (el.tagName === 'TEXTAREA') ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
var d = Object.getOwnPropertyDescriptor(proto, 'value');
if (d && d.set) { d.set.call(el, text); } else { el.value = text; }
el.dispatchEvent(new Event('input', { bubbles: true }));
el.dispatchEvent(new Event('change', { bubbles: true }));
el.focus();
"""

# Синтетический Enter (keydown/keypress/keyup). React вешает обработчики на
# корень документа, поэтому bubbles обязателен. Это запасной путь на случай,
# если реальный Enter из Selenium не привёл к отправке.
JS_DISPATCH_ENTER = """
var el = arguments[0];
el.focus();
var opts = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
             bubbles: true, cancelable: true };
el.dispatchEvent(new KeyboardEvent('keydown', opts));
el.dispatchEvent(new KeyboardEvent('keypress', opts));
el.dispatchEvent(new KeyboardEvent('keyup', opts));
return true;
"""

# Клик по кнопке отправки (круглая кнопка со стрелкой вверх): полная
# последовательность pointer/mouse-событий — голый .click() React-кнопка
# на div[role="button"] может игнорировать.
JS_CLICK_SEND = """
var btns = document.querySelectorAll('div[role="button"].ds-button--primary.ds-button--circle');
for (var i = btns.length - 1; i >= 0; i--) {
    var b = btns[i];
    if (String(b.className).indexOf('ds-button--disabled') !== -1) continue;
    var r = b.getBoundingClientRect();
    var opts = { bubbles: true, cancelable: true, view: window, button: 0,
                 clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 };
    try { b.dispatchEvent(new PointerEvent('pointerdown', opts)); } catch (e) {}
    b.dispatchEvent(new MouseEvent('mousedown', opts));
    try { b.dispatchEvent(new PointerEvent('pointerup', opts)); } catch (e) {}
    b.dispatchEvent(new MouseEvent('mouseup', opts));
    b.dispatchEvent(new MouseEvent('click', opts));
    return true;
}
return false;
"""


def count_answers(driver):
    return _safe_execute(driver, JS_COUNT_ANSWERS, default=0) or 0


def answer_len(driver):
    val = _safe_execute(driver, JS_ANSWER_LEN, default=-1)
    return val if val is not None else -1


def answer_preview(driver):
    val = _safe_execute(driver, JS_ANSWER_PREVIEW, default="")
    return val if isinstance(val, str) else ""


def answer_stream(driver):
    val = _safe_execute(driver, JS_ANSWER_STREAM, default="")
    return val if isinstance(val, str) else ""


def is_generating(driver):
    return bool(_safe_execute(driver, JS_IS_GENERATING, default=False))


def extract_answer(driver):
    return _safe_execute(
        driver, JS_EXTRACT,
        default={"text": "", "actionRaw": None, "error": "execute_script failed"}
    )


class DeepSeekParser(BaseSiteParser):
    """DeepSeek: сайт-специфичная часть поверх BaseSiteParser."""

    LOG_TAG = "deepseek_parser"
    WINDOW_URL_MATCH = "chat.deepseek.com"
    START_PHASE = "модель думает…"  # пока модель «думает», блока ответа ещё нет
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
        # React-совместимая вставка: нативный сеттер value + событие input.
        driver.execute_script(JS_SET_INPUT, el, prompt)

    def before_submit(self, driver, el):
        time.sleep(0.4)

    def submit(self, driver, el):
        el.send_keys(Keys.ENTER)

    def _input_leftover(self, driver, el):
        """Текст, оставшийся в поле ввода (пусто => сообщение отправлено)."""
        try:
            val = driver.execute_script("return arguments[0].value;", el)
        except Exception:
            val = _safe_execute(
                driver,
                "var el = document.querySelector('#chat-input')"
                " || document.querySelector('textarea');"
                " return el ? el.value : '';",
                default="")
        return (val or "").strip()

    def after_submit(self, driver, el):
        # Ступенчатая гарантия отправки: после каждой попытки проверяем,
        # что поле ввода очистилось (значит, сообщение реально ушло).
        # 1) реальный Enter -> 2) синтетический Enter -> 3) клик по кнопке.
        time.sleep(1.2)
        if not self._input_leftover(driver, el):
            return
        self._log("Enter не отправил сообщение — пробую синтетический Enter…")
        try:
            driver.execute_script(JS_DISPATCH_ENTER, el)
        except Exception as e:
            self._log("синтетический Enter не удался: %s" % e)
        time.sleep(1.0)
        if not self._input_leftover(driver, el):
            self._log("сообщение отправлено синтетическим Enter.")
            return
        self._log("пробую клик по кнопке отправки…")
        clicked = _safe_execute(driver, JS_CLICK_SEND, default=False)
        time.sleep(1.0)
        if not self._input_leftover(driver, el):
            self._log("сообщение отправлено кликом по кнопке.")
            return
        self._log("ВНИМАНИЕ: текст всё ещё в поле ввода (клик=%s) — "
                  "сообщение могло не отправиться." % clicked)

    def confirm_sent(self, driver, el):
        # Сообщение считаем отправленным, только если поле ввода очистилось.
        return not self._input_leftover(driver, el)


PARSER = DeepSeekParser()


# --- Обёртки для совместимости со старым интерфейсом модуля ---

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
