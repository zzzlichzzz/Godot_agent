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
            out.append('\\"')
            i += 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


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
        # Починка несогласованного экранирования кавычек внутри строковых
        # значений (см. _repair_unescaped_inner_quotes) — пробуем ПЕРЕД
        # откатом на внешний json_repair, отдельно и в комбинации с уже
        # накопленными починками.
        candidates.append(_repair_unescaped_inner_quotes(cand))
        candidates.append(_remove_trailing_commas(_repair_unescaped_inner_quotes(cand)))
        candidates.append(_repair_unescaped_inner_quotes(_escape_raw_newlines_in_strings(cand)))
        candidates.append(_remove_trailing_commas(_repair_unescaped_inner_quotes(_escape_raw_newlines_in_strings(cand))))
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
        # v56: снимок «живого» текста ПОСЛЕДНЕГО блока до отправки — пока модель
        # «думает» (генерация уже идёт, но новый блок ответа в DOM ещё не появился),
        # answer_len/answer_preview/answer_stream у некоторых сайтов (DeepSeek) читают
        # ПОСЛЕДНИЙ существующий блок — это ещё СТАРЫЙ ответ. Не транслируем его в панель
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
        revealed = False  # v56: True, когда на странице виден ДЕЙСТВИТЕЛЬНО новый текст
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
                # v56: пока не увидели рост счётчика реплик или текст, отличный от
                # того, что было ДО отправки — это ещё СТАРЛЙ ответ (модель «думает»,
                # генерация уже идёт, но новый блок в DOM не появился). Сравниваем С СВЕЖИй
                # текстом (а не с закешированным 1 раз/сек preview_txt/stream_txt ниже), иначе
                # сам момент перехода мог бы на мгновение показать в ленте ещё старый кеш.
                if not revealed:
                    try:
                        _live_now = self.answer_stream(driver) or ""
                    except Exception:
                        _live_now = stream_txt
                    revealed = (self.count_answers(driver) > initial_count
                                or _live_now != _baseline_stream_txt)
                    if revealed:
                        stream_txt = _live_now
                        preview_txt = self.answer_preview(driver)
                        last_preview_ts = now
                if revealed and now - last_preview_ts >= 1.0:
                    preview_txt = self.answer_preview(driver)
                    stream_txt = self.answer_stream(driver)
                    last_preview_ts = now
                if revealed:
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

        # v56: если настоящий новый ответ так и Не появился в DOM к моменту
        # выхода из цикла стабилизации (например, долгое «думанье» дотянулось
        # до hard_quiet_period на старом тексте), preview_txt/stream_txt всё ещё содержат
        # СтАРый ответ — обнуляем их, чтобы он НЕ утек в грейс-период.
        if not revealed:
            preview_txt = ""
            stream_txt = ""

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

        # 5) v51: АНТИ-ДУБЛЬ старого ответа. Если «стабилизировавшийся» результат
        # побайтово совпадает с последним ответом модели, снятым ДО отправки
        # сообщения, и НОВЫХ реплик модели на странице не появилось — значит,
        # прочитан СТАРЫЙ ответ (счётчик реплик «мигнул» при перестройке DOM,
        # или модель долго думает, не создав новый блок). Такой результат
        # возвращать нельзя — ждём настоящий новый ответ до общего таймаута.
        def _sig_of(r):
            return (((r or {}).get("text") or "") + "\x00" + ((r or {}).get("actionRaw") or ""))

        def _is_stale(r):
            s = _sig_of(r)
            if not s.replace("\x00", "").strip():
                return False
            # v53: счётчик реплик может УМЕНЬШАТЬСЯ (сайт сворачивает/перестраивает
            # DOM; у DeepSeek наблюдали answers=2 (было 3)) — поэтому «новых реплик
            # нет» проверяем как «счётчик НЕ ВЫРОС», а не «равен исходному».
            if self.count_answers(driver) > initial_count:
                return False
            # После перестройки DOM последним блоком может оказаться и более СТАРЫЙ
            # ответ, не совпадающий со снимком до отправки, — ловим его по памяти
            # ранее возвращённых ответов (_returned_sigs).
            return s == _baseline_sig or s in getattr(self, "_returned_sigs", ())

        _stale_logged = False
        while _is_stale(result):
            if time.time() - start >= timeout:
                raise TimeoutError("Модель не дала НОВЫЙ ответ: на странице только сообщение, "
                                   "которое было там ещё до отправки (дубль не возвращаю).")
            if not _stale_logged:
                self._log("анти-дубль: прочитан ТОТ ЖЕ ответ, что был до отправки, "
                          "новых реплик модели нет — жду настоящий новый ответ.")
                _stale_logged = True
            _report("модель ещё думает…")
            got = _try_salvage()
            if got is not None:
                return got
            time.sleep(max(poll_interval, 0.25))
            cur = self.extract_answer(driver) or {}
            if _sig_of(cur) == _sig_of(result):
                continue
            # Текст начал меняться — пошёл настоящий ответ, ждём стабилизации заново.
            stable_since = None
            last_len = -1
            while time.time() - start < timeout:
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
                if driver.execute_script("return arguments[0].value;", el):
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
