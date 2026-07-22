# -*- coding: utf-8 -*-
"""Парсер сайта Qwen (chat.qwen.ai) — v73: боевые селекторы с реальной страницы.

Интерфейс модуля тот же, что у ai_parser/deepseek_parser:
  send_message_and_get_response(driver, prompt, ...) -> {"text", "action"}

Селекторы взяты из реального DOM chat.qwen.ai (июль 2026):
  - ответ модели: div.qwen-chat-message-assistant .response-message-content .qwen-markdown
    (карточка размышлений qwen-chat-thinking-* лежит ВНЕ response-message-content);
  - поле ввода: textarea.message-input-textarea;
  - кнопка отправки: div.chat-prompt-send-button button.send-button (disabled, пока поле пустое);
  - конец генерации: у последнего ответа появились иконки действий в футере.
Если Qwen обновит вёрстку — обнови селекторы здесь.
"""
import time

from selenium.webdriver.common.keys import Keys

from parser_base import (BaseSiteParser, _safe_execute, _extract_json_object,
                         _looks_json_balanced, _strip_code_fences)

_BLOCKS_JS = r"""
function __qwenBlocks() {
    var sels = [
        'div.qwen-chat-message-assistant div.response-message-content div.qwen-markdown',
        'div.qwen-chat-message-assistant div.response-message-content',
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
# v86.16: к длине видимого текста добавляем высоту тел код-блоков (px):
# у виртуализированного Monaco-блока innerText постоянен (~39 видимых
# строк), а высота растёт с каждой новой строкой (~20px) — так метрика
# прогресса видит генерацию до самого конца и quiet-периоды не срабатывают
# посреди ответа.
JS_ANSWER_LEN = _BLOCKS_JS + (
    "var b = __qwenBlocks(); if (!b.length) return -1;"
    " var el = b[b.length-1];"
    " var n = (el.innerText || '').length;"
    " var bodies = el.querySelectorAll('pre.qwen-markdown-code .qwen-markdown-code-body');"
    " for (var i = 0; i < bodies.length; i++) {"
    "   var h = parseFloat((bodies[i].style && bodies[i].style.height) || '0');"
    "   if (!isNaN(h) && h > 0) { n += Math.round(h); }"
    "   else { n += (bodies[i].scrollHeight || 0); }"
    " }"
    " return n;")
JS_ANSWER_TEXT = _BLOCKS_JS + "var b = __qwenBlocks(); return b.length ? (b[b.length-1].innerText || '') : '';"
JS_IS_GENERATING = (
    "var msgs = document.querySelectorAll('div.qwen-chat-message-assistant');"
    " if (msgs.length) { var last = msgs[msgs.length - 1];"
    "   if (!last.querySelector('.response-message-footer .qwen-chat-package-comp-new-action-control-icons')) return true; }"
    " return !!document.querySelector('button[aria-label*=\"Stop\"],"
    " [class*=\"stop\"] button, button[class*=\"stop\"]');")
# v86.12: Qwen periodicheski (chashche na PERVOM soobshchenii v chate) pokazyvaet
# DVA alʹternativnykh otveta ryadom ("Response 1"/"Response 2", smulti-o-*) s
# podskazkoy "Which response do you prefer? Select one to continue." — dialog
# NE prodolzhitsya, poka polzovatel (ili avtomatizatsiya) ne vyberet odin iz
# nikh knopkoy "I prefer this response" (class smulti-make-better). Eti knopki
# poyavlyayutsya TOLʹKO kogda OBE generatsii uzhe zaversheny — poetomu ikh
# prisutstvie v kolichestve >= 2 sluzhit nadezhnym signalom gotovnosti vybora.
# Avtomatizatsiya vsegda vybiraet PERVYY (levyy, "Response 1") variant — eto
# prosto i predskazuemo; poryadok knopok v DOM sovpadaet s poryadkom otvetov
# (podtverzhdeno cherez data-spm-anchor-id i1/i2 na realnom HTML sayta).
JS_DUAL_CHOICE_BUTTON_COUNT = (
    "return document.querySelectorAll('button.smulti-make-better').length;")
JS_CLICK_PREFER_FIRST_RESPONSE = (
    "var btns = document.querySelectorAll('button.smulti-make-better');"
    " if (btns.length) { btns[0].click(); return true; } return false;")
JS_FIND_INPUT = ("return document.querySelector('textarea.message-input-textarea')"
                 " || document.querySelector('textarea#chat-input')"
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
JS_CLICK_SEND = ("var b = document.querySelector('div.chat-prompt-send-button button.send-button');"
                 " if (b && !b.disabled) { b.click(); return true; }"
                 " b = document.querySelector('button[id*=\"send\"],"
                 " button[class*=\"send\"], button[type=\"submit\"]');"
                 " if (b && !b.disabled) { b.click(); return true; } return false;")


# ---------------------------------------------------------------------------
# v86.13/v86.14/v86.15: Qwen рендерит ДЛИННЫЕ блоки кода (в т.ч. agent_action)
# через Monaco-редактор с виртуализацией строк: в DOM существуют только видимые
# строки, причём в произвольном порядке — .innerText даёт неполный и
# перемешанный текст, JSON действия в нём отсутствует. Полный текст собирается
# универсальным помощником из parser_base: модель Monaco -> ПЕРЕХВАТ КНОПКИ
# Copy код-блока (на реальном Qwen глобальный monaco НЕ выставлен — выяснено
# по HTML от пользователя, поэтому рабочий путь — именно перехват Copy) ->
# аварийно видимые строки. Qwen-специфичные селекторы передаются параметрами.
from parser_base import (build_composed_answer_js, build_copy_click_js,
                         missing_ref_bodies, read_composed_answer)

JS_COMPOSED_ANSWER = build_composed_answer_js(
    _BLOCKS_JS, '__qwenBlocks', 'pre.qwen-markdown-code')
# Кнопка Copy — ПЕРВЫЙ .qwen-markdown-code-header-action-item в шапке блока
# (в шапке два значка: Copy и Download; querySelector берёт первый — Copy,
# подтверждено обоими HTML-дампами от пользователя: #icon-line-copy-right идёт
# перед #icon-line-download-02).
JS_COPY_CLICK = build_copy_click_js(
    _BLOCKS_JS, '__qwenBlocks', 'pre.qwen-markdown-code',
    '.qwen-markdown-code-header-action-item')


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
    # v86.12: esli Qwen pokazal vybor "Response 1"/"Response 2" (obe knopki
    # "I prefer this response" uzhe otrisovany — znachit, OBE generatsii
    # zaversheny) — avtomaticheski vybiraem PERVYY variant, chtoby dialog
    # prodolzhilsya sam, bez ruchnogo vybora polzovatelem. Posle klika DOM
    # eshchyo mgnovenie perestraivaetsya (dual-kartochka skladyvaetsya v obychnyy
    # odinarnyy otvet) — na etom cikle schitaem "eshchyo generiruet", chtoby
    # ne popytatsya prochitat otvet do zaversheniya perestroyki DOM.
    n = _safe_execute(driver, JS_DUAL_CHOICE_BUTTON_COUNT, default=0) or 0
    if n >= 2:
        _safe_execute(driver, JS_CLICK_PREFER_FIRST_RESPONSE, default=False)
        return True
    return bool(_safe_execute(driver, JS_IS_GENERATING, default=False))


def _action_raw_from_text(text):
    """v76: vozvrashchaet stroku-kandidata JSON-deystviya TOLKO esli v tekste
    deystvitelno est JSON-obekt s klyuchom "action". Ranshe obychnyy tekst bez
    figurnykh skobok celikom schitalsya kandidatom (_extract_json_object
    vozvrashchaet iskhodnuyu stroku, a _looks_json_balanced schitaet tekst bez
    skobok sbalansirovannym) -> parse_error -> lozhnyy sistemnyy povtor na
    prostoe privetstvie.

    v86.11: Qwen otdayet VESʹ otvet odnim sploshnym tekstom (net otdelnogo
    <pre>/<code>-elementa dlya agent_action) — content_ref/search_ref/
    replace_ref (v86.9) khranyat svoi tela kak ===METKA===...===END_METKA===
    POSLE JSON, v TOM ZHE tekste. _extract_json_object rezhet ot pervoy '{'
    do POSLEDNEY '}' vo VSYOM tekste — dlya deystviy s *_ref eto sluchayno
    otrezalo vse ===METKA=== bloki (v .gd/.tscn kontente net figurnykh
    skobok, poetomu 'poslednyaya }' — eto zakryvayushchaya skobka SAMOGO
    JSON), i _resolve_content_refs() v parser_base.py potom NIKOGDA ikh ne
    nakhodil — vesʹ plan padal s oshibkoy "ne naydeno telo dlya metki",
    khotya model prislala vsyo pravilno. Teper posle proverok JSON-kandidata
    voobshche vozvrashchaem OT nachala JSON DO KONTsA vsego teksta, chtoby
    lyubye ===METKA=== bloki posle JSON ostalisʹ dostupny dlya razbora."""
    if not text:
        return None
    stripped = _strip_code_fences(text)
    try:
        cand = _extract_json_object(stripped)
    except Exception:
        return None
    if not cand:
        return None
    cand = cand.strip()
    if not (cand.startswith("{") and cand.endswith("}")):
        return None
    if u'"action"' not in cand:
        return None
    if not _looks_json_balanced(cand):
        return None
    start = stripped.find("{")
    if start == -1:
        return cand
    return stripped[start:]


def extract_answer(driver):
    # v86.13/v86.14/v86.15: сначала пытаемся собрать ПОЛНЫЙ текст ответа
    # (код-блоки — из модели Monaco или перехватом кнопки Copy, см.
    # parser_base). Если составной сбор не удался — старый путь через innerText.
    text = read_composed_answer(driver, JS_COMPOSED_ANSWER, "[qwen_parser]",
                                copy_click_js=JS_COPY_CLICK)
    if not text.strip():
        text = answer_stream(driver)
    if not text:
        return {"text": "", "actionRaw": None, "error": "пустой ответ (qwen): проверь, что чат открыт и ответ дописан"}
    raw = _action_raw_from_text(text)
    # v86.16: если JSON действия ссылается на метки (content_ref и т.п.), а их
    # тел ===МЕТКА===...===END_МЕТКА=== в тексте ещё нет — ответ, скорее
    # всего, ЕЩЁ ДОПИСЫВАЕТСЯ: JSON плана становится сбалансированным задолго
    # до конца тел файлов.
    # v86.18: ожидание дозаписи больше не ограничено фиксированными ~20 с:
    # пока сайт РЕАЛЬНО генерирует (is_generating), продолжаем ждать и
    # перечитывать (длинный ответ с 6+ файлами пишется минутами — именно
    # так терялись FILE_4..FILE_6). После остановки генерации — ещё до 8
    # контрольных перечитываний. Общий предохранитель — 240 с на вызов,
    # чтобы никогда не зависнуть навечно. Если тела так и не появились —
    # отдаём как есть: дальше сработает терпимый разбор тел (v86.18 в
    # parser_base) и штатное самоисцеление/частичное восстановление.
    tries = 0
    post_gen_tries = 0
    wait_start = time.time()
    while raw and missing_ref_bodies(raw, text):
        try:
            still_generating = bool(is_generating(driver))
        except Exception:
            still_generating = False
        if not still_generating:
            post_gen_tries += 1
            if post_gen_tries > 8:
                break
        if time.time() - wait_start > 240:
            print("[qwen_parser] лимит ожидания дозаписи (240 с) исчерпан — "
                  "отдаю ответ как есть (v86.18).")
            break
        tries += 1
        print("[qwen_parser] в ответе пока нет тел для меток: %s — жду и перечитываю "
              "(попытка %d, генерация идёт=%s, v86.18)…"
              % (", ".join(missing_ref_bodies(raw, text)), tries,
                 "да" if still_generating else "нет"))
        time.sleep(2.5)
        new_text = read_composed_answer(driver, JS_COMPOSED_ANSWER, "[qwen_parser]",
                                        copy_click_js=JS_COPY_CLICK)
        if new_text.strip():
            text = new_text
            raw = _action_raw_from_text(text)
    return {"text": text, "actionRaw": raw, "error": None}


class QwenParser(BaseSiteParser):
    """Qwen: сайт-специфичная часть поверх BaseSiteParser (v73, боевые селекторы)."""

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
