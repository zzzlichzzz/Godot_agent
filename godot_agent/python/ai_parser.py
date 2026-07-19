import time
import json
import re
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    JavascriptException,
    StaleElementReferenceException,
    WebDriverException,
)

from parser_base import (
    BaseSiteParser,
    _safe_execute,
    _escape_bbcode_py,
    _strip_code_fences,
    _extract_json_object,
    _escape_raw_newlines_in_strings,
    _remove_trailing_commas,
    parse_action_json,
    _looks_json_balanced,
)

# ---------------------------------------------------------------------------
# JS: извлечение последнего ответа модели.
# Всё завёрнуто в try/catch — скрипт НИКОГДА не должен кидать исключение
# наружу в Python, даже если разметка AI Studio внезапно поменялась.
# JSON action НЕ парсится в JS — сырой текст блока agent_action отдаётся
# в Python, где его гораздо проще "починить".
#
# ВАЖНО (фикс): блок размышлений модели ("Thoughts"/thinking) ИСКЛЮЧАЕТСЯ
# и из текста, и из поиска agent_action, и из замера длины.
# ---------------------------------------------------------------------------

# Общая JS-функция: является ли узел частью «размышлений».
# Если в будущем AI Studio поменяет разметку — добавь селектор сюда.
_JS_IS_THOUGHT = r"""
    function isThoughtNode(node) {
        try {
            var el = (node && node.nodeType === Node.ELEMENT_NODE) ? node
                     : (node ? node.parentElement : null);
            while (el && el !== document.body) {
                var tag = (el.tagName || '').toLowerCase();
                if (tag === 'ms-thought-chunk') return true;
                var cls = (el.className && el.className.toString) ? el.className.toString() : '';
                if (/thought|thinking/i.test(cls)) return true;
                if (el.getAttribute && (el.getAttribute('data-thought') ||
                    el.getAttribute('data-test-thought'))) return true;
                el = el.parentElement;
            }
        } catch (e) {}
        return false;
    }
"""

_THOUGHT_SELECTORS = (
    "ms-thought-chunk, [data-thought], [data-test-thought], "
    ".thought, .thoughts, .model-thoughts"
)

# Мысли + служебный «хром» реплики: шапка (автор Model + время 4:50 PM),
# кнопки и иконки. Без этого замер длины ответа считал шапку за текст
# (ожидание завершалось во время «размышлений» модели), а грубый
# фолбэк отдавал в чат пустое сообщение вида «Model 4:50 PM».
_CHROME_SELECTORS = (
    _THOUGHT_SELECTORS + ", "
    "mat-icon, button, time, "
    '[class*="turn-header" i], [class*="turn-footer" i], '
    '[class*="author" i], [class*="timestamp" i], [class*="actions" i]'
)

JS_EXTRACT_LAST_ANSWER = r"""try {""" + _JS_IS_THOUGHT + r"""
    function extractLastAnswer() {
        const modelTurns = document.querySelectorAll('[data-turn-role="Model"]');
        if (modelTurns.length === 0) return { text: '', actionRaw: null, error: null };
        const lastModelTurn = modelTurns[modelTurns.length - 1];
        const chunks = lastModelTurn.querySelectorAll('div[mssnapshotlink]');
        function escapeBBCode(text) {
            return text.replace(/[\[\]]/g, function(ch) {
                return ch === '[' ? '[lb]' : '[rb]';
            });
        }
        let capturedActionRaw = null; // берём ПОСЛЕДНИЙ найденный agent_action блок
        function walk(node, listDepth) {
            listDepth = listDepth || 0;
            try {
                if (isThoughtNode(node)) return '';
                if (node.nodeType === Node.TEXT_NODE) {
                    return escapeBBCode(node.textContent);
                }
                if (node.nodeType !== Node.ELEMENT_NODE) return '';
                const tag = node.tagName.toLowerCase();
                if (tag === 'ms-code-block') {
                    const lang = (node.getAttribute('data-test-language') || '').trim().toLowerCase();
                    const codeEl = node.querySelector('pre code') || node.querySelector('code');
                    const rawCode = codeEl ? (codeEl.textContent || codeEl.innerText || '') : '';
                    if (lang === 'agent_action') {
                        capturedActionRaw = rawCode; // последний найденный перезапишет предыдущий
                        return '\n[color=#888888]— агент предлагает действие (см. ниже) —[/color]\n';
                    }
                    const code = escapeBBCode(rawCode);
                    const header = '[bgcolor=#1f2430][color=#8ab4f8] ▸ ' + (lang ? escapeBBCode(lang) : 'код') + ' [/color][/bgcolor]\n';
                    return '\n' + header + '[bgcolor=#2b2b2b][code]' + code + '[/code][/bgcolor]\n';
                }
                if (['button', 'svg', 'mat-icon'].includes(tag)) return '';
                function collectChildren(node, allowedTags) {
                    let items = [];
                    function scan(n) {
                        for (const child of n.children) {
                            const t = child.tagName.toLowerCase();
                            if (allowedTags.includes(t)) {
                                items.push(child);
                            } else if (t === 'ms-cmark-node') {
                                scan(child);
                            }
                        }
                    }
                    scan(node);
                    return items;
                }
                if (tag === 'ol' || tag === 'ul') {
                    let out = '';
                    let idx = 1;
                    for (const li of collectChildren(node, ['li'])) {
                        const marker = (tag === 'ol') ? (idx + '. ') : '•  ';
                        out += marker + walk(li, listDepth + 1).trim() + '\n';
                        idx++;
                    }
                    if (listDepth > 0) {
                        out = '[indent]' + out.trim() + '[/indent]\n';
                    }
                    return out;
                }
                if (tag === 'table') {
                    let rows = [];
                    function collectRows(n) {
                        for (const child of n.children) {
                            const t = child.tagName.toLowerCase();
                            if (t === 'tr') {
                                rows.push(child);
                            } else if (['thead', 'tbody', 'tfoot', 'ms-cmark-node'].includes(t)) {
                                collectRows(child);
                            }
                        }
                    }
                    collectRows(node);
                    let out = '\n';
                    for (const tr of rows) {
                        const cells = collectChildren(tr, ['th', 'td']).map(function(c) {
                            return walk(c, listDepth).trim();
                        });
                        out += cells.join('\t') + '\n';
                    }
                    return out + '\n';
                }
                let inner = '';
                for (const child of node.childNodes) {
                    inner += walk(child, listDepth);
                }
                if (tag === 'strong') return '[b]' + inner + '[/b]';
                if (tag === 'em') return '[i]' + inner + '[/i]';
                if (node.classList && node.classList.contains('inline-code')) return '[code]' + inner + '[/code]';
                if (tag === 'li') return inner;
                if (['h1', 'h2', 'h3', 'h4'].includes(tag)) return '[b][font_size=20]' + inner + '[/font_size][/b]\n';
                if (tag === 'p') return inner + '\n';
                if (tag === 'hr') return '\n―――――――――――\n';
                if (tag === 'br') return '\n';
                return inner;
            } catch (innerErr) {
                return '';
            }
        }
        let fullText = '';
        try {
            if (chunks.length === 0) {
                const cmarkRoot = lastModelTurn.querySelector('ms-cmark-node.cmark-node') || lastModelTurn;
                fullText += walk(cmarkRoot) + '\n';
            } else {
                for (const chunk of chunks) {
                    if (isThoughtNode(chunk)) continue;
                    const cmarkRoot = chunk.querySelector('ms-cmark-node.cmark-node') || chunk;
                    fullText += walk(cmarkRoot) + '\n';
                }
            }
        } catch (e) {
            fullText = lastModelTurn.innerText || '';
        }
        fullText = fullText.replace(/\n{3,}/g, '\n\n').trim();
        // Страховка: сканируем все ms-code-block напрямую, если walk() что-то
        // пропустил из-за внутренних try/catch. Блоки в размышлениях ПРОПУСКАЕМ.
        if (capturedActionRaw === null) {
            const codeBlocks = lastModelTurn.querySelectorAll('ms-code-block');
            for (const block of codeBlocks) {
                if (isThoughtNode(block)) continue;
                const lang = (block.getAttribute('data-test-language') || '').trim().toLowerCase();
                if (lang === 'agent_action') {
                    const codeEl = block.querySelector('pre code') || block.querySelector('code');
                    if (codeEl) {
                        capturedActionRaw = codeEl.textContent || codeEl.innerText || '';
                    }
                }
            }
        }
        return { text: fullText, actionRaw: capturedActionRaw, error: null };
    }
    return extractLastAnswer();
} catch (outerErr) {
    return { text: '', actionRaw: null, error: String(outerErr && outerErr.message || outerErr) };
}"""

JS_COUNT_MODEL_TURNS = "return document.querySelectorAll('[data-turn-role=\"Model\"]').length;"

# Список селекторов-кандидатов "идёт генерация". Проверяем ВСЕ по очереди —
# если один селектор в UI студии сломается, остальные подстрахуют.
JS_IS_GENERATING = r"""try {
    if (document.querySelector('ms-run-button .spin')) return true;
    if (document.querySelector('ms-run-button .stoppable')) return true;
    const stopBtn = document.querySelector(
        'button[aria-label*="Stop" i], button[aria-label*="стоп" i], button[aria-label*="Останов" i]'
    );
    if (stopBtn) return true;
    if (document.querySelector('.loading-indicator, .thinking-indicator, [data-test-loading="true"]')) return true;
    return false;
} catch (e) {
    return false;
}"""

JS_GET_LAST_MODEL_TEXT_LENGTH = r"""try {
    const modelTurns = document.querySelectorAll('[data-turn-role="Model"]');
    if (modelTurns.length === 0) return 0;
    const last = modelTurns[modelTurns.length - 1];
    return (last.innerText || '').length;
} catch (e) {
    return -1;
}"""

# Длина ТОЛЬКО ответа (без блока размышлений). Клонируем реплику,
# вырезаем мысли и берём textContent (работает на отсоединённом узле,
# в отличие от innerText).
JS_GET_ANSWER_TEXT_LENGTH = r"""try {
    const turns = document.querySelectorAll('[data-turn-role="Model"]');
    if (turns.length === 0) return 0;
    const clone = turns[turns.length - 1].cloneNode(true);
    clone.querySelectorAll('""" + _CHROME_SELECTORS + r"""').forEach(function(n){ n.remove(); });
    return (clone.textContent || '').length;
} catch (e) {
    return -1;
}"""

# Хвост ОТВЕТА (без блока размышлений) для живой трансляции в панель.
JS_GET_ANSWER_PREVIEW = r"""try {
    const turns = document.querySelectorAll('[data-turn-role="Model"]');
    if (turns.length === 0) return '';
    const clone = turns[turns.length - 1].cloneNode(true);
    clone.querySelectorAll('""" + _CHROME_SELECTORS + r"""').forEach(function(n){ n.remove(); });
    const t = (clone.textContent || '').replace(/\s+/g, ' ').trim();
    return t.slice(-260);
} catch (e) {
    return '';
}"""

# ПЛАН Б: грубое извлечение ответа без форматирования. Клонируем реплику,
# вырезаем мысли, последний agent_action забираем напрямую из код-блоков,
# остальное отдаём как чистый textContent. Используется, когда основной
# структурный парсер вернул пустоту (например, AI Studio сменила разметку).
JS_EXTRACT_RAW_FALLBACK = r"""try {
    const turns = document.querySelectorAll('[data-turn-role="Model"]');
    if (turns.length === 0) return { text: '', actionRaw: null, error: 'no model turns' };
    const clone = turns[turns.length - 1].cloneNode(true);
    clone.querySelectorAll('""" + _CHROME_SELECTORS + r"""').forEach(function(n){ n.remove(); });
    let actionRaw = null;
    const blocks = clone.querySelectorAll('ms-code-block');
    for (const block of blocks) {
        const lang = (block.getAttribute('data-test-language') || '').trim().toLowerCase();
        if (lang === 'agent_action') {
            const codeEl = block.querySelector('pre code') || block.querySelector('code');
            if (codeEl) actionRaw = codeEl.textContent || '';
            block.remove();
        }
    }
    const text = (clone.textContent || '').trim();
    return { text: text, actionRaw: actionRaw, error: null };
} catch (e) {
    return { text: '', actionRaw: null, error: String(e && e.message || e) };
}"""

# Чем модель занята ПРЯМО СЕЙЧАС (для статуса в стиле Gemini): если ответ
# обрывается внутри последнего код-блока — значит, модель сейчас пишет код.
JS_GET_LIVE_ACTIVITY = r"""try {
    const turns = document.querySelectorAll('[data-turn-role="Model"]');
    if (turns.length === 0) return { code: false, lang: '' };
    const clone = turns[turns.length - 1].cloneNode(true);
    clone.querySelectorAll('""" + _CHROME_SELECTORS + r"""').forEach(function(n){ n.remove(); });
    const blocks = clone.querySelectorAll('ms-code-block');
    if (blocks.length === 0) return { code: false, lang: '' };
    const last = blocks[blocks.length - 1];
    const lang = (last.getAttribute('data-test-language') || '').trim().toLowerCase();
    const total = (clone.textContent || '').replace(/\s+/g, ' ').trim();
    const tail = (last.textContent || '').replace(/\s+/g, ' ').trim().slice(-30);
    const writing = tail.length > 0 && total.endsWith(tail);
    return { code: writing, lang: lang };
} catch (e) {
    return { code: false, lang: '' };
}"""


def get_model_turn_count(driver):
    return _safe_execute(driver, JS_COUNT_MODEL_TURNS, default=0) or 0


def is_generating(driver):
    return bool(_safe_execute(driver, JS_IS_GENERATING, default=False))


def get_last_model_text_length(driver):
    val = _safe_execute(driver, JS_GET_LAST_MODEL_TEXT_LENGTH, default=-1)
    return val if val is not None else -1


def get_answer_text_length(driver):
    val = _safe_execute(driver, JS_GET_ANSWER_TEXT_LENGTH, default=-1)
    return val if val is not None else -1


def get_answer_preview(driver):
    val = _safe_execute(driver, JS_GET_ANSWER_PREVIEW, default="")
    return val if isinstance(val, str) else ""


def get_live_activity(driver):
    val = _safe_execute(driver, JS_GET_LIVE_ACTIVITY, default=None)
    return val if isinstance(val, dict) else {"code": False, "lang": ""}


# Полный текст ответа (без «мыслей») с переносами строк — для живого стрима
# прямо в чат панели. textContent не даёт переносов, а innerText не работает
# на отсоединённом клоне — поэтому обходим DOM вручную.
JS_GET_ANSWER_STREAM = r"""try {
    const turns = document.querySelectorAll('[data-turn-role="Model"]');
    if (turns.length === 0) return '';
    const clone = turns[turns.length - 1].cloneNode(true);
    clone.querySelectorAll('""" + _CHROME_SELECTORS + r"""').forEach(function(n){ n.remove(); });
    const BLOCK = /^(P|DIV|LI|PRE|UL|OL|H1|H2|H3|H4|H5|TABLE|TR|SECTION|ARTICLE|MS-CODE-BLOCK)$/;
    function walk(node) {
        if (node.nodeType === 3) return node.data;
        if (node.nodeType !== 1) return '';
        if (node.tagName === 'BR') return '\n';
        let s = '';
        for (let i = 0; i < node.childNodes.length; i++) s += walk(node.childNodes[i]);
        if (BLOCK.test(node.tagName)) s += '\n';
        return s;
    }
    let text = walk(clone);
    text = text.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n');
    if (text.length > 30000) text = text.slice(0, 30000);
    return text.replace(/^\s+/, '');
} catch (e) {
    return '';
}"""


def get_answer_stream(driver):
    val = _safe_execute(driver, JS_GET_ANSWER_STREAM, default="")
    return val if isinstance(val, str) else ""


def extract_last_answer(driver):
    return _safe_execute(
        driver, JS_EXTRACT_LAST_ANSWER,
        default={"text": "", "actionRaw": None, "error": "execute_script failed"}
    )


# Шапка реплики в textContent: "Model 4:50 PM" / "User 12:03" в начале строки.
_TURN_HEADER_RE = re.compile(r"^\s*(?:Model|User)\s+\d{1,2}:\d{2}(?:\s*[APap]\.?[Mm]\.?)?\s*")


def _strip_turn_chrome(text: str) -> str:
    """Убирает шапку реплики (автор + время) из грубого textContent-фолбэка.
    Если после чистки ничего не осталось — ответ считается пустым и парсер
    продолжает ждать/перечитывать, а не шлёт в чат пустое сообщение."""
    cleaned = text or ""
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _TURN_HEADER_RE.sub("", cleaned, count=1)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Парсер AI Studio на базе общего менеджера парсинга (parser_base).
# Вся общая логика (ожидание ответа, план Б, разбор agent_action) — в
# BaseSiteParser; здесь только «где что лежит» на странице AI Studio.
# ---------------------------------------------------------------------------

_JS_FIND_INPUT = """
function findInput(root) {
    let nodes = [root];
    while (nodes.length > 0) {
        let node = nodes.shift();
        if (node.tagName === 'TEXTAREA') return node;
        if (node.shadowRoot) nodes.push(node.shadowRoot);
        for (let child of node.children) nodes.push(child);
    }
    return null;
}
return findInput(document.body);
"""

_JS_INSERT = """
let el = arguments[0];
el.focus();
el.value = arguments[1];
el.dispatchEvent(new Event('input', { bubbles: true }));
el.dispatchEvent(new Event('change', { bubbles: true }));
"""


class AiStudioParser(BaseSiteParser):
    """Google AI Studio: сайт-специфичная часть поверх BaseSiteParser."""

    LOG_TAG = "ai_parser"
    WINDOW_URL_MATCH = "aistudio.google.com"
    START_PHASE = "жду начала ответа"
    QUIET_PERIOD = 2.5
    POLL_INTERVAL = 0.25

    def count_answers(self, driver):
        return get_model_turn_count(driver)

    def answer_len(self, driver):
        return get_answer_text_length(driver)

    def answer_preview(self, driver):
        return get_answer_preview(driver)

    def answer_stream(self, driver):
        return get_answer_stream(driver)

    def is_generating(self, driver):
        return is_generating(driver)

    def get_live_activity(self, driver):
        return get_live_activity(driver)

    def extract_answer(self, driver):
        return extract_last_answer(driver)

    def extract_raw_fallback(self, driver):
        raw = _safe_execute(driver, JS_EXTRACT_RAW_FALLBACK, default=None) or {}
        return {
            "text": _strip_turn_chrome(raw.get("text") or ""),
            "actionRaw": raw.get("actionRaw"),
        }

    def find_input(self, driver):
        return driver.execute_script(_JS_FIND_INPUT)

    def insert_input(self, driver, el, prompt):
        driver.execute_script("arguments[0].value = '';", el)
        time.sleep(0.2)
        driver.execute_script(_JS_INSERT, el, prompt)

    def before_submit(self, driver, el):
        # «Толчок» Angular: пробел + backspace, чтобы поле точно заметило текст.
        time.sleep(1)
        try:
            el.send_keys(Keys.SPACE)
            el.send_keys(Keys.BACKSPACE)
        except StaleElementReferenceException:
            pass
        time.sleep(0.5)

    def submit(self, driver, el):
        el.send_keys(Keys.CONTROL, Keys.ENTER)


PARSER = AiStudioParser()


# --- Обёртки для совместимости со старым интерфейсом модуля ---

def extract_last_answer_robust(driver, retries=3, delay=1.5):
    return PARSER.extract_answer_robust(driver, retries=retries, delay=delay)


def wait_for_new_answer(driver, initial_model_count, timeout=900,
                        quiet_period=2.5, hard_quiet_period=45.0, poll_interval=0.25,
                        post_quiet_grace=6.0, progress_cb=None):
    return PARSER.wait_for_new_answer(
        driver, initial_model_count, timeout=timeout, quiet_period=quiet_period,
        hard_quiet_period=hard_quiet_period, poll_interval=poll_interval,
        post_quiet_grace=post_quiet_grace, progress_cb=progress_cb)


def send_message_and_get_response(driver, prompt, input_retries=3, progress_cb=None, cancel_cb=None):
    return PARSER.send_message_and_get_response(
        driver, prompt, input_retries=input_retries, progress_cb=progress_cb,
        cancel_cb=cancel_cb)
