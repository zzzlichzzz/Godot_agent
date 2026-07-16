import time
from selenium.webdriver.common.keys import Keys

# JS-функция, которая структурно проходит дерево ПОСЛЕДНЕГО ОТВЕТА МОДЕЛИ
# и собирает BBCode — формат, который RichTextLabel в Godot интерпретирует
# нативно (при bbcode_enabled=true), в отличие от голого markdown, который
# просто отображается как есть (буквальные ** и ```).
#
# ВАЖНО: любые квадратные скобки из ИСХОДНОГО текста (например, в GDScript:
# `var array = [1, 2, 3]`, `Array[int]`) экранируются в [lb] / [rb] —
# это спецсимволы Godot BBCode для литеральных "[" и "]". Без этого код
# со скобками сломает всю последующую разметку в чате Godot.
JS_EXTRACT_LAST_ANSWER = """
function extractLastAnswer() {
    const modelTurns = document.querySelectorAll('[data-turn-role="Model"]');
    if (modelTurns.length === 0) return null;
    const lastModelTurn = modelTurns[modelTurns.length - 1];

    const chunks = lastModelTurn.querySelectorAll('div[mssnapshotlink]');
    if (chunks.length === 0) return null;

    // Экранируем BBCode-спецсимволы В ИСХОДНОМ тексте (до того, как мы сами
    // добавим свои теги форматирования поверх).
    // ВАЖНО: один проход через regex с альтернативой [\[\]] — а не два
    // последовательных .replace(). Два последовательных replace() ломают
    // друг друга: первый заменяет "[" на "[lb]", но в САМОЙ строке "[lb]"
    // есть символ "]", и второй replace (идущий уже по изменённой строке)
    // случайно захватывает и его тоже — экранирование само себя портит.
    function escapeBBCode(text) {
        return text.replace(/[\[\]]/g, function(ch) {
            return ch === '[' ? '[lb]' : '[rb]';
        });
    }

    // Если модель хочет выполнить действие (прочитать/изменить файл), она
    // оформляет его как ЕДИНСТВЕННЫЙ блок кода с языком "agent_action".
    // Перехватываем его RAW-содержимое ДО экранирования — если прогнать JSON
    // через escapeBBCode, он будет искажён точно так же, как искажался бы
    // любой другой текст с квадратными скобками, и превратится в невалидный
    // JSON. Вместо самого блока в видимом тексте оставляем только короткую
    // пометку — сырой JSON в чат не идёт.
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

        // Обобщённая "распаковка" passthrough-обёртки <ms-cmark-node>, которая
        // Angular иногда вставляет между структурным элементом (ol/ul/table/tr)
        // и его настоящими детьми (li/tr/th/td) — используется и для списков,
        // и для таблиц ниже, чтобы не наступать на те же грабли дважды.
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

        // Списки — нумеруем/маркируем вручную, т.к. в исходной разметке
        // числа/маркеры это CSS-counter, а не текст, и просто "прохождением
        // насквозь" они не появятся.
        // listDepth здесь — это "сколько списков уже оборачивают ТЕКУЩИЙ
        // список снаружи". Если > 0, значит мы сами вложенный список внутри
        // чьего-то пункта — оборачиваем себя в [indent], чтобы визуально
        // сдвинуться и не выглядеть как продолжение родительской нумерации.
        // Пунктам ВНУТРИ себя передаём listDepth + 1 — если там окажется ещё
        // один вложенный список, он получит отступ уже относительно нас.
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

        // Таблицы — раньше вообще не обрабатывались отдельно, поэтому все
        // ячейки склеивались в одну строку без разделителей. Строки ищем
        // сквозь возможные thead/tbody/tfoot (и их возможные ms-cmark-node
        // обёртки), ячейки разделяем табуляцией, строки — переводом строки.
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

        if (tag === 'li') return inner; // обрабатывается родителем ol/ul выше
        if (['h1', 'h2', 'h3', 'h4'].includes(tag)) return '[b][font_size=20]' + inner + '[/font_size][/b]\\n';
        if (tag === 'p') return inner + '\\n';
        if (tag === 'hr') return '\\n―――――――――――\\n';
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

# Считаем ТОЛЬКО реплики модели по семантической роли, а не общее число блоков.
# Это не зависит от того, как и когда рендерится эхо пользователя.
JS_COUNT_MODEL_TURNS = "return document.querySelectorAll('[data-turn-role=\"Model\"]').length;"

# Спиннер отражает, судя по всему, только фазу "жду первый токен" — он гаснет,
# как только начинается стриминг текста, и дальше уже НЕ является признаком
# завершения. Поэтому используем его как ОДНО из двух условий, а не единственное.
JS_IS_GENERATING = "return !!document.querySelector('ms-run-button .spin');"

# Длина текста именно ПОСЛЕДНЕГО хода с ролью Model (а не абы какого узла) —
# используется как второе условие: даже если спиннер уже погас, но текст ещё
# растёт, значит генерация не закончена.
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
    # timeout=900 (15 минут) — на случай долгого "размышления" продвинутых моделей.
    # hard_quiet_period увеличен до 30 сек: это должно быть заметно ДОЛЬШЕ любой
    # обычной паузы модели между кусками текста, чтобы не путать естественную
    # паузу мышления со сломанным определением спиннера. Это подстраховка на
    # крайний случай, а не основной механизм — основной путь почти всегда
    # завершится по quiet_period (1.5 сек) сразу после того, как спиннер погаснет.
    start = time.time()

    # 1. Ждём появления НОВОГО хода именно с ролью "Model"
    while time.time() - start < timeout:
        if get_model_turn_count(driver) > initial_model_count:
            break
        time.sleep(poll_interval)
    else:
        raise TimeoutError("Новая реплика модели не появилась за отведенное время.")

    # 2. Ждём одновременно: (а) спиннера больше нет, И (б) текст ответа
    #    не меняется на протяжении quiet_period секунд подряд.
    #    Плюс hard_quiet_period — защитный fallback: если по каким-то причинам
    #    is_generating() перестанет корректно определяться (Google поменяет
    #    разметку спиннера), мы всё равно не зависнем навсегда, а просто
    #    подождём чуть дольше по одной стабилизации длины текста.
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

    raise TimeoutError("Генерация не завершилась за отведенное время.")


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
        raise Exception("Поле ввода не найдено на странице.")

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

    # Фиксируем количество ОТВЕТОВ МОДЕЛИ до отправки (не общее число блоков)
    initial_model_count = get_model_turn_count(driver)

    textarea.send_keys(Keys.CONTROL, Keys.ENTER)
    print("Текст отправлен! Ждём ответ модели...")

    wait_for_new_answer(driver, initial_model_count)

    result = driver.execute_script(JS_EXTRACT_LAST_ANSWER)

    if not result or not result.get('text'):
        return {"text": "Ответ получен, но возникла ошибка парсинга. Проверьте браузер.", "action": None}

    return result