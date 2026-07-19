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
import re
import time

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


def parse_action_json(raw: str):
    """Пытается распарсить JSON блока agent_action.
    Возвращает (dict_or_None, error_message_or_None)."""
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
    try:
        from json_repair import repair_json
        fixed = repair_json(_extract_json_object(base))
        return json.loads(fixed), None
    except Exception as e:
        last_error = f"{last_error}; json_repair: {e}"
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
        """Де����твия между вставкой и отправкой (опционально)."""
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

    def switch_to_site_window(self, driver):
        """Переключается на вкладку своего сайта, если она открыта."""
        if not self.WINDOW_URL_MATCH:
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
        JSON действия; всё через методы наследника."""
        timeout = self.TIMEOUT if timeout is None else timeout
        quiet_period = self.QUIET_PERIOD if quiet_period is None else quiet_period
        hard_quiet_period = self.HARD_QUIET_PERIOD if hard_quiet_period is None else hard_quiet_period
        poll_interval = self.POLL_INTERVAL if poll_interval is None else poll_interval
        post_quiet_grace = self.POST_QUIET_GRACE if post_quiet_grace is None else post_quiet_grace
        start = time.time()

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

        # СТОРОЖЕВОЙ ТАЙМЕР: даже если счётчик ответов или длина «сломались»
        # (у «думающих» моделей другая разметка ответа, сайт обновил DOM
        # и т.п.), раз в ~20 с читаем ответ целиком через extract_answer;
        # если он ОТЛИЧАЕТСЯ от снятого до отправки, дописан (JSON действия
        # сбалансирован), генерация не идёт и текст не меняется два замера
        # подряд — возвращаем его как результат, не дожидаясь зависшего
        # основного ожидания. Это лечит «ответ на сайте есть, а агент
        # пишет „модель думает…“ бесконечно».
        _base = self.extract_answer(driver) or {}
        _baseline_sig = (_base.get("text") or "") + "\x00" + (_base.get("actionRaw") or "")
        _salv = {"ts": time.time(), "sig": None}
        _diag = {"ts": time.time()}

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
            if sig == _baseline_sig or self.is_generating(driver):
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
            # зависнет, по этим строкам будет видно, что именно сломалось.
            if time.time() - _diag["ts"] < 30.0:
                return
            _diag["ts"] = time.time()
            try:
                self._log("жду ответ [%s]: answers=%s (было %s), len=%s, generating=%s"
                          % (stage, self.count_answers(driver), initial_count,
                             self.answer_len(driver), self.is_generating(driver)))
            except Exception:
                pass

        # 1) ждём появления нового ответа/реплики модели.
        # важно: сравниваем с initial_count на Неравенство (а не только на рост),
        # потому что сайт иногда перестраивает DOM так, что старый блок удаляется
        # раньше, чем появится новый (счётчик временно уменьшается), и строгое "только больше"
        # никогда не срабатывало и ждало сторожевого таймера (~20 с) вместо того, чтобы сразу
        # заметить изменившийся счётчик. Аналогично выходим раньше, если генерация уже идёт —
        # это уже достаточный сигнал, что новый ответ начался, даже если счётчик пока не изменился.
        while time.time() - start < timeout:
            if self.count_answers(driver) != initial_count or self.is_generating(driver):
                break
            got = _try_salvage()
            if got is not None:
                return got
            _maybe_diag("жду начала ответа")
            _report(self.START_PHASE)
            time.sleep(poll_interval)
        else:
            raise TimeoutError("Новый ответ модели не появился.")

        # 2) ждём начала генерации ИЛИ первого текста ответа
        while time.time() - start < timeout:
            if self.answer_len(driver) > 0 or self.is_generating(driver):
                break
            got = _try_salvage()
            if got is not None:
                return got
            _maybe_diag("жду первый текст")
            _report("модель думает…")
            time.sleep(poll_interval)

        # 3) стабилизация текста + живая трансляция прогресса
        preview_txt = ""
        stream_txt = ""
        phase_txt = "пишет ответ…"
        last_preview_ts = 0.0
        last_length = -1
        quiet_since = None
        length_only_quiet_since = None
        while time.time() - start < timeout:
            length = self.answer_len(driver)   # длина ТОЛЬКО ответа, без «мыслей»
            generating = self.is_generating(driver)
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
            if length > 0:
                if now - last_preview_ts >= 1.0:
                    preview_txt = self.answer_preview(driver)
                    stream_txt = self.answer_stream(driver)
                    activity = self.get_live_activity(driver) or {}
                    if activity.get("code"):
                        lang = activity.get("lang") or ""
                        if lang == "agent_action":
                            phase_txt = "готовит действие для проекта…"
                        elif lang:
                            phase_txt = "пишет код (" + lang + ")…"
                        else:
                            phase_txt = "пишет код…"
                    else:
                        phase_txt = "пишет ответ…"
                    last_preview_ts = now
                _report("модель " + phase_txt, chars=length, preview=preview_txt, stream=stream_txt)
            else:
                _report("модель думает…")
            got = _try_salvage()
            if got is not None:
                return got
            _maybe_diag("стабилизация")
            # ВАЖНО: не завершаем, пока в ОТВЕТЕ нет ни одного символа.
            if length > 0:
                if quiet_since is not None and now - quiet_since >= quiet_period:
                    break
                if length_only_quiet_since is not None and now - length_only_quiet_since >= hard_quiet_period:
                    break
            last_length = length
            time.sleep(poll_interval)
        else:
            raise TimeoutError("Генерация не завершилась вовремя.")

        # 4) защита от «ложного завершения»: обрыв JSON / пустой ответ /
        #    генерация ещё идёт.
        grace_start = time.time()
        _report("проверяю, что ответ дописан", chars=max(last_length, 0), preview=preview_txt, stream=stream_txt)
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
            if (not still_generating) and cur_len == last_length and (not action_incomplete) and (not answer_empty):
                break
            limit = empty_grace if (answer_empty or still_generating) else post_quiet_grace
            if time.time() - grace_start >= limit:
                break
            time.sleep(0.4)
            result = self.extract_answer(driver)
            last_length = cur_len
            _report("проверяю, что ответ дописан", chars=max(cur_len, 0), preview=preview_txt, stream=stream_txt)
        return result

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

    def send_message_and_get_response(self, driver, prompt, input_retries=None, progress_cb=None, cancel_cb=None):
        """Общий конвейер «промпт -> ответ» для любого сайта."""
        retries = input_retries or self.INPUT_RETRIES
        self.switch_to_site_window(driver)
        from browser_manager import harden_background_tab
        harden_background_tab(driver)
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
                if driver.execute_script("return arguments[0].value;", el):
                    inserted = True
                    break
            except (JavascriptException, StaleElementReferenceException):
                el = self.find_input(driver)
            time.sleep(0.3)
        if not inserted:
            raise Exception("Не удалось вставить текст в поле ввода (%s)." % self.LOG_TAG)
        self.before_submit(driver, el)
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
        text = (result or {}).get("text") or ""
        raw_action = (result or {}).get("actionRaw")
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
        return {"text": text, "action": action}
