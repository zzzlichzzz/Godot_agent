# -*- coding: utf-8 -*-
"""Менеджер парсинга: общая логика для ВСЕХ сайтов-нейросетей.

BaseSiteParser реализует общий конвейер целиком:
    переключение на вкладку сайта -> вставка промпта -> отправка ->
    ожидание нового ответа (стабилизация длины + целостность JSON) ->
    извлечение текста/agent_action (+ «план Б») -> разбор JSON действия.

Наследники (ai_parser.AiStudioParser, deepseek_parser.DeepSeekParser, ...)
переопределяют только «где что лежит на странице»:
    count_answers, answer_len, answer_preview, answer_stream, is_generating,
    extract_answer, find_input, insert_input, submit
    (+ опционально before_submit / after_submit / extract_raw_fallback /
    get_live_activity).

Будущий универсальный автопарсер — это ещё один наследник, у которого эти
же методы работают по эвристикам/спец-маркерам, а не по известным селекторам.
"""
import json
import os
import re
import sys
import time

from text_sanitize import sanitize_llm_text


# ---------------------------------------------------------------------------
# v86.8: сигнальный маркер конца ответа. Модель обязана (agent_prompts.py,
# правило 14) ставить отдельной строкой ===DONE=== в самом конце каждого своего
# сообщения. До 86.8 готовность ответа определялась ТОЛЬКО эвристикой по
# «тишине» (quiet_period/hard_quiet_period) — а это зависит от DOM/скорости
# конкретного сайта. С ===DONE=== парсер может завершить ожидание детерминированно,
# не дожидаясь тишины. Обратная совместимость: если маркера нет (старый чат,
# модель забыла, другой PROMPT_HASH) — работает только старая эвристика, как и раньше.
DONE_MARKER = "===DONE==="
_DONE_MARKER_RE = re.compile(r'\n?[ \t]*={2,}\s*DONE\s*={2,}[ \t]*$', re.IGNORECASE)


def _has_done_marker(text):
    """v86.8: есть ли в конце текста маркер завершения ответа. Смотрим только
    в хвост (дешево, и исключает случайные совпадения глубоко внутри кода/контента)."""
    if not text:
        return False
    tail = text.rstrip()[-64:]
    return bool(_DONE_MARKER_RE.search(tail))


def _strip_done_marker(text):
    """v86.8: убирает служебный маркер конца ответа из текста, который увидит
    пользователь. Абсолютно безопасно: если маркер не найден — возвращает текст без изменений."""
    if not text:
        return text
    stripped = text.rstrip()
    m = _DONE_MARKER_RE.search(stripped[-64:])
    if not m:
        return text
    cut = len(stripped) - 64 + m.start() if len(stripped) > 64 else m.start()
    return stripped[:cut].rstrip()


from selenium.common.exceptions import (
    JavascriptException,
    StaleElementReferenceException,
    WebDriverException,
)


# ---------------------------------------------------------------------------
# Общие утилиты (используются всеми парсерами)
# ---------------------------------------------------------------------------

class ParserCancelled(Exception):
    """Обработка запроса остановлена пользователем (кнопка «Стоп»)."""


def _safe_execute(driver, script, retries=5, delay=0.2, default=None):
    """Обёртка над driver.execute_script с защитой от Stale/JS-исключений —
    они возможны, если фреймворк сайта перерисовал DOM во время скрипта."""
    last_exc = None
    for _ in range(retries):
        try:
            return driver.execute_script(script)
        except (JavascriptException, StaleElementReferenceException, WebDriverException) as e:
            last_exc = e
            time.sleep(delay)
    print(f"[parser_base] execute_script не удался после {retries} попыток: {last_exc}")
    return default



# ---------------------------------------------------------------------------
# v86.14/v86.15: универсальный сборщик ПОЛНОГО текста ответа для сайтов,
# которые рендерят длинные код-блоки через Monaco-редактор (движок VS Code)
# с ВИРТУАЛИЗАЦИЕЙ строк: в DOM существуют только видимые на экране строки,
# причём в произвольном порядке (absolute-позиционирование по style.top),
# поэтому .innerText возвращает неполный и перемешанный текст. Первым таким
# сайтом оказался Qwen (см. v86.13 в README).
# Порядок попыток для каждого код-блока:
#   1) модель Monaco (monaco.editor.getModels() по data-uri) — работает, только
#      если сайт выставляет глобальный monaco (на реальном Qwen его НЕТ —
#      выяснено в v86.15 по повторному HTML от пользователя);
#   2) ПЕРЕХВАТ КНОПКИ Copy код-блока (v86.15): подменяем
#      navigator.clipboard.writeText/write и document.execCommand('copy') на
#      перехватчики и программно нажимаем кнопку Copy — сайт сам отдаёт
#      ПОЛНЫЙ текст блока из своего хранилища; текст ловится БЕЗ обращения
#      к реальному буферу обмена (не требует фокуса окна и разрешений,
#      буфер пользователя не портится); после чтения подмены снимаются;
#   3) аварийно: видимые .view-line, отсортированные по style.top (частично).
# Использование в парсере сайта:
#   js = build_composed_answer_js(<JS с функцией блоков>, '<имя функции>',
#                                 '<css-селектор код-блока>')
#   click_js = build_copy_click_js(<JS с функцией блоков>, '<имя функции>',
#                                  '<css-селектор код-блока>',
#                                  '<css-селектор кнопки Copy внутри блока>')
#   text = read_composed_answer(driver, js, '[my_parser]', copy_click_js=click_js)
_MONACO_HELPERS_JS = r"""
function __monacoValueByUri(pre) {
    try {
        var ed = pre.querySelector('.monaco-editor[data-uri]');
        if (!ed) return null;
        var uri = ed.getAttribute('data-uri') || '';
        var me = null;
        try { if (typeof monaco !== 'undefined' && monaco && monaco.editor) me = monaco.editor; } catch (e) {}
        if (!me && typeof window !== 'undefined' && window.monaco && window.monaco.editor) me = window.monaco.editor;
        if (!me || !me.getModels) return null;
        var models = me.getModels();
        for (var i = 0; i < models.length; i++) {
            try {
                if (String(models[i].uri) === uri) return models[i].getValue();
            } catch (e) {}
        }
    } catch (e) {}
    return null;
}
function __sortedVisibleCodeText(pre) {
    var rows = [];
    var lines = pre.querySelectorAll('.view-line');
    for (var i = 0; i < lines.length; i++) {
        var t = parseFloat((lines[i].style && lines[i].style.top) || '0');
        rows.push([isNaN(t) ? 0 : t, lines[i].textContent || '']);
    }
    if (!rows.length) return pre.innerText || '';
    rows.sort(function(a, b) { return a[0] - b[0]; });
    var out = [];
    for (var j = 0; j < rows.length; j++) out.push(rows[j][1]);
    return out.join('\n');
}
"""

_COMPOSED_ANSWER_TEMPLATE_JS = r"""
function __composedAnswer() {
    var b = __BLOCKS_FN__();
    if (!b.length) return {text: '', partialCode: false, monacoUsed: false, codeBlocks: 0,
                           missing: [], fallbacks: {}, monacoGlobal: false};
    var mg = false;
    try { mg = (typeof monaco !== 'undefined' && !!monaco) || !!(window && window.monaco); } catch (e) {}
    var root = b[b.length - 1];
    var pres = root.querySelectorAll('__CODE_SEL__');
    if (!pres.length) return {text: root.innerText || '', partialCode: false, monacoUsed: false,
                              codeBlocks: 0, missing: [], fallbacks: {}, monacoGlobal: mg};
    var preList = Array.prototype.slice.call(pres);
    var state = {monaco: false, missing: [], fallbacks: {}};
    function textOf(node) {
        if (node.nodeType === 3) return node.textContent || '';
        if (node.nodeType !== 1) return '';
        if (node.matches && node.matches('__CODE_SEL__')) {
            var idx = preList.indexOf(node);
            var val = __monacoValueByUri(node);
            if (val !== null && val !== undefined) { state.monaco = true; return val; }
            state.missing.push(idx);
            state.fallbacks[idx] = __sortedVisibleCodeText(node);
            return '\uE000CODE_BLOCK_' + idx + '\uE000';
        }
        if (node.querySelector && node.querySelector('__CODE_SEL__')) {
            var parts = [];
            for (var i = 0; i < node.childNodes.length; i++) parts.push(textOf(node.childNodes[i]));
            return parts.join('\n');
        }
        return (node.innerText !== undefined ? node.innerText : (node.textContent || ''));
    }
    var parts = [];
    for (var i = 0; i < root.childNodes.length; i++) {
        var piece = textOf(root.childNodes[i]);
        if (piece && piece.trim()) parts.push(piece);
    }
    return {text: parts.join('\n'), partialCode: state.missing.length > 0,
            monacoUsed: state.monaco, codeBlocks: preList.length,
            missing: state.missing, fallbacks: state.fallbacks, monacoGlobal: mg};
}
"""

# Скрипт «взвести перехват и нажать Copy у блока N». Токен __CB_IDX__
# подставляется в read_composed_answer номером блока (execute_script без
# аргументов — чтобы не менять _safe_execute).
_COPY_CLICK_TEMPLATE_JS = r"""
var __cbIdx = __CB_IDX__;
var b = __BLOCKS_FN__();
if (!b.length) return false;
var root = b[b.length - 1];
var pres = root.querySelectorAll('__CODE_SEL__');
if (__cbIdx < 0 || __cbIdx >= pres.length) return false;
var btn = pres[__cbIdx].querySelector('__COPY_BTN_SEL__');
if (!btn) return false;
if (!window.__aiCopyIntercept) {
    var st = {captured: null, origWriteText: null, origWrite: null, origExec: document.execCommand};
    try {
        if (navigator.clipboard) {
            st.origWriteText = navigator.clipboard.writeText;
            st.origWrite = navigator.clipboard.write;
            navigator.clipboard.writeText = function (t) { st.captured = String(t); return Promise.resolve(); };
            navigator.clipboard.write = function (items) {
                try {
                    for (var i = 0; i < items.length; i++) {
                        var it = items[i];
                        if (it && it.getType) {
                            it.getType('text/plain').then(function (blob) {
                                return blob.text();
                            }).then(function (t) {
                                if (t) st.captured = String(t);
                            }).catch(function () {});
                        }
                    }
                } catch (e) {}
                return Promise.resolve();
            };
        }
    } catch (e) {}
    try {
        document.execCommand = function (cmd) {
            if (String(cmd).toLowerCase() === 'copy') {
                try {
                    var ae = document.activeElement;
                    var t = null;
                    if (ae && (ae.tagName === 'TEXTAREA' || ae.tagName === 'INPUT')) {
                        t = ae.value || '';
                        if (typeof ae.selectionStart === 'number' &&
                                ae.selectionEnd > ae.selectionStart) {
                            t = t.substring(ae.selectionStart, ae.selectionEnd);
                        }
                    } else {
                        var sel = document.getSelection();
                        t = sel ? String(sel) : null;
                    }
                    if (t) st.captured = String(t);
                } catch (e) {}
                return true;
            }
            return st.origExec.apply(document, arguments);
        };
    } catch (e) {}
    window.__aiCopyIntercept = st;
}
window.__aiCopyIntercept.captured = null;
btn.click();
return true;
"""

_COPY_CAPTURE_READ_JS = (
    "var st = window.__aiCopyIntercept;"
    " if (!st) { return null; }"
    " return st.captured;")

_COPY_INTERCEPT_RESTORE_JS = (
    "var st = window.__aiCopyIntercept;"
    " if (!st) { return true; }"
    " try { if (st.origWriteText) navigator.clipboard.writeText = st.origWriteText; } catch (e) {}"
    " try { if (st.origWrite) navigator.clipboard.write = st.origWrite; } catch (e) {}"
    " try { document.execCommand = st.origExec; } catch (e) {}"
    " window.__aiCopyIntercept = null;"
    " return true;")


def build_composed_answer_js(blocks_js, blocks_fn, code_block_selector):
    """Собирает готовый JS для чтения ПОЛНОГО текста последнего ответа (v86.14).

    blocks_js  — JS с определением функции, возвращающей список корневых
                 элементов ответов модели (сайт-специфично);
    blocks_fn  — имя этой функции, например '__qwenBlocks';
    code_block_selector — css-селектор контейнера код-блока, например
                 'pre.qwen-markdown-code' (сайт-специфично).
    """
    js = _COMPOSED_ANSWER_TEMPLATE_JS.replace('__BLOCKS_FN__', blocks_fn)
    js = js.replace('__CODE_SEL__', code_block_selector)
    return blocks_js + _MONACO_HELPERS_JS + js + "return __composedAnswer();"


def build_copy_click_js(blocks_js, blocks_fn, code_block_selector, copy_button_selector):
    """Собирает JS «перехватить буфер и нажать Copy у блока №__CB_IDX__» (v86.15).

    copy_button_selector — css-селектор кнопки Copy ВНУТРИ код-блока.
    Перед выполнением подставь номер блока: js.replace('__CB_IDX__', str(i)).
    После чтения результата выполни _COPY_INTERCEPT_RESTORE_JS.
    """
    js = _COPY_CLICK_TEMPLATE_JS.replace('__BLOCKS_FN__', blocks_fn)
    js = js.replace('__CODE_SEL__', code_block_selector)
    js = js.replace('__COPY_BTN_SEL__', copy_button_selector)
    return blocks_js + js


# v86.16: проверка ПОЛНОТЫ ответа с действием: у всех меток *_ref из JSON
# должны быть ЗАВЕРШЁННЫЕ тела ===МЕТКА===...===END_МЕТКА=== в том же тексте.
# Непустой результат обычно означает, что ответ ещё дописывается (JSON плана
# генерируется РАНЬШЕ тел файлов) — парсеру сайта стоит подождать и
# перечитать ответ, прежде чем отдавать его на разбор.
_REF_LABEL_RE = re.compile(
    r'"(?:content_ref|search_ref|replace_ref)"\s*:\s*"([A-Za-z0-9_\-]+)"')


def missing_ref_bodies(action_raw, text):
    """Список меток *_ref из JSON действия, для которых в тексте нет
    завершённого тела (нет маркера ===END_МЕТКА===). Пустой список —
    ответ полон (или меток нет вовсе)."""
    if not action_raw or not text:
        return []
    out = []
    seen = set()
    for label in _REF_LABEL_RE.findall(action_raw):
        if label in seen:
            continue
        seen.add(label)
        if ("===END_%s===" % label) not in text:
            out.append(label)
    return out


def read_composed_answer(driver, composed_js, log_tag="[parser_base]", copy_click_js=None):
    """Выполняет JS от build_composed_answer_js; возвращает текст ('' при неудаче).

    Если для каких-то код-блоков модель Monaco недоступна, а copy_click_js задан —
    добирает их полный текст перехватом кнопки Copy (v86.15).

    v86.17: результат перехвата КЭШИРУЕТСЯ (на объекте driver) по «отпечатку»
    блока (число блоков + отсортированный видимый текст). Сторожевой таймер
    ожидания перечитывает последний ответ каждые ~20 с, и без кэша КАЖДОЕ
    перечитывание нажимало Copy у всех код-блоков уже завершённого сообщения —
    сайт спамил подсказкой «скопировать текст», пока модель думала над новым
    ответом. Теперь повторный клик выполняется только если блок реально
    изменился (например, идёт генерация нового ответа)."""
    res = _safe_execute(driver, composed_js, default=None)
    if not isinstance(res, dict) or not isinstance(res.get("text"), str):
        return ""
    text = res.get("text") or ""
    missing = res.get("missing") or []
    fallbacks = res.get("fallbacks") or {}
    try:
        n_code = int(res.get("codeBlocks") or 0)
    except Exception:
        n_code = 0
    if n_code and res.get("monacoUsed"):
        print("%s блок(и) кода прочитаны целиком из модели Monaco-редактора (v86.14)." % log_tag)
    cache = getattr(driver, "_ai_copy_block_cache", None)
    if cache is None:
        cache = {}
        try:
            setattr(driver, "_ai_copy_block_cache", cache)
        except Exception:
            pass
    used_copy = 0
    used_cache = 0
    clicked_any = False
    for idx in missing:
        placeholder = "\ue000CODE_BLOCK_%d\ue000" % int(idx)
        fb = fallbacks.get(str(idx)) or fallbacks.get(idx) or ""
        sig = (n_code, fb)
        captured = None
        cached = cache.get(int(idx))
        if cached and cached[0] == sig and cached[1]:
            captured = cached[1]
            used_cache += 1
        elif copy_click_js:
            if not clicked_any:
                print("%s глобальный monaco недоступен (monacoGlobal=%s) — читаю код-блок(и) "
                      "через перехват кнопки Copy (v86.15)."
                      % (log_tag, res.get("monacoGlobal")))
            clicked_any = True
            armed = _safe_execute(
                driver, copy_click_js.replace("__CB_IDX__", str(int(idx))), default=False)
            if armed:
                for _ in range(6):
                    time.sleep(0.25)
                    got = _safe_execute(driver, _COPY_CAPTURE_READ_JS, default=None)
                    if isinstance(got, str) and got.strip():
                        captured = got
                        break
            if captured is not None:
                cache[int(idx)] = (sig, captured)
                used_copy += 1
        if captured is not None:
            text = text.replace(placeholder, captured)
        else:
            text = text.replace(placeholder, fb)
            print("%s ВНИМАНИЕ: код-блок #%s: Monaco недоступен и перехват кнопки Copy "
                  "не сработал — использована только видимая часть, разбор действия "
                  "может не удаться (v86.15)." % (log_tag, idx))
    if clicked_any:
        _safe_execute(driver, _COPY_INTERCEPT_RESTORE_JS, default=None)
    if used_copy:
        print("%s %d код-блок(ов) прочитаны целиком перехватом кнопки Copy (v86.15)."
              % (log_tag, used_copy))
    if used_cache:
        print("%s %d код-блок(ов) взяты из кэша без повторного нажатия Copy (v86.17)."
              % (log_tag, used_cache))
    return text


def _escape_bbcode_py(text: str) -> str:
    """[ и ] -> [lb]/[rb], чтобы сырой текст не ломал BBCode в панели."""
    return text.replace('[', '[lb]').replace(']', '[rb]')


# ---------------------------------------------------------------------------
# Разбор JSON из agent_action (общий для всех сайтов)
# ---------------------------------------------------------------------------

def _strip_code_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r'^```[a-zA-Z_]*\s*', '', raw)
    raw = re.sub(r'```\s*$', '', raw)
    return raw.strip()


def _extract_json_object(raw: str) -> str:
    """Вырезает подстроку от первой '{' до последней '}'."""
    start = raw.find('{')
    end = raw.rfind('}')
    if start == -1 or end == -1 or end < start:
        return raw
    return raw[start:end + 1]


def _extract_first_json_object(raw: str) -> str:
    """v86.7: вырезает ПЕРВЫЙ сбалансированный JSON-объект (учитывая строки
    и экранирование). _extract_json_object режет от первой '{' до ПОСЛЕДНЕЙ
    '}' — если после действия в ответе шёл ещё текст с '}' («Готово :}»),
    в кандидат попадал мусор. ОБЕ версии остаются кандидатами разбора: при
    битом экранировании кавычек баланс может закрыться раньше времени, и
    тогда честнее жадный вырез + починки кавычек."""
    start = raw.find('{')
    if start == -1:
        return raw
    depth = 0
    in_string = False
    escape = False
    for j in range(start, len(raw)):
        ch = raw[j]
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
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return raw[start:j + 1]
    return _extract_json_object(raw)


def _escape_raw_newlines_in_strings(raw: str) -> str:
    """Экранирует "голые" переносы строк внутри JSON-строк."""
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


# v86.7: образец `"знач"  "ключ": ...` — модель забыла запятую между полями.
_MISSING_COMMA_KEY_RE = re.compile(r'"(?:[^"\\\n]|\\.){0,64}"\s*:')


def _repair_unescaped_inner_quotes(raw: str) -> str:
    """Достраивает недостающее экранирование '"' внутри строковых значений JSON.

    Модель иногда присылает НЕсогласованное экранирование кавычек внутри
    длинного строкового значения — типичный случай — .tscn-контент в поле
    "content"/"replace", где рядом оказываются id=\\"1_player\\" (кавычки
    экранированы) и id="2_icon" (не экранированы) в ОДНОЙ JSON-строке.
    Обычный json.loads() принимает первую неэкранированную кавычку за конец
    строки и обрывает разбор посреди значения — весь блок agent_action
    считается битым, хотя реально повреждён только один шаг.

    Эвристика: пока мы внутри JSON-строки и встречаем '"', смотрим на
    следующий (после пробелов/переносов) символ. Если это ',', '}', ':'
    или конец текста — кавычка действительно ЗАКРЫВАЕТ строку (обычная
    граница JSON: конец значения перед следующим полем/концом объекта).
    Иначе — это НЕэкранированная кавычка ВНУТРИ значения; достраиваем перед
    ней '\\' и продолжаем читать строку дальше.

    ВАЖНО: ']' сознательно НЕ входит в список "разрешающих" границ — иначе
    ломается на .tscn-синтаксисе с квадратными скобками (PackedStringArray,
    Vector2 в массивах и т.п. внутри самого текста .tscn): там ']' очень
    часто идёт сразу после закрывающей кавычки атрибута ВНУТРИ содержимого
    файла, а не как разделитель JSON-массива шагов — раньше это приводило к
    ложному обрыву строки на первом же .tscn-массиве. Это была найдена и
    исправлена ошибка при разработке этой функции.
    """
    if not raw:
        return raw
    out = []
    in_string = False
    escape = False
    n = len(raw)
    i = 0
    while i < n:
        ch = raw[i]
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue
        if escape:
            out.append(ch)
            escape = False
            i += 1
            continue
        if ch == '\\':
            out.append(ch)
            escape = True
            i += 1
            continue
        if ch == '"':
            j = i + 1
            while j < n and raw[j] in ' \t\r\n':
                j += 1
            nxt = raw[j] if j < n else ''
            if nxt == '' or nxt in ',}:':
                out.append(ch)
                in_string = False
                i += 1
                continue
            # v86.7: пропущенная запятая между полями: `"знач" "ключ": ...` —
            # следующий непробельный символ — кавычка, за которой ключ с ':'.
            # Раньше кавычка ключа ошибочно экранировалась и два поля
            # склеивались в одно значение. Закрываем строку и достраиваем ','.
            if nxt == '"' and _MISSING_COMMA_KEY_RE.match(raw, j):
                out.append('",')
                in_string = False
                i += 1
                continue
            out.append('\\"')
            i += 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


_PARSE_STATS = {"ok_first": 0, "ok_repaired": 0, "ok_json_repair": 0, "fail": 0, "ref_missing": 0}


def get_parse_stats():
    """v86.7: счётчики разбора agent_action за жизнь процесса: сразу /
    с починкой / только json_repair / провал. По ним видно, что реально
    хрупко в бою, а не в теории."""
    return dict(_PARSE_STATS)


_CORPUS_MAX_FILES = 200


def _corpus_dir():
    """v86.7: папка «золотого корпуса» — сырые ответы, которые разобрать не
    удалось. По умолчанию parser_corpus рядом с сервером; путь можно
    переопределить переменной окружения GODOT_AGENT_CORPUS_DIR."""
    base = os.environ.get("GODOT_AGENT_CORPUS_DIR")
    if base:
        return base
    try:
        root = os.path.dirname(os.path.abspath(sys.argv[0]))
    except Exception:
        root = "."
    return os.path.join(root, "parser_corpus")


def _save_corpus_sample(raw, error):
    """v86.7: сохраняет неразобранный ответ в золотой корпус — selfcheck
    (РАЗДЕЛ 26) прогоняет корпус через parse_action_json, так каждый боевой
    сбой навсегда становится регресс-тестом. Ошибки глотаются: сбор корпуса
    не должен мешать работе. Возвращает путь файла или None."""
    try:
        if not (raw or "").strip():
            return None
        d = _corpus_dir()
        if not os.path.isdir(d):
            os.makedirs(d)
        existing = [f for f in os.listdir(d) if f.endswith(".txt")]
        if len(existing) >= _CORPUS_MAX_FILES:
            return None
        path = os.path.join(d, "fail_%d.txt" % int(time.time() * 1000))
        with open(path, "w", encoding="utf-8") as f:
            f.write(u"# parse error: %s\n" % (error or ""))
            f.write(raw)
        return path
    except Exception:
        return None


def _build_candidates(raw):
    """v86.7: упорядоченный список (метка, текст) кандидатов разбора БЕЗ
    дублей — раньше комбинации починок давали одинаковые строки, и
    json.loads гонялся по мегабайтным дублям впустую. Метка попадает в лог
    метрик, чтобы было видно, какая починка спасла разбор."""
    base = _strip_code_fences(raw)
    pairs = [(u"как есть", base),
             (u"первый объект {…}", _extract_first_json_object(base)),
             (u"жадный вырез {…}", _extract_json_object(base))]
    for label, cand in list(pairs):
        esc = _escape_raw_newlines_in_strings(cand)
        rep = _repair_unescaped_inner_quotes(cand)
        rep_esc = _repair_unescaped_inner_quotes(esc)
        pairs.extend([
            (label + u" + запятые", _remove_trailing_commas(cand)),
            (label + u" + переносы", esc),
            (label + u" + переносы + запятые", _remove_trailing_commas(esc)),
            (label + u" + кавычки", rep),
            (label + u" + кавычки + запятые", _remove_trailing_commas(rep)),
            (label + u" + переносы + кавычки", rep_esc),
            (label + u" + переносы + кавычки + запятые", _remove_trailing_commas(rep_esc)),
        ])
    for k, cand in enumerate(_find_action_json_candidates(base)):
        pairs.append((u"вложенный объект №%d" % (k + 1), cand))
    seen = set()
    out = []
    for label, cand in pairs:
        if cand and cand not in seen:
            seen.add(cand)
            out.append((label, cand))
    return out


_REF_BLOCK_RE_CACHE = {}
_REF_BLOCK_LENIENT_RE_CACHE = {}


def _extract_ref_block(raw, label):
    """v86.9: ищет тело content_ref/search_ref/replace_ref — сырой блок
    ===МЕТКА===\n...\n===END_МЕТКА=== в тексте actionRaw (raw), ПОСЛЕ JSON,
    но внутри того же ```agent_action. Регэксп привязан к конкретной метке
    из самого JSON, а не угадывает границы вслепую — случайное "===" в
    комментарии кода не совпадёт с чужой меткой (не тот label/END_label).

    v86.18 (терпимый разбор «невалидных» ответов): если строгий блок не
    найден (модель забыла или оборвала ===END_МЕТКА===), пробуем терпимый
    вариант: тело от ===МЕТКА=== до СЛЕДУЮЩЕГО маркера вида ===ЧТО-ТО===
    (другая метка, чужой END, ===DONE===) или до конца текста. Лучше принять
    содержимое без идеальной обёртки (с громким предупреждением в консоли
    и последующей проверкой линтерами), чем отбросить весь шаг плана."""
    if not raw or not label or not isinstance(label, str):
        return None
    pat = _REF_BLOCK_RE_CACHE.get(label)
    if pat is None:
        pat = re.compile(
            r"===\s*" + re.escape(label) + r"\s*===\r?\n(.*?)\r?\n===\s*END_" + re.escape(label) + r"\s*===",
            re.DOTALL,
        )
        _REF_BLOCK_RE_CACHE[label] = pat
    m = pat.search(raw)
    if m:
        return m.group(1)
    lpat = _REF_BLOCK_LENIENT_RE_CACHE.get(label)
    if lpat is None:
        lpat = re.compile(
            r"===\s*" + re.escape(label) + r"\s*===\r?\n(.*?)"
            r"(?=\r?\n===[^\r\n]{0,120}===[ \t]*(?:\r?\n|$)|\Z)",
            re.DOTALL,
        )
        _REF_BLOCK_LENIENT_RE_CACHE[label] = lpat
    m = lpat.search(raw)
    if not m:
        return None
    body = m.group(1)
    if not body.strip():
        return None
    print(u"[parser_base] ВНИМАНИЕ: у метки %s не найден закрывающий ===END_%s=== — "
          u"тело принято до следующего маркера/конца текста (терпимый разбор, "
          u"v86.18). Содержимое могло быть оборвано — проверь итоговый файл."
          % (label, label))
    return body


_REF_FIELD_MAP = (("content_ref", "content"), ("search_ref", "search"), ("replace_ref", "replace"))


def _resolve_one_ref(step, raw, missing):
    """Подставляет *_ref в обычные текстовые поля ОДНОГО действия/шага плана."""
    if not isinstance(step, dict):
        return
    for ref_key, target_key in _REF_FIELD_MAP:
        label = step.get(ref_key)
        if not label:
            continue
        body = _extract_ref_block(raw, label)
        if body is None:
            missing.append(label)
            continue
        step[target_key] = body
        step.pop(ref_key, None)


def _resolve_content_refs(obj, raw):
    """v86.9: превращает content_ref/search_ref/replace_ref в обычные
    content/search/replace ДО того, как action уйдёт в main.py — вся
    остальная система (валидация плана, patch на диск, tscn-линт,
    self-heal, mini-lich) работает НЕИЗМЕНЁННОЙ, видя только привычные
    поля. Возвращает (obj, missing_labels): missing_labels — метки, для
    которых тело не найдено (сигнал на self-heal просить модель переслать)."""
    if not isinstance(obj, dict):
        return obj, []
    missing = []
    _resolve_one_ref(obj, raw, missing)
    steps = obj.get("steps")
    if isinstance(steps, list):
        for step in steps:
            _resolve_one_ref(step, raw, missing)
    return obj, missing


def parse_action_json(raw: str):
    """Пытается распарсить JSON блока agent_action.
    Возвращает (dict_or_None, error_message_or_None).

    v86.7: кандидаты без дублей и с метками (_build_candidates); среди
    успешно разобранных предпочитается объект С КЛЮЧОМ "action" — раньше
    побеждал ПЕРВЫЙ разобравшийся кандидат, даже если это был посторонний
    JSON-фрагмент из текста ответа. Провалы копятся в золотой корпус
    (_save_corpus_sample), счётчики — в _PARSE_STATS."""
    if raw is None:
        return None, None
    # v86.2: невидимые символы из DOM (NBSP/NUL/zero-width) ломают json.loads
    raw = sanitize_llm_text(raw)
    candidates = _build_candidates(raw)
    last_error = None
    winner = None
    win_idx = -1
    fallback = None
    fallback_idx = -1
    for idx, (_label, cand) in enumerate(candidates):
        try:
            obj = json.loads(cand)
        except Exception as e:
            last_error = str(e)
            continue
        if isinstance(obj, dict) and obj.get("action"):
            winner, win_idx = obj, idx
            break
        if fallback is None:
            fallback, fallback_idx = obj, idx
    if winner is None and fallback is not None:
        winner, win_idx = fallback, fallback_idx
    if winner is not None:
        if win_idx == 0:
            _PARSE_STATS["ok_first"] += 1
        else:
            _PARSE_STATS["ok_repaired"] += 1
            print(u"[parser_base] JSON разобран починкой «%s» (итого: сразу=%d, починкой=%d, json_repair=%d, провал=%d)"
                  % (candidates[win_idx][0], _PARSE_STATS["ok_first"], _PARSE_STATS["ok_repaired"],
                     _PARSE_STATS["ok_json_repair"], _PARSE_STATS["fail"]))
        winner, _missing_refs = _resolve_content_refs(winner, raw)
        if _missing_refs:
            _PARSE_STATS["ref_missing"] += 1
            _ref_err = (u"не найдено тело для метки(ок) %s — ожидался блок ===МЕТКА===...===END_МЕТКА=== "
                        u"внутри того же блока agent_action, после JSON"
                        % u", ".join(sorted(set(_missing_refs))))
            saved = _save_corpus_sample(raw, _ref_err)
            if saved:
                print(u"[parser_base] для content_ref/search_ref/replace_ref не найдено тело — образец сохранён в золотой корпус: %s" % saved)
            return None, _ref_err
        return winner, None
    try:
        from json_repair import repair_json
        fixed = repair_json(_extract_json_object(_strip_code_fences(raw)))
        obj = json.loads(fixed)
        _PARSE_STATS["ok_json_repair"] += 1
        print(u"[parser_base] JSON разобран только внешним json_repair (итого: сразу=%d, починкой=%d, json_repair=%d, провал=%d)"
              % (_PARSE_STATS["ok_first"], _PARSE_STATS["ok_repaired"],
                 _PARSE_STATS["ok_json_repair"], _PARSE_STATS["fail"]))
        obj, _missing_refs2 = _resolve_content_refs(obj, raw)
        if _missing_refs2:
            _PARSE_STATS["ref_missing"] += 1
            _ref_err2 = (u"не найдено тело для метки(ок) %s — ожидался блок ===МЕТКА===...===END_МЕТКА=== "
                         u"внутри того же блока agent_action, после JSON"
                         % u", ".join(sorted(set(_missing_refs2))))
            return None, _ref_err2
        return obj, None
    except Exception as e:
        last_error = "%s; json_repair: %s" % (last_error, e)
    _PARSE_STATS["fail"] += 1
    saved = _save_corpus_sample(raw, last_error)
    if saved:
        print(u"[parser_base] ответ не разобран — образец сохранён в золотой корпус: %s" % saved)
    return None, last_error


def _looks_json_balanced(raw: str) -> bool:
    """Грубая проверка баланса скобок/кавычек."""
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


def _find_action_json_candidates(raw: str):
    """Страховка на случай, если сайт отрисует блок agent_action ВНЕ
    ожидаемых тегов (не в <pre>/<code>, а обычным текстом ответа) —
    ищет ВСЕ подстроки, похожие на JSON-объект agent_action, начиная от
    каждой '{', после которой вскоре встречается '"action"', и вырезает
    сбалансированный (с учётом JSON-строк) объект до парной '}'."""
    out = []
    if not raw:
        return out
    n = len(raw)
    i = 0
    while i < n:
        if raw[i] != '{':
            i += 1
            continue
        if '"action"' not in raw[i:i + 40]:
            i += 1
            continue
        depth = 0
        in_string = False
        escape = False
        j = i
        end = -1
        while j < n:
            ch = raw[j]
            if in_string:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = j
                        break
            j += 1
        if end != -1:
            out.append(raw[i:end + 1])
            i = end + 1
        else:
            i += 1
    return out


# ---------------------------------------------------------------------------
# Терпимый (lenient) разбор action=plan: битый ОДИН шаг не должен ронять
# весь план (v44). См. подробный комментарий над _reply_with_self_heal
# в main.py про мотивацию и общую схему восстановления.
# ---------------------------------------------------------------------------

def _extract_step_candidates(raw: str):
    """Вырезает СЫРЫЕ подстроки отдельных шагов из "steps": [...] с учётом
    баланса скобок и JSON-строк — работает, даже если JSON плана целиком не
    парсится (например, ОДИН шаг содержит несогласованное экранирование
    кавычек). Возвращает список сырых текстов "{...}" (по одному на шаг, в
    порядке появления в тексте) или [] если "steps": [ вообще не найдено.
    """
    out = []
    if not raw:
        return out
    m = re.search(r'"steps"\s*:\s*\[', raw)
    if not m:
        return out
    n = len(raw)
    i = m.end()          # сразу после '[' списка шагов
    bracket_depth = 1    # мы уже внутри этой '['
    in_string = False
    escape = False
    obj_start = None
    obj_depth = 0
    while i < n and bracket_depth > 0:
        ch = raw[i]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
        elif ch == '{':
            if obj_start is None:
                obj_start = i
            obj_depth += 1
        elif ch == '}':
            obj_depth -= 1
            if obj_depth == 0 and obj_start is not None:
                out.append(raw[obj_start:i + 1])
                obj_start = None
        elif ch == '[':
            bracket_depth += 1
        elif ch == ']':
            bracket_depth -= 1
        i += 1
    return out


def parse_plan_lenient(raw: str):
    """Терпимый разбор ответа модели, похожего на action=plan, когда обычный
    parse_action_json не смог разобрать его ЦЕЛИКОМ (обычно из-за
    несогласованного экранирования кавычек внутри содержимого ОДНОГО шага —
    например, .tscn-контента). Разбирает КАЖДЫЙ шаг из "steps": [...] ПО
    ОТДЕЛЬНОСТИ, чтобы один битый шаг не ронял остальные, уже корректные.

    Возвращает {"description": str, "good_steps": [{"index", "step"}, ...],
    "bad_steps": [{"index", "raw", "error"}, ...]} — или None, если raw
    вообще не похож на план (нет ни "action":"plan", ни "steps": [ в тексте).
    """
    if not raw:
        return None
    base = _strip_code_fences(raw)
    if '"plan"' not in base or '"action"' not in base:
        return None
    step_candidates = _extract_step_candidates(base)
    if not step_candidates:
        return None
    description = ""
    dm = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', base)
    if dm:
        try:
            description = json.loads('"' + dm.group(1) + '"')
        except Exception:
            description = dm.group(1)
    good_steps, bad_steps = [], []
    for idx, cand in enumerate(step_candidates):
        step_obj, err = parse_action_json(cand)
        if isinstance(step_obj, dict) and step_obj.get("action"):
            good_steps.append({"index": idx, "step": step_obj})
        else:
            bad_steps.append({"index": idx, "raw": cand, "error": err or "не удалось разобрать JSON шага"})
    return {"description": description, "good_steps": good_steps, "bad_steps": bad_steps}


# ---------------------------------------------------------------------------
# Базовый класс парсера сайта
# ---------------------------------------------------------------------------

class BaseSiteParser:
    """Общий конвейер «отправить промпт -> дождаться -> прочитать ответ».

    Наследник обязан переопределить: count_answers, answer_len,
    extract_answer, find_input, insert_input, submit.
    Остальное — по желанию (значения по умолчанию безопасны).
    """

    LOG_TAG = "parser"            # префикс для печати в лог
    WINDOW_URL_MATCH = ""         # подстрока адреса вкладки сайта
    START_PHASE = "жду начала ответа"

    TIMEOUT = 900                 # общий лимит ожидания ответа, с
    QUIET_PERIOD = 2.5            # тишина (длина не растёт, генерации нет), с
    HARD_QUIET_PERIOD = 45.0      # тишина по длине даже при «генерации», с
    POLL_INTERVAL = 0.25          # период опроса, с
    POST_QUIET_GRACE = 6.0        # добор после тишины (обрыв JSON и т.п.), с
    INPUT_RETRIES = 3
    # сколько раз повторить submit, если confirm_sent вернул False (сообщение не ушло) —
    # прежде чем сдаваться и показывать ошибку пользователю.
    SEND_RETRIES = 2

    # ---- сайт-специфичные методы (переопределяются наследниками) ----

    def count_answers(self, driver):
        """Сколько ответов модели сейчас на странице."""
        raise NotImplementedError

    def answer_len(self, driver):
        """Длина текста ПОСЛЕДНЕГО ответа (без «размышлений»)."""
        raise NotImplementedError

    def answer_preview(self, driver):
        """Хвост ответа для живой трансляции (опционально)."""
        return ""

    def answer_stream(self, driver):
        """Полный текст ответа для живого стрима (опционально)."""
        return ""

    def is_generating(self, driver):
        """Идёт ли генерация прямо сейчас (опционально, подстраховка)."""
        return False

    def extract_answer(self, driver):
        """Полное извлечение: {'text': BBCode, 'actionRaw': str|None, 'error': ...}."""
        raise NotImplementedError

    def extract_raw_fallback(self, driver):
        """Грубое извлечение для «плана Б» (опционально):
        {'text': str, 'actionRaw': str|None} или None."""
        return None

    def get_live_activity(self, driver):
        """Чем модель занята сейчас: {'code': bool, 'lang': str} (опционально)."""
        return {"code": False, "lang": ""}

    def find_input(self, driver):
        """Возвращает элемент поля ввода или None."""
        raise NotImplementedError

    def insert_input(self, driver, el, prompt):
        """Вставляет текст промпта в поле ввода."""
        raise NotImplementedError

    def before_submit(self, driver, el):
        """Де����твия между вставкой и отправкой (опц��онально)."""
        pass

    def submit(self, driver, el):
        """Отправляет сообщение."""
        raise NotImplementedError

    def after_submit(self, driver, el):
        """Действия сразу после отправки, например запасной клик (опционально)."""
        pass

    # ---- общая логика (менеджер парсинга) ----

    def confirm_sent(self, driver, el):
        """Убедиться, что сообщение реально ушло (наследник может проверить
        поле ввода). По умолчанию считаем, что отправлено."""
        return True

    def _log(self, msg):
        print("[%s] %s" % (self.LOG_TAG, msg))

    def switch_to_site_window(self, driver, prefer_url=None):
        """Переключается на вкладку своего сайта.

        v54: приоритет выбора вкладки:
          1) вкладка с ТОЧНЫМ адресом prefer_url (адрес текущего чата);
          2) ТЕКУЩАЯ вкладка, если она уже на нужном сайте;
          3) первая попавшаяся вкладка сайта (старое поведение).
        Раньше всегда бралась первая попавшаяся — при двух открытых вкладках
        одного сайта агент печатал в ЧУЖОЙ (старый) чат."""
        if not self.WINDOW_URL_MATCH:
            return

        def _path(u):
            return (u or "").split("://", 1)[-1].split("?", 1)[0].split("#", 1)[0].rstrip("/")

        def _cur_url():
            try:
                return driver.current_url or ""
            except WebDriverException:
                return ""

        cur = _cur_url()
        if prefer_url:
            want = _path(prefer_url)
            if want and _path(cur) == want:
                return
            if want:
                try:
                    cur_handle = None
                    try:
                        cur_handle = driver.current_window_handle
                    except WebDriverException:
                        pass
                    for handle in driver.window_handles:
                        driver.switch_to.window(handle)
                        if _path(driver.current_url or "") == want:
                            return
                    if cur_handle is not None:
                        driver.switch_to.window(cur_handle)
                except WebDriverException:
                    pass
                cur = _cur_url()
        # Текущая вкладка уже на нужном сайте — остаёмся на ней (не прыгаем
        # на первую попавшуюся вкладку с тем же доменом — там может быть ДРУГОЙ чат).
        if self.WINDOW_URL_MATCH in cur:
            return
        try:
            for handle in driver.window_handles:
                driver.switch_to.window(handle)
                if self.WINDOW_URL_MATCH in (driver.current_url or ""):
                    return
        except WebDriverException:
            pass

    def wait_for_new_answer(self, driver, initial_count, timeout=None,
                            quiet_period=None, hard_quiet_period=None,
                            poll_interval=None, post_quiet_grace=None,
                            progress_cb=None, cancel_cb=None):
        """Ждёт новый ответ модели и возвращает результат extract_answer().
        Завершение — стабилизация длины текста ответа + проверка целостности
        JSON действия; всё через методы наследника.

        v86.10 (шаг 4 плана «улучшение парсера»): конвейер ожидания
        переписан как явная состояние-машина вместо пяти самостоятельных
        вложенных while-циклов, каждый со своим расчётом таймаута. Порядок
        проверок и ВСЕ сообщения об ошибках сохранены 1-в-1 — это чистый
        рефакторинг структуры, а не изменение поведения. Таблица переходов:

            WAIT_NEW_MESSAGE -> WAIT_FIRST_TEXT -> STABILIZE -> VERIFY_COMPLETE -> DONE
                                                        ^               |
                                                        |               v
                                                        +----- ANTI_STALE
                                            (VERIFY_COMPLETE прочитал ответ,
                                             который был на странице ещё ДО
                                             отправки — ждём настоящий новый)

        Из любого состояния — TimeoutError по общему дедлайну `start + timeout`.
        Сторожевой таймер (`_try_salvage`, см. ниже) проверяется во всех
        состояниях одинаково и может вернуть результат в обход всего конвейера.
        """
        timeout = self.TIMEOUT if timeout is None else timeout
        quiet_period = self.QUIET_PERIOD if quiet_period is None else quiet_period
        hard_quiet_period = self.HARD_QUIET_PERIOD if hard_quiet_period is None else hard_quiet_period
        poll_interval = self.POLL_INTERVAL if poll_interval is None else poll_interval
        post_quiet_grace = self.POST_QUIET_GRACE if post_quiet_grace is None else post_quiet_grace
        start = time.time()

        def _deadline_hit():
            # v86.10: раньше каждый из пяти циклов сам писал
            # "time.time() - start < timeout" -- при добавлении нового цикла
            # легко было перепутать "<" и ">=" (так уже бывало в истории правок).
            # Теперь дедлайн считается в одном месте.
            return time.time() - start >= timeout

        def _report(phase, chars=0, preview=None, stream=None):
            # Кнопка «Стоп»: _report вызывается на КАЖДОЙ итерации всех фаз
            # ожидания — единая точка проверки отмены.
            if cancel_cb is not None and cancel_cb():
                raise ParserCancelled("остановлено пользователем")
            # Живая трансляция: снимок состояния уходит в main.py -> /chat/progress.
            if progress_cb is None:
                return
            try:
                progress_cb({
                    "phase": phase,
                    "chars": int(chars or 0),
                    "elapsed": int(time.time() - start),
                    "preview": preview or "",
                    "stream": stream or "",
                })
            except Exception:
                pass

        # СТОРОЖЕВОЙ ТАИМЕР: даже если счётчик ответов или длина «сломались»
        # (у «думающих» моделей другая разметка ответа, сайт обновил DOM
        # и т.п.), раз в ~20 с читаем ответ целиком через extract_answer;
        # если он ОТЛИЧАЕтССЙ от снятого до отправки (JSON действия
        # сбалансирован), генерация не идёт и текст не меняется два замера
        # подряд — возвращаем его как результат, не дожидаясь зависшего
        # основного ожидания. Это лечит «ответ на сайте есть, а агент
        # пишет „модель думает…“ бесконечно».
        _base = self.extract_answer(driver) or {}
        _baseline_sig = (_base.get("text") or "") + "\x00" + (_base.get("actionRaw") or "")
        _salv = {"ts": time.time(), "sig": None}
        _diag = {"ts": time.time()}
        # v56: снимок «живого» текста ПОСЛЕДНЕГО блока до отправки — пока модель
        # «думает» (генерация уже идёт, но новый блок ответа в DOM ещё не появился),
        # answer_len/answer_preview/answer_stream у некоторых сайтов (DeepSeek) читают
        # ПОСЛЕДНИЙ существующий блок — это ещё Старый ответ. Не транслируем его в панель
        # как «живую генерацию», пока не увидим либо рост счётчика реплик, либо текст,
        # отличный от этого снимка.
        try:
            _baseline_stream_txt = self.answer_stream(driver) or ""
        except Exception:
            _baseline_stream_txt = ""

        def _try_salvage():
            if time.time() - _salv["ts"] < 20.0:
                return None
            _salv["ts"] = time.time()
            r = self.extract_answer(driver) or {}
            raw = r.get("actionRaw")
            sig = (r.get("text") or "") + "\x00" + (raw or "")
            if not sig.replace("\x00", "").strip():
                _salv["sig"] = None
                return None
            if (sig == _baseline_sig or sig in getattr(self, "_returned_sigs", ())
                    or self.is_generating(driver)):
                _salv["sig"] = None
                return None
            if raw is not None and not _looks_json_balanced(
                    _extract_json_object(_strip_code_fences(raw))):
                _salv["sig"] = None
                return None
            if _salv["sig"] == sig:
                self._log("сторожевой таймер: готовый ответ найден на странице — "
                          "забираю его в обход зависшего ожидания.")
                return r
            _salv["sig"] = sig
            return None

        def _maybe_diag(stage):
            # Диагностика в лог сервера раз в 30 с — если ожидание опять
            # зависнет, по этим строкам будет видно, что иденно сломалось.
            if time.time() - _diag["ts"] < 30.0:
                return
            _diag["ts"] = time.time()
            try:
                self._log("жду ответ [%s]: answers=%s (было %s), len=%s, generating=%s"
                          % (stage, self.count_answers(driver), initial_count,
                             self.answer_len(driver), self.is_generating(driver)))
            except Exception:
                pass

        def _sig_of(r):
            return (((r or {}).get("text") or "") + "\x00" + ((r or {}).get("actionRaw") or ""))

        def _is_stale(r):
            s = _sig_of(r)
            if not s.replace("\x00", "").strip():
                return False
            # v53: счётчик реплик может УМЕНьШАТЬСя (сайт сворачивает/перестраивает
            # DOM; у DeepSeek наблюдали answers=2 (было 3)) — поэтому «новых реплик
            # нет» проверяем как «счётчик НЕ ВОСОСЛ», а не «равен исходному».
            if self.count_answers(driver) > initial_count:
                return False
            # После перестройки DOM последним блоком может оказаться и более старый
            # ответ, не совпадающий со снимком до отправки, — ловим его по памяти
            # ранее возвращённых ответов (_returned_sigs).
            return s == _baseline_sig or s in getattr(self, "_returned_sigs", ())

        # Общее изменяемое состояние конвейера — общий словарь вместо
        # раскиданных по функции локальных переменных, чтобы каждое
        # состояние-обработчик ниже могло читать/писать его через замыкание.
        st = {
            "preview_txt": "",
            "stream_txt": "",
            "phase_txt": "пишет ответ…",
            "last_preview_ts": 0.0,
            "last_length": -1,
            "quiet_since": None,
            "length_only_quiet_since": None,
            "revealed": False,  # v56: True, когда на странице виден ДЕИСТВИТЕЛьНО новый текст
            "result": None,
        }

        ST_WAIT_NEW_MESSAGE = "wait_new_message"
        ST_WAIT_FIRST_TEXT = "wait_first_text"
        ST_STABILIZE = "stabilize"
        ST_VERIFY_COMPLETE = "verify_complete"
        ST_ANTI_STALE = "anti_stale"
        ST_DONE = "done"

        def _state_wait_new_message():
            # 1) ждём появления нового ответа/реплики модели.
            # важно: сравниваем с initial_count на Неравенство (а не только на рост),
            # потому что сайт иногда перестраивает DOM так, что старый блок удаляется
            # раньше, чем появится новый (счётчик временно уменьшается), и строгое
            # "только больше" никогда не срабатывало и ждало сторожевого таймера (~20 с)
            # вместо того, чтобы сразу заметить изменившийся счётчик. Аналогично выходим
            # раньше, если генерация уже идёт — это уже достаточный сигнал, что новый ответ
            # начался, даже если счётчик пока не изменился.
            while not _deadline_hit():
                if self.count_answers(driver) != initial_count or self.is_generating(driver):
                    return ST_WAIT_FIRST_TEXT
                got = _try_salvage()
                if got is not None:
                    st["result"] = got
                    return ST_DONE
                _maybe_diag("жду начала ответа")
                _report(self.START_PHASE)
                time.sleep(poll_interval)
            raise TimeoutError("Новый ответ модели не появился.")

        def _state_wait_first_text():
            # 2) ждём начала генерации ИЛИ первого текста ответа
            while not _deadline_hit():
                if self.answer_len(driver) > 0 or self.is_generating(driver):
                    return ST_STABILIZE
                got = _try_salvage()
                if got is not None:
                    st["result"] = got
                    return ST_DONE
                _maybe_diag("жду первый текст")
                _report("модель думает…")
                time.sleep(poll_interval)
            # Как и в оригинале: эта фаза не бросает TimeoutError сама — если
            # общий дедлайн истёк именно тут, STABILIZE увидит это на первой
            # же проверке и бросит тот же TimeoutError, что и раньше.
            return ST_STABILIZE

        def _state_stabilize():
            # 3) стабилизация текста + живая трансляция прогресса
            while not _deadline_hit():
                length = self.answer_len(driver)   # длина тОЛько ответа, без «мыслей»
                generating = self.is_generating(driver)
                now = time.time()
                if length == st["last_length"]:
                    if st["length_only_quiet_since"] is None:
                        st["length_only_quiet_since"] = now
                    if not generating:
                        if st["quiet_since"] is None:
                            st["quiet_since"] = now
                    else:
                        st["quiet_since"] = None
                else:
                    st["quiet_since"] = None
                    st["length_only_quiet_since"] = None
                if length > 0:
                    # v56: пока не увидели рост счётчика реплик или текст, отличный от
                    # того, что было ДО отправки — это ещё Старый ответ (модель «думает»,
                    # генерация уже идёт, но новый блок в DOM не появился). Сравниваем со
                    # свежим текстом (а не с закешированным 1 раз/сек preview_txt/stream_txt
                    # ниже), иначе сам момент перехода мог бы на мгновение показать в ленте
                    # ещё старый кеш.
                    if not st["revealed"]:
                        try:
                            _live_now = self.answer_stream(driver) or ""
                        except Exception:
                            _live_now = st["stream_txt"]
                        st["revealed"] = (self.count_answers(driver) > initial_count
                                          or _live_now != _baseline_stream_txt)
                        if st["revealed"]:
                            st["stream_txt"] = _live_now
                            st["preview_txt"] = self.answer_preview(driver)
                            st["last_preview_ts"] = now
                    if st["revealed"] and now - st["last_preview_ts"] >= 1.0:
                        st["preview_txt"] = self.answer_preview(driver)
                        st["stream_txt"] = self.answer_stream(driver)
                        st["last_preview_ts"] = now
                    # v86.8: если в потоке уже виден служебный маркер конца ответа — модель
                    # сама сообщила, что дописала: выходим из цикла стабилизации сразу, ещё до
                    # истечения quiet_period/hard_quiet_period. VERIFY_COMPLETE всё равно ещё раз
                    # проверит is_generating/JSON/пустоту, поэтому ранний выход ничего не пропускает.
                    if st["revealed"] and _has_done_marker(st["stream_txt"]):
                        self._log("маркер ===DONE=== найден в потоке ответа — завершаю ожидание досрочно вместо тихого периода.")
                        break
                    if st["revealed"]:
                        activity = self.get_live_activity(driver) or {}
                        if activity.get("code"):
                            lang = activity.get("lang") or ""
                            if lang == "agent_action":
                                st["phase_txt"] = "готовит действие для проекта…"
                            elif lang:
                                st["phase_txt"] = "пишет код (" + lang + ")…"
                            else:
                                st["phase_txt"] = "пишет код…"
                        else:
                            st["phase_txt"] = "пишет ответ…"
                        _report("модель " + st["phase_txt"], chars=length, preview=st["preview_txt"], stream=st["stream_txt"])
                    else:
                        _report("модель думает…")
                got = _try_salvage()
                if got is not None:
                    st["result"] = got
                    return ST_DONE
                _maybe_diag("стабилизация")
                # ВАЖНО: не завершаем, пока в ОТВЕТЕ нет ни одного символа.
                if length > 0:
                    if st["quiet_since"] is not None and now - st["quiet_since"] >= quiet_period:
                        break
                    if st["length_only_quiet_since"] is not None and now - st["length_only_quiet_since"] >= hard_quiet_period:
                        break
                st["last_length"] = length
                time.sleep(poll_interval)
            else:
                raise TimeoutError("Генерация не завершилась вовремя.")

            # v56: если настоящий новый ответ так и не появился в DOM к моменту
            # выхода из цикла стабилизации (например, долгое «думанье» дотянулось
            # до hard_quiet_period на старом тексте), preview_txt/stream_txt всё ещё содержат
            # СтАРый ответ — обнуляем их, чтобы он Не утёк в грейс-период.
            if not st["revealed"]:
                st["preview_txt"] = ""
                st["stream_txt"] = ""
            return ST_VERIFY_COMPLETE

        def _state_verify_complete():
            # 4) защита от «ложного завершения»: обрыв JSON / пустой ответ /
            #    генерация ещё идёт.
            grace_start = time.time()
            _report("проверяю, что ответ дописан", chars=max(st["last_length"], 0),
                    preview=st["preview_txt"], stream=st["stream_txt"])
            result = self.extract_answer(driver)
            empty_grace = max(post_quiet_grace, 90.0)
            while True:
                raw = (result or {}).get("actionRaw")
                text = (result or {}).get("text") or ""
                cur_len = self.answer_len(driver)
                still_generating = self.is_generating(driver)
                action_incomplete = raw is not None and not _looks_json_balanced(
                    _extract_json_object(_strip_code_fences(raw)))
                answer_empty = (not text.strip()) and (raw is None)
                if (not still_generating) and cur_len == st["last_length"] and (not action_incomplete) and (not answer_empty):
                    break
                limit = empty_grace if (answer_empty or still_generating) else post_quiet_grace
                if time.time() - grace_start >= limit:
                    break
                time.sleep(0.4)
                result = self.extract_answer(driver)
                st["last_length"] = cur_len
                _report("проверяю, что ответ дописан", chars=max(cur_len, 0),
                        preview=st["preview_txt"], stream=st["stream_txt"])
            # 5) v51: АНТИ-ДУБЛь старого ответа. Если «стабилизировавшийся» результат
            # побайтово совпадает с последним ответом модели, снятым ДО отправки
            # сообщения, и НОВых реплик модели на странице не появилось — значит,
            # прочитан СтАРый ответ (счётчик реплик «мигнул» при перестройке DOM,
            # или модель долго думает, не создав новый блок). такой результат
            # возвращать нельзя — ждём настоящий новый ответ до общего таймаута
            # (передаём эстафету ANTI_STALE).
            st["result"] = result
            if _is_stale(result):
                return ST_ANTI_STALE
            return ST_DONE

        def _state_anti_stale():
            result = st["result"]
            stale_logged = False
            while _is_stale(result):
                if _deadline_hit():
                    raise TimeoutError("Модель не дала НОВЫЙ ответ: на странице только сообщение, "
                                       "которое было там ещё до отправки (дубль не возвращаю).")
                if not stale_logged:
                    self._log("анти-дубль: прочитан ТОТ ЖЕ ответ, что был до отправки, "
                              "новых реплик модели нет — жду настоящий новый ответ.")
                    stale_logged = True
                _report("модель ещё думает…")
                got = _try_salvage()
                if got is not None:
                    st["result"] = got
                    return ST_DONE
                time.sleep(max(poll_interval, 0.25))
                cur = self.extract_answer(driver) or {}
                if _sig_of(cur) == _sig_of(result):
                    continue
                # Текст начал меняться — пошёл настоящий ответ, ждём стабилизации заново.
                stable_since = None
                last_len = -1
                while not _deadline_hit():
                    ln = self.answer_len(driver)
                    now2 = time.time()
                    if ln == last_len and ln > 0 and not self.is_generating(driver):
                        if stable_since is None:
                            stable_since = now2
                        if now2 - stable_since >= quiet_period:
                            break
                    else:
                        stable_since = None
                    _report("модель пишет ответ…", chars=max(ln, 0))
                    last_len = ln
                    time.sleep(poll_interval)
                result = self.extract_answer(driver)
            st["result"] = result
            return ST_DONE

        _STATE_HANDLERS = {
            ST_WAIT_NEW_MESSAGE: _state_wait_new_message,
            ST_WAIT_FIRST_TEXT: _state_wait_first_text,
            ST_STABILIZE: _state_stabilize,
            ST_VERIFY_COMPLETE: _state_verify_complete,
            ST_ANTI_STALE: _state_anti_stale,
        }
        state = ST_WAIT_NEW_MESSAGE
        while state != ST_DONE:
            state = _STATE_HANDLERS[state]()
        return st["result"]
    def extract_answer_robust(self, driver, retries=3, delay=1.5):
        """ПЛАН Б: многоуровневое извлечение ответа.
          1) основной парсер наследника (форматирование + agent_action);
          2) грубый фолбэк наследника — текст без оформления лучше пустоты;
          3) пауза и повтор с нуля (DOM мог перерисоваться во время чтения)."""
        result = None
        for attempt in range(retries):
            result = self.extract_answer(driver) or {}
            text = (result.get("text") or "").strip()
            if text or result.get("actionRaw") is not None:
                if attempt > 0:
                    self._log("План Б: ответ прочитан с попытки %d." % (attempt + 1))
                return result
            raw = self.extract_raw_fallback(driver) or {}
            raw_text = (raw.get("text") or "").strip()
            if raw_text or raw.get("actionRaw") is not None:
                self._log("План Б: основной парсер дал пустоту — использую грубый фолбэк.")
                return {"text": _escape_bbcode_py(raw_text), "actionRaw": raw.get("actionRaw"), "error": None}
            if attempt < retries - 1:
                self._log("Пустой ответ (попытка %d/%d) — жду %s с и читаю заново." % (attempt + 1, retries, delay))
                time.sleep(delay)
        return result or {"text": "", "actionRaw": None, "error": "extraction failed"}

    def send_message_and_get_response(self, driver, prompt, input_retries=None, progress_cb=None, cancel_cb=None, prefer_url=None):
        """Общий конвейер «промпт -> ответ» для любого сайта."""
        retries = input_retries or self.INPUT_RETRIES
        # v54: prefer_url — адрес страницы ТЕКУЩЕГО чата: печатаем именно в его
        # вкладку, а не в первую попавшуюся вкладку этого сайта.
        self.switch_to_site_window(driver, prefer_url=prefer_url)
        from browser_manager import harden_background_tab
        harden_background_tab(driver)
        # v80-wait-before-send: НЕ отправляем новое сообщение, пока модель ещё
        # пишет предыдущий ответ (частый случай — быстрые шаги плана): иначе
        # отправка молча теряется, а ожидание принимает ЕЩЁ ПЕЧАТАЮЩЕЕСЯ старое
        # сообщение за ответ на новый промпт — и настоящий последний ответ
        # остаётся непрочитанным.
        _busy_start = time.time()
        _busy_logged = False
        while time.time() - _busy_start < 240.0:
            try:
                if not self.is_generating(driver):
                    break
            except Exception:
                break
            if not _busy_logged:
                self._log("модель ещё дописывает предыдущий ответ — жду его конца перед отправкой нового сообщения.")
                _busy_logged = True
            if cancel_cb is not None and cancel_cb():
                raise ParserCancelled("остановлено пользователем")
            time.sleep(0.5)
        else:
            self._log("предыдущий ответ пишется дольше 240 с — отправляю новое сообщение как есть.")
        if _busy_logged:
            time.sleep(1.5)  # даём странице дописать DOM до конца
        el = None
        for _ in range(retries):
            el = self.find_input(driver)
            if el:
                break
            time.sleep(0.5)
        if not el:
            raise Exception("Поле ввода не найдено (%s)." % self.LOG_TAG)
        inserted = False
        for _ in range(retries):
            try:
                self.insert_input(driver, el, prompt)
                time.sleep(0.2)
                # v86.7: у contenteditable-полей (див вместо textarea у многих
                # сайтов) нет .value — проверяем и innerText/textContent, иначе
                # удачная вставка считалась провалом («не удалось вставить текст»).
                _val = driver.execute_script(
                    "var e=arguments[0];var t=(e.tagName||'').toUpperCase();"
                    "if(t==='TEXTAREA'||t==='INPUT'){return e.value||'';}"
                    "return e.innerText||e.textContent||'';", el)
                if (_val or "").strip():
                    inserted = True
                    break
            except (JavascriptException, StaleElementReferenceException):
                el = self.find_input(driver)
            time.sleep(0.3)
        if not inserted:
            raise Exception("Не удалось вставить текст в поле ввода (%s)." % self.LOG_TAG)
        self.before_submit(driver, el)
        # v51: снимок ПОСЛЕДНЕГО ответа модели ДО отправки — для анти-дубля
        # (защита от возврата СТАРОГО сообщения вместо нового ответа).
        _pre = self.extract_answer(driver) or {}
        _pre_sig = ((_pre.get("text") or "") + "\x00" + (_pre.get("actionRaw") or ""))
        initial_count = self.count_answers(driver)
        try:
            self.submit(driver, el)
        except StaleElementReferenceException:
            el = self.find_input(driver)
            if el:
                self.submit(driver, el)
        self.after_submit(driver, el)
        sent = self.confirm_sent(driver, el)
        # Сообщение могло не уйти из-за временного глюка сайта (особенно на больших сообщениях/вложениях) —
        # прежде чем сдаваться и терять введённый текст, пробуем повторить отправку (не вставляя текст заново —
        # он всё ещё в поле ввода) несколько раз с нарастающей паузой, давая сайту больше времени на обработку большого текста.
        send_retries = max(0, self.SEND_RETRIES)
        for send_attempt in range(send_retries):
            if sent:
                break
            delay = 1.5 * (send_attempt + 1)
            self._log("сообщение не ушло (повтор %d/%d) — жду %sс и пробую отправить ещё раз." % (send_attempt + 1, send_retries, delay))
            time.sleep(delay)
            try:
                el = self.find_input(driver) or el
                self.before_submit(driver, el)
                self.submit(driver, el)
                self.after_submit(driver, el)
            except (JavascriptException, StaleElementReferenceException) as e:
                self._log("повторная отправка сорвалась с ошибкой: %s" % e)
                continue
            sent = self.confirm_sent(driver, el)
        if not sent:
            # Все повторы исчерпаны, сообщение так и не ушло — НЕ ждём ответ впустую, сразу сообщаем.
            self._log("сообщение НЕ отправилось после %d повтор(ов) — прерываю, ответ не жду." % send_retries)
            return {"text": "[Ошибка]: сообщение не отправилось на сайт даже после %d повтор(ов) "
                            "(текст остался в поле ввода; возможная причина — слишком большой текст сообщения). "
                            "Попробуйте ещё раз." % send_retries,
                    "action": None}
        result = self.wait_for_new_answer(driver, initial_count, progress_cb=progress_cb,
                                          cancel_cb=cancel_cb)
        time.sleep(0.5)
        # ПЛАН Б: основной парсер дал пустоту -> многоуровневое чтение заново.
        empty = (not result) or (
            not ((result.get("text") or "").strip()) and result.get("actionRaw") is None)
        if empty:
            result = self.extract_answer_robust(driver)
            # v51: анти-дубль для «Плана Б» — грубое извлечение могло схватить
            # СТАРЫЙ ответ (тот, что был на странице ещё до отправки). Дубль не
            # возвращаем: лучше явная ошибка, чем повторно выполненный старый план.
            _sig_b = (((result or {}).get("text") or "") + "\x00" + ((result or {}).get("actionRaw") or ""))
            if (_sig_b.replace("\x00", "").strip()
                    and (_sig_b == _pre_sig or _sig_b in getattr(self, "_returned_sigs", ()))
                    and self.count_answers(driver) <= initial_count):
                self._log("анти-дубль (План Б): извлечён тот же ответ, что был до отправки — дубль не возвращаю.")
                return {"text": "[Ошибка]: модель не дала НОВЫЙ ответ (на странице найден только старый). "
                                "Отправьте сообщение ещё раз.",
                        "action": None}
        # v86.2: чистим невидимый мусор из веб-DOM (кейс qwen: NBSP U+00A0, NUL,
        # zero-width) — иначе он попадает в .gd/.tscn и Godot падает на парсинге.
        text = sanitize_llm_text((result or {}).get("text") or "")
        raw_action = sanitize_llm_text((result or {}).get("actionRaw"))
        # v86.8: служебный маркер конца ответа не должен увидеть пользователь в чате.
        text = _strip_done_marker(text)
        error = (result or {}).get("error")
        if error:
            self._log("JS extraction error: %s" % error)
        action = None
        if raw_action is not None:
            action, parse_error = parse_action_json(raw_action)
            if action is None:
                self._log("Не удалось распарсить agent_action: %s" % parse_error)
                self._log("RAW (%d симв.): %s" % (len(raw_action), raw_action[:2000]))
                action = {"action": "parse_error", "raw": raw_action, "error": parse_error}
        # ПЛАН В: основной парсер нигде не нашёл actionRaw (например,
        # сайт отрисовал блок agent_action одиной обратной котировкой вместо
        # ```-блока, и она попала в абзац без особой обработки) — ответ
        # виден в чате, но действие теряется. Страхуемся ещё одним способом:
        # сканируем сырой текст ответа (answer_stream) на встроенный JSON с ключом
        # "action", независимо от того, в какой тег его обёрнул сайт.
        if action is None and raw_action is None:
            try:
                raw_stream = self.answer_stream(driver) or ""
            except Exception:
                raw_stream = ""
            if '"action"' in raw_stream:
                for cand in _find_action_json_candidates(raw_stream):
                    salv_action, _ = parse_action_json(cand)
                    if salv_action is not None:
                        self._log("Страховка (план В): JSON-действие найдено в тексте "
                                  "ответа вне ожидаемых тегов — забираю его.")
                        action = salv_action
                        break
        # v53: запоминаем возвращённый ответ (последние 8) — при следующем ожидании
        # анти-дубль отбрасывает такие ответы, если счётчик реплик модели не вырос
        # (защита от «ответа на старый запрос» после перестройки DOM сайтом).
        _sig_ret = (text or "") + "\x00" + (raw_action or "")
        if _sig_ret.replace("\x00", "").strip():
            _mem = getattr(self, "_returned_sigs", None)
            if _mem is None:
                _mem = []
                self._returned_sigs = _mem
            if _sig_ret in _mem:
                _mem.remove(_sig_ret)
            _mem.append(_sig_ret)
            del _mem[:-8]
        return {"text": text, "action": action}
