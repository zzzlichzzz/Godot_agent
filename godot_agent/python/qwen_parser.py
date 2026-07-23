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
import threading
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
# v88.7: поиск поля также в ОТКРЫТЫХ shadow-root'ах (новая вёрстка qwen
# может прятать textarea в веб-компоненте — обычный querySelector её НЕ видит).
# Сначала быстрые селекторы по документу, обход shadow DOM — только если не нашли.
JS_FIND_INPUT = (
    "function pick(root){"
    " return root.querySelector('textarea.message-input-textarea')"
    " || root.querySelector('textarea#chat-input')"
    " || root.querySelector('textarea[placeholder]')"
    " || root.querySelector('textarea')"
    " || root.querySelector('[contenteditable=\"true\"]');}"
    "var el = pick(document);"
    "if (el) return el;"
    "var all = document.querySelectorAll('*');"
    "for (var i = 0; i < all.length; i++) {"
    "  var sr = all[i].shadowRoot;"
    "  if (sr) { el = pick(sr); if (el) return el; }"
    "}"
    "return null;")
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
from parser_base import (answer_transfer_incomplete, build_composed_answer_js,
                         build_copy_click_js, missing_ref_bodies,
                         read_answer_stable, read_composed_answer,
                         height_says_incomplete, split_net_text_and_action)

# v88.6: сетевой захват ответа (как у kimi v87.x и AI Studio v88.0) —
# общая база net_monitor + Qwen-специфика SSE-стрима в qwen_net
from cdp_ws import CDPSession, find_page_ws_url
from qwen_net import QwenChatMonitor

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


# v86.27: высота (px) последнего блока ответа — для height_says_incomplete
# из parser_base.
JS_BLOCK_HEIGHT = _BLOCKS_JS + (
    "var b = __qwenBlocks(); if (!b.length) return 0;"
    " var el = b[b.length-1];"
    " var h = 0;"
    " try { h = el.getBoundingClientRect().height || 0; } catch (e) {}"
    " return Math.max(h, el.scrollHeight || 0);")


def block_height(driver):
    val = _safe_execute(driver, JS_BLOCK_HEIGHT, default=0)
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


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


def extract_answer(driver, net_fallback_fn=None, net_finished_fn=None):
    # v86.13/v86.14/v86.15: сначала пытаемся собрать ПОЛНЫЙ текст ответа
    # (код-блоки — из модели Monaco или перехватом кнопки Copy, см.
    # parser_base). Если составной сбор не удался — старый путь через innerText.
    # v86.19: чтение «двойное» (read_answer_stable) — текст принимается,
    # только когда два чтения подряд совпали.
    text = read_answer_stable(driver, JS_COMPOSED_ANSWER, "[qwen_parser]",
                              copy_click_js=JS_COPY_CLICK)
    if not text.strip():
        text = answer_stream(driver)
    if not text:
        return {"text": "", "actionRaw": None, "error": "пустой ответ (qwen): проверь, что чат открыт и ответ дописан"}
    raw = _action_raw_from_text(text)
    # v86.16/v86.18/v86.19: если передача не завершена (нет тел меток или
    # завершающего ===DONE=== при ссылках на метки) — ответ, скорее всего,
    # ЕЩЁ ДОПИСЫВАЕТСЯ. Пока сайт реально генерирует (is_generating) — ждём и
    # перечитываем; после остановки генерации — ещё до 8 контрольных
    # перечитываний. Общий предохранитель — 240 с на вызов. Если тела так и
    # не появились — отдаём как есть: дальше сработает терпимый разбор тел
    # (v86.18) и штатное самоисцеление/частичное восстановление.
    tries = 0
    post_gen_tries = 0
    wait_start = time.time()
    while True:
        missing = answer_transfer_incomplete(raw, text) if raw else []
        # v86.27: даже без action (обычный текстовый ответ) высота блока
        # может подсказать, что реально отрендерено больше строк, чем
        # попало в innerText (виртуализация/обрезание).
        height_short = (not missing) and height_says_incomplete(text, block_height(driver))
        if not missing and not height_short:
            break
        try:
            still_generating = bool(is_generating(driver))
        except Exception:
            still_generating = False
        # v88.6: сетевой фолбэк (как v88.1/v88.2 у AI Studio): если DOM
        # обрезал/не докачал ответ (Monaco-виртуализация), а сеть уже
        # получила его целиком — берём текст из сетевого захвата сразу,
        # не тратя до 8 циклов × 2.5 с на перечитывания.
        # v88.8: DOM-индикатор генерации у qwen отстаёт от сети — если стрим
        # уже FINISHED, фолбэк разрешён даже при «генерация идёт=да», иначе
        # зря крутились циклы «высота блока намекает…» по 2.5 с.
        net_done = False
        if net_finished_fn is not None:
            try:
                net_done = bool(net_finished_fn())
            except Exception:
                net_done = False
        if net_fallback_fn is not None and (not still_generating or net_done):
            try:
                net_text = (net_fallback_fn() or "").strip()
            except Exception:
                net_text = ""
            if len(net_text) > len(text or ""):
                _prose, _action_raw = split_net_text_and_action(net_text)
                net_missing = (answer_transfer_incomplete(_action_raw, net_text)
                               if _action_raw else [])
                if not net_missing:
                    print("[qwen_parser] сетевой фолбэк решил проблему докачки "
                          "(DOM=%d симв. → сеть=%d симв., не хватало: %s, "
                          "действие выделено=%s, v88.6)"
                          % (len(text or ""), len(net_text),
                             ", ".join(missing) if missing else "высота блока",
                             "да" if _action_raw else "нет"))
                    return {"text": _prose, "actionRaw": _action_raw, "error": None}
        if not still_generating:
            post_gen_tries += 1
            if post_gen_tries > 8:
                break
        if time.time() - wait_start > 240:
            print("[qwen_parser] лимит ожидания дозаписи (240 с) исчерпан — "
                  "отдаю ответ как есть (v86.18).")
            break
        tries += 1
        if missing:
            print("[qwen_parser] передача ещё не завершена, не хватает: %s — жду и перечитываю "
                  "(попытка %d, генерация идёт=%s, v86.19)…"
                  % (", ".join(missing), tries,
                     "да" if still_generating else "нет"))
        else:
            print("[qwen_parser] текст устоялся, но высота блока намекает на больше текста, чем "
                  "распознано — жду и перечитываю (попытка %d, генерация идёт=%s, v86.27)…"
                  % (tries, "да" if still_generating else "нет"))
        time.sleep(2.5)
        new_text = read_composed_answer(driver, JS_COMPOSED_ANSWER, "[qwen_parser]",
                                        copy_click_js=JS_COPY_CLICK)
        if new_text.strip():
            text = new_text
            raw = _action_raw_from_text(text)
    return {"text": text, "actionRaw": raw, "error": None}


# v87.9: кнопка «Сгенерировать заново» у ПОСЛЕДНЕГО ответа (появляется, когда
# сервер qwen сбоит: генерация оборвалась или не началась). Ищем по боевому
# классу кнопки; aria-label — запасной вариант (он локализован, поэтому
# перечислены несколько языков). Берём ПОСЛЕДНЮЮ кнопку на странице — она
# относится к последнему ответу. Кнопка может быть скрыта до наведения мыши
# (enable-hover) — если видимой нет, жмём последнюю найденную как есть.
JS_CLICK_REGENERATE = r"""try {
    var byClass = document.querySelectorAll('.qwen-chat-package-comp-new-action-control-container-regenerate');
    var byAria = document.querySelectorAll('[role="button"][aria-label="Сгенерировать заново"], [role="button"][aria-label="Regenerate"], [role="button"][aria-label*="重新"]');
    var list = byClass.length ? byClass : byAria;
    if (!list.length) return false;
    var btn = null;
    for (var i = list.length - 1; i >= 0; i--) {
        var r = list[i].getBoundingClientRect();
        if (r.width > 0 && r.height > 0) { btn = list[i]; break; }
    }
    if (!btn) btn = list[list.length - 1];
    try { btn.scrollIntoView({block: 'center'}); } catch (e2) {}
    btn.click();
    return true;
} catch (e) { return false; }"""


class QwenParser(BaseSiteParser):
    """Qwen: сайт-специфичная часть поверх BaseSiteParser (v73, боевые селекторы)."""

    LOG_TAG = "qwen_parser"
    WINDOW_URL_MATCH = "chat.qwen.ai"
    START_PHASE = "модель думает…"
    QUIET_PERIOD = 4.0
    POLL_INTERVAL = 0.3

    # v88.6: сетевой монитор chat/completions (общая база net_monitor)
    _monitor = None
    _monitor_lock = threading.Lock()
    _monitor_next_retry = 0.0
    _req_count_before_send = None

    def _ensure_monitor(self):
        """Возвращает живой QwenChatMonitor или None (чистый DOM-режим).
        Неудачные попытки подключения кэшируются на 30 секунд, чтобы не
        дёргать DevTools-порт на каждый опрос (как у AI Studio, v88.0)."""
        with QwenParser._monitor_lock:
            mon = QwenParser._monitor
            try:
                if mon is not None and mon._cdp.is_alive():
                    return mon
            except Exception:
                pass
            now = time.time()
            if now < QwenParser._monitor_next_retry:
                return None
            try:
                ws_url = find_page_ws_url(self.WINDOW_URL_MATCH)
                cdp = CDPSession(ws_url)
                # подписки регистрируются в конструкторе ДО Network.enable,
                # чтобы не потерять первые события (как у kimi, v87.1)
                new_mon = QwenChatMonitor(cdp)
                if mon is not None:
                    # переподключение: счётчики не обнуляются
                    new_mon._assistant_message_count = mon.assistant_message_count()
                    new_mon._chat_request_count = mon.chat_request_count()
                cdp.send_command("Network.enable")
                QwenParser._monitor = new_mon
                print("[qwen_parser] сетевой монитор chat/completions подключён")
                return new_mon
            except Exception as e:
                QwenParser._monitor_next_retry = now + 30.0
                print("[qwen_parser] сетевой монитор недоступен (%s) - работаю только по DOM" % e)
                return None

    def count_answers(self, driver):
        return count_answers(driver)

    def _net_live_text(self):
        # v88.9: живой текст из сетевого захвата для трансляции в панель
        # агента. DOM у qwen отстаёт (Monaco-блоки, перехват Copy), поэтому
        # во время генерации текст в агенте мог не показываться, хотя чат
        # его уже стримил. Защита от УСТАРЕВШЕГО текста: после submit()
        # должен уйти НОВЫЙ POST, иначе current_text() — ещё прошлый ответ.
        # Возвращает None, если сетевой текст брать нельзя (тогда — DOM).
        mon = QwenParser._monitor
        if mon is None:
            return None
        try:
            if not mon._cdp.is_alive():
                return None
            before = QwenParser._req_count_before_send
            # v88.10: answer_request_count, а не chat_request_count — иначе в
            # окне «POST уже ушёл, ответ ещё не пришёл» буфер с ПРОШЛЫМ
            # ответом транслировался в панель как живой текст (дубль).
            if before is not None and mon.answer_request_count() <= before:
                return None
            return mon.current_text() or ""
        except Exception:
            return None

    def answer_len(self, driver):
        net = self._net_live_text()
        if net:
            return len(net)
        return answer_len(driver)

    def answer_preview(self, driver):
        net = self._net_live_text()
        if net:
            return net[-160:]
        return answer_preview(driver)

    def answer_stream(self, driver):
        net = self._net_live_text()
        if net:
            return net
        return answer_stream(driver)

    def is_generating(self, driver):
        return is_generating(driver)

    def extract_answer(self, driver):
        # v88.8: сеть — ОСНОВНОЙ источник текста (как у kimi): если стрим
        # уже завершён (status=finished в /api/v2/chat/completions), берём
        # ответ из захвата СРАЗУ, вообще не читая DOM — двойные чтения с
        # тишиной, перехваты кнопки Copy и проверки высоты блока медленные
        # и заставляли qwen отставать от чата. Защита от устаревшего текста:
        # после submit() должен уйти НОВЫЙ POST (счётчик запросов).
        mon = self._ensure_monitor()
        if mon is not None:
            try:
                before = QwenParser._req_count_before_send
                # v88.10: сверяемся с answer_request_count — номером POST, чей
                # ответ РЕАЛЬНО лежит в буфере. chat_request_count растёт уже
                # при отправке запроса, а буфер сбрасывается только с приходом
                # ответа — в этом окне старый текст выглядел «свежим».
                fresh = (before is None) or (mon.answer_request_count() > before)
                if fresh and mon.is_finished():
                    net = (mon.current_text() or "").strip()
                    if net:
                        prose, action_raw = split_net_text_and_action(net)
                        net_missing = (answer_transfer_incomplete(action_raw, net)
                                       if action_raw else [])
                        if not net_missing:
                            print("[qwen_parser] ответ взят напрямую из сетевого "
                                  "захвата — DOM не читаем (%d симв., действие "
                                  "выделено=%s, v88.8)"
                                  % (len(net), "да" if action_raw else "нет"))
                            return {"text": prose, "actionRaw": action_raw,
                                    "error": None}
            except Exception as e:
                print("[qwen_parser] быстрый сетевой путь не сработал (%r) — "
                      "читаю по DOM (v88.8)" % (e,))

        # сеть ещё не закончила или недоступна — старый гибрид: DOM +
        # мгновенный сетевой фолбэк докачки (v88.6)
        def _net_fallback():
            try:
                mon2 = QwenParser._monitor
                return mon2.current_text() if mon2 is not None else ""
            except Exception:
                return ""

        def _net_finished():
            try:
                mon2 = QwenParser._monitor
                return mon2.is_finished() if mon2 is not None else False
            except Exception:
                return False
        return extract_answer(driver, net_fallback_fn=_net_fallback,
                              net_finished_fn=_net_finished)

    def extract_answer_snapshot(self, driver):
        # v88.3: мгновенный снимок для анти-дубля перед отправкой — одно
        # чтение без цикла ожидания дозаписи (см. parser_base.extract_answer_snapshot).
        text = read_composed_answer(driver, JS_COMPOSED_ANSWER, "[qwen_parser]",
                                    copy_click_js=JS_COPY_CLICK)
        if not (text or "").strip():
            text = answer_stream(driver) or ""
        return {"text": text, "actionRaw": _action_raw_from_text(text) if text else None,
                "error": None}

    def extract_raw_fallback(self, driver):
        # v88.6: план В — DOM пуст, но сеть захватила ответ (страховка от
        # смены разметки qwen). Сетевой текст берётся только если после
        # submit() реально ушёл НОВЫЙ POST — защита от устаревшего ответа
        # прошлого обмена (как у kimi/AI Studio).
        mon = QwenParser._monitor
        before = QwenParser._req_count_before_send
        if mon is not None and before is not None and mon.chat_request_count() > before:
            net = (mon.current_text() or "").strip()
            if net:
                text, action_raw = split_net_text_and_action(net)
                print("[qwen_parser] план В: ответ взят из сетевого захвата (%d симв.)" % len(net))
                return {"text": text, "actionRaw": action_raw}
        return None

    def find_input(self, driver):
        return driver.execute_script(JS_FIND_INPUT)

    def insert_input(self, driver, el, prompt):
        driver.execute_script(JS_SET_INPUT, el, prompt)

    def before_submit(self, driver, el):
        time.sleep(0.4)

    def submit(self, driver, el):
        # v88.6: снимок счётчика POST до отправки — страховка от устаревшего
        # сетевого текста в extract_raw_fallback (как у AI Studio/kimi)
        mon = self._ensure_monitor()
        QwenParser._req_count_before_send = (
            mon.chat_request_count() if mon is not None else None)
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

    def try_regenerate(self, driver):
        # v87.9: авто-повтор сбойной генерации кликом по «Сгенерировать заново».
        clicked = bool(_safe_execute(driver, JS_CLICK_REGENERATE, default=False))
        if clicked:
            time.sleep(1.2)  # даём сайту убрать сбойный блок и начать новую генерацию
        return clicked


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
