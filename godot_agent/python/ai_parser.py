import time
from selenium.webdriver.common.keys import Keys

JS_EXTRACT_LAST_ANSWER = """
function extractLastAnswer() {
    const modelTurns = document.querySelectorAll('[data-turn-role="Model"]');
    if (modelTurns.length === 0) return null;
    const lastModelTurn = modelTurns[modelTurns.length - 1];

    const chunks = lastModelTurn.querySelectorAll('div[mssnapshotlink]');
    if (chunks.length === 0) return null;

    function escapeBBCode(text) {
        return text.replace(/[\[\]]/g, function(ch) {
            return ch === '[' ? '[lb]' : '[rb]';
        });
    }

    let capturedActionRaw = null;

    function walk(node, listDepth) {
        listDepth = listDepth || 0;

        if (node.nodeType === Node.TEXT_NODE) {
            return escapeBBCode(node.textContent);
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return '';

        const tag = node.tagName.toLowerCase();

        if (tag === 'ms-code-block') {
            const lang = (node.getAttribute('data-test-language') || '').toLowerCase();
            const codeEl = node.querySelector('.mat-expansion-panel-body pre code');
            const rawCode = codeEl ? codeEl.innerText : '';

            if (lang === 'agent_action' && capturedActionRaw === null) {
                capturedActionRaw = rawCode;
                return '\\n[color=#888888]— агент предлагает действие (см. ниже) —[/color]\\n';
            }

            const code = escapeBBCode(rawCode);
            const langLabel = lang ? '[color=#8ab4f8]' + escapeBBCode(lang) + '[/color]\\n' : '';
            return '\\n' + langLabel + '[bgcolor=#2b2b2b][code]' + code + '[/code][/bgcolor]\\n';
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
                out += marker + walk(li, listDepth + 1).trim() + '\\n';
                idx++;
            }
            if (listDepth > 0) {
                out = '[indent]' + out.trim() + '[/indent]\\n';
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

            let out = '\\n';
            for (const tr of rows) {
                const cells = collectChildren(tr, ['th', 'td']).map(function(c) {
                    return walk(c, listDepth).trim();
                });
                out += cells.join('\\t') + '\\n';
            }
            return out + '\\n';
        }

        let inner = '';
        for (const child of node.childNodes) {
            inner += walk(child, listDepth);
        }

        if (tag === 'strong') return '[b]' + inner + '[/b]';
        if (tag === 'em') return '[i]' + inner + '[/i]';
        if (node.classList && node.classList.contains('inline-code')) return '[code]' + inner + '[/code]';

        if (tag === 'li') return inner;
        if (['h1', 'h2', 'h3', 'h4'].includes(tag)) return '[b][font_size=20]' + inner + '[/font_size][/b]\\n';
        if (tag === 'p') return inner + '\\n';
        if (tag === 'hr') return '\\n――――――――――Jew\\n';
        if (tag === 'br') return '\\n';

        return inner;
    }

    let fullText = '';
    for (const chunk of chunks) {
        const cmarkRoot = chunk.querySelector('ms-cmark-node.cmark-node') || chunk;
        fullText += walk(cmarkRoot) + '\\n';
    }

    fullText = fullText.replace(/\\n{3,}/g, '\\n\\n').trim();

    let action = null;
    if (capturedActionRaw !== null) {
        try {
            action = JSON.parse(capturedActionRaw);
        } catch (e) {
            action = { "action": "parse_error", "raw": capturedActionRaw };
        }
    }

    return { text: fullText, action: action };
}
return extractLastAnswer();
"""

JS_COUNT_MODEL_TURNS = "return document.querySelectorAll('[data-turn-role=\"Model\"]').length;"
JS_IS_GENERATING = "return !!document.querySelector('ms-run-button .spin');"

JS_GET_LAST_MODEL_TEXT_LENGTH = """
const modelTurns = document.querySelectorAll('[data-turn-role="Model"]');
if (modelTurns.length === 0) return 0;
const last = modelTurns[modelTurns.length - 1];
return last.innerText.length;
"""

def get_model_turn_count(driver):
    return driver.execute_script(JS_COUNT_MODEL_TURNS)

def is_generating(driver):
    return driver.execute_script(JS_IS_GENERATING)

def get_last_model_text_length(driver):
    return driver.execute_script(JS_GET_LAST_MODEL_TEXT_LENGTH)

def wait_for_new_answer(driver, initial_model_count, timeout=900,
                        quiet_period=1.5, hard_quiet_period=30.0, poll_interval=0.25):
    start = time.time()

    # 1. Ждём появления нового ответа
    while time.time() - start < timeout:
        if get_model_turn_count(driver) > initial_model_count:
            break
        time.sleep(poll_interval)
    else:
        raise TimeoutError("Новая реплика модели не появилась.")

    # 2. ЗАЩИТА ОТ ЛАГОВ: Ждём, пока в блоке появится текст ИЛИ загорится спиннер
    while time.time() - start < timeout:
        length = get_last_model_text_length(driver)
        generating = is_generating(driver)
        if length > 0 or generating:
            break
        time.sleep(poll_interval)

    # 3. Мониторим стабилизацию потока текста
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
            return
        if length_only_quiet_since is not None and now - length_only_quiet_since >= hard_quiet_period:
            return

        last_length = length
        time.sleep(poll_interval)

    raise TimeoutError("Генерация не завершилась вовремя.")

def send_message_and_get_response(driver, prompt):
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "aistudio.google.com" in driver.current_url:
            break

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
    textarea = driver.execute_script(js_find_input)
    if not textarea:
        raise Exception("Поле ввода не найдено.")

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

    time.sleep(1)
    textarea.send_keys(Keys.SPACE)
    textarea.send_keys(Keys.BACKSPACE)
    time.sleep(0.5)

    initial_model_count = get_model_turn_count(driver)
    textarea.send_keys(Keys.CONTROL, Keys.ENTER)

    wait_for_new_answer(driver, initial_model_count)
    return driver.execute_script(JS_EXTRACT_LAST_ANSWER)
