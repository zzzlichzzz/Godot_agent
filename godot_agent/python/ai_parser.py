import time
import json
import re

from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    JavascriptException,
    StaleElementReferenceException,
    WebDriverException,
)

# ---------------------------------------------------------------------------
# JS: извлечение последнего ответа модели.
# Всё завёрнуто в try/catch — скрипт НИКОГДА не должен кидать исключение
# наружу в Python, даже если разметка AI Studio внезапно поменялась.
# JSON action НЕ парсится в JS — сырой текст блока agent_action отдаётся
# в Python, где его гораздо проще "починить".
# ---------------------------------------------------------------------------
JS_EXTRACT_LAST_ANSWER = r"""
try {
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
                    const langLabel = lang ? '[color=#8ab4f8]' + escapeBBCode(lang) + '[/color]\n' : '';
                    return '\n' + langLabel + '[bgcolor=#2b2b2b][code]' + code + '[/code][/bgcolor]\n';
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
                    const cmarkRoot = chunk.querySelector('ms-cmark-node.cmark-node') || chunk;
                    fullText += walk(cmarkRoot) + '\n';
                }
            }
        } catch (e) {
            fullText = lastModelTurn.innerText || '';
        }

        fullText = fullText.replace(/\n{3,}/g, '\n\n').trim();

        // Страховка: сканируем все ms-code-block напрямую, если walk() что-то
        // пропустил из-за внутренних try/catch.
        if (capturedActionRaw === null) {
            const codeBlocks = lastModelTurn.querySelectorAll('ms-code-block');
            for (const block of codeBlocks) {
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
}
"""

JS_COUNT_MODEL_TURNS = "return document.querySelectorAll('[data-turn-role=\"Model\"]').length;"

# Список селекторов-кандидатов "идёт генерация". Проверяем ВСЕ по очереди —
# если один селектор в UI студии сломается, остальные подстрахуют.
# Если проблема повторится — открой DevTools во время генерации и добавь
# сюда актуальный селектор кнопки "Stop"/спиннера.
JS_IS_GENERATING = r"""
try {
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
}
"""

JS_GET_LAST_MODEL_TEXT_LENGTH = r"""
try {
    const modelTurns = document.querySelectorAll('[data-turn-role="Model"]');
    if (modelTurns.length === 0) return 0;
    const last = modelTurns[modelTurns.length - 1];
    return (last.innerText || '').length;
} catch (e) {
    return -1;
}
"""


def _safe_execute(driver, script, retries=5, delay=0.2, default=None):
    """
    Обёртка над driver.execute_script с защитой от StaleElementReferenceException /
    JavascriptException — они возможны, если Angular перерисовал DOM прямо
    во время выполнения скрипта.
    """
    last_exc = None
    for _ in range(retries):
        try:
            return driver.execute_script(script)
        except (JavascriptException, StaleElementReferenceException, WebDriverException) as e:
            last_exc = e
            time.sleep(delay)
    print(f"[ai_parser] execute_script не удался после {retries} попыток: {last_exc}")
    return default


def get_model_turn_count(driver):
    return _safe_execute(driver, JS_COUNT_MODEL_TURNS, default=0) or 0


def is_generating(driver):
    return bool(_safe_execute(driver, JS_IS_GENERATING, default=False))


def get_last_model_text_length(driver):
    val = _safe_execute(driver, JS_GET_LAST_MODEL_TEXT_LENGTH, default=-1)
    return val if val is not None else -1


def extract_last_answer(driver):
    return _safe_execute(
        driver, JS_EXTRACT_LAST_ANSWER,
        default={"text": "", "actionRaw": None, "error": "execute_script failed"}
    )


# ---------------------------------------------------------------------------
# Разбор JSON из agent_action. LLM часто присылает "почти валидный" JSON:
# необрезанные переносы строк внутри строковых значений, висячие запятые,
# иногда лишний текст до/после {}. Пытаемся почленно "починить".
# ---------------------------------------------------------------------------
def _strip_code_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z_]*\s*', '', raw)
    raw = re.sub(r'```\s*$', '', raw)
    return raw.strip()


def _extract_json_object(raw: str) -> str:
    """Вырезает подстроку от первой '{' до последней '}' — на случай, если
    модель добавила пояснительный текст до/после самого JSON."""
    start = raw.find('{')
    end = raw.rfind('}')
    if start == -1 or end == -1 or end < start:
        return raw
    return raw[start:end + 1]


def _escape_raw_newlines_in_strings(raw: str) -> str:
    """
    Экранирует "голые" переносы строк внутри JSON-строк.
    LLM иногда вставляет реальный \n вместо \\n в значениях content/search/replace.
    Идём по символам и следим, находимся ли мы внутри строки.
    """
    out = []
    in_string = False
    escape = False
    for ch in raw:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == '\\':
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                continue
            if ch == '\n':
                out.append('\\n')
                continue
            if ch == '\r':
                out.append('\\r')
                continue
            if ch == '\t':
                out.append('\\t')
                continue
            out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)
    return ''.join(out)


def _remove_trailing_commas(raw: str) -> str:
    return re.sub(r',(\s*[}\]])', r'\1', raw)


def parse_action_json(raw: str):
    """
    Пытается распарсить JSON блока agent_action в несколько заходов —
    от простого к "чинящему".
    Возвращает (dict_or_None, error_message_or_None).
    """
    if raw is None:
        return None, None

    base = _strip_code_fences(raw)
    candidates = [base, _extract_json_object(base)]
    for cand in list(candidates):
        candidates.append(_remove_trailing_commas(cand))
        candidates.append(_escape_raw_newlines_in_strings(cand))
        candidates.append(_remove_trailing_commas(_escape_raw_newlines_in_strings(cand)))

    last_error = None
    for cand in candidates:
        try:
            return json.loads(cand), None
        except Exception as e:
            last_error = str(e)

    # Последний рубеж: если установлен pip-пакет json_repair — используем его.
    try:
        from json_repair import repair_json
        fixed = repair_json(_extract_json_object(base))
        return json.loads(fixed), None
    except Exception as e:
        last_error = f"{last_error}; json_repair: {e}"

    return None, last_error


def _looks_json_balanced(raw: str) -> bool:
    """Грубая проверка баланса скобок/кавычек — признак того, что блок
    кода дорендерился полностью, а не оборван на середине."""
    if not raw:
        return False
    depth = 0
    in_string = False
    escape = False
    for ch in raw:
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in '{[':
            depth += 1
        elif ch in '}]':
            depth -= 1
    return (not in_string) and depth == 0


def wait_for_new_answer(driver, initial_model_count, timeout=900,
                        quiet_period=2.0, hard_quiet_period=30.0, poll_interval=0.25,
                        post_quiet_grace=4.0):
    start = time.time()

    while time.time() - start < timeout:
        if get_model_turn_count(driver) > initial_model_count:
            break
        time.sleep(poll_interval)
    else:
        raise TimeoutError("Новая реплика модели не появилась.")

    while time.time() - start < timeout:
        length = get_last_model_text_length(driver)
        generating = is_generating(driver)
        if length > 0 or generating:
            break
        time.sleep(poll_interval)

    last_length = -1
    quiet_since = None
    length_only_quiet_since = None

    while time.time() - start < timeout:
        length = get_last_model_text_length(driver)
        generating = is_generating(driver)
        now = time.time()

        if length == last_length:
            if length_only_quiet_since is None:
                length_only_quiet_since = now
            if not generating:
                if quiet_since is None:
                    quiet_since = now
            else:
                quiet_since = None
        else:
            quiet_since = None
            length_only_quiet_since = None

        if quiet_since is not None and now - quiet_since >= quiet_period:
            break
        if length_only_quiet_since is not None and now - length_only_quiet_since >= hard_quiet_period:
            break

        last_length = length
        time.sleep(poll_interval)
    else:
        raise TimeoutError("Генерация не завершилась вовремя.")

    # --- Защита от "ложного завершения" ---
    # Сеть может ненадолго подвиснуть дольше quiet_period, хотя модель ещё
    # не закончила. Перепроверяем: если появился новый текст ИЛИ JSON
    # agent_action выглядит незавершённым — ждём ещё немного.
    grace_start = time.time()
    result = extract_last_answer(driver)
    while time.time() - grace_start < post_quiet_grace:
        raw = (result or {}).get("actionRaw")
        cur_len = get_last_model_text_length(driver)
        still_generating = is_generating(driver)

        action_incomplete = raw is not None and not _looks_json_balanced(
            _extract_json_object(_strip_code_fences(raw))
        )

        if not still_generating and cur_len == last_length and not action_incomplete:
            break

        time.sleep(0.4)
        result = extract_last_answer(driver)
        last_length = cur_len

    return result


def send_message_and_get_response(driver, prompt, input_retries=3):
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "aistudio.google.com" in driver.current_url:
            break

    from browser_manager import harden_background_tab
    harden_background_tab(driver)

    js_find_input = """
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

    textarea = None
    for _ in range(input_retries):
        textarea = driver.execute_script(js_find_input)
        if textarea:
            break
        time.sleep(0.5)
    if not textarea:
        raise Exception("Поле ввода не найдено.")

    for _ in range(input_retries):
        try:
            driver.execute_script("arguments[0].value = '';", textarea)
            time.sleep(0.2)

            js_insert = """
            let el = arguments[0];
            el.focus();
            el.value = arguments[1];
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            """
            driver.execute_script(js_insert, textarea, prompt)

            actual_value = driver.execute_script("return arguments[0].value;", textarea)
            if actual_value:
                break
        except (JavascriptException, StaleElementReferenceException):
            textarea = driver.execute_script(js_find_input)
        time.sleep(0.3)
    else:
        raise Exception("Не удалось вставить текст в поле ввода после нескольких попыток.")

    time.sleep(1)
    try:
        textarea.send_keys(Keys.SPACE)
        textarea.send_keys(Keys.BACKSPACE)
    except StaleElementReferenceException:
        textarea = driver.execute_script(js_find_input)
    time.sleep(0.5)

    initial_model_count = get_model_turn_count(driver)

    try:
        textarea.send_keys(Keys.CONTROL, Keys.ENTER)
    except StaleElementReferenceException:
        textarea = driver.execute_script(js_find_input)
        textarea.send_keys(Keys.CONTROL, Keys.ENTER)

    result = wait_for_new_answer(driver, initial_model_count)
    time.sleep(0.6)

    if not result:
        result = extract_last_answer(driver)

    text = result.get("text") or ""
    raw_action = result.get("actionRaw")
    error = result.get("error")

    if error:
        print(f"[ai_parser] JS extraction error: {error}")

    action = None
    if raw_action is not None:
        action, parse_error = parse_action_json(raw_action)
        if action is None:
            print(f"[ai_parser] Не удалось распарсить agent_action: {parse_error}")
            print(f"[ai_parser] RAW ({len(raw_action)} симв.): {raw_action[:2000]}")
            action = {
                "action": "parse_error",
                "raw": raw_action,
                "error": parse_error,
            }

    return {"text": text, "action": action}