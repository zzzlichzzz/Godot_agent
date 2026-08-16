# -*- coding: utf-8 -*-
"""Бэкенд работы по ключу API — сиблинг браузерного, не наследник.

ЧТО ЗДЕСЬ ЕСТЬ И ЧЕГО НЕТ. Есть: сборка messages, вызов транспорта, живая
трансляция в панель, разбор блока agent_action, запись истории. Нет ничего
браузерного: ни вставки текста, ни ожидания тишины DOM, ни маркера ===DONE===
как способа понять конец ответа — по API конец известен точно (finish_reason).

ТЕКСТОВЫЙ ПРОТОКОЛ ДЕЙСТВИЙ СОХРАНЁН. Действия по-прежнему приходят блоком
```agent_action, а не через нативный function calling. Это осознанно: так
продолжают работать без единой правки parse_action_json, ref-блоки,
самоисцеление, корпус реальных сбоев и весь набор тестов, а оба режима ведут
себя одинаково — иначе пришлось бы поддерживать две разные логики поведения
модели. Нативные tool calls — отдельная задача, не смешанная с этой.

ПОЧЕМУ ЗДЕСЬ ЛОВЯТСЯ ОШИБКИ, А НЕ ПРОБРАСЫВАЮТСЯ. main.py уже умеет две
вещи: показывать текст ответа пользователю и засыпать при лимите запросов
(_reply -> rate_limit). Поэтому ошибки провайдера переводятся в эти два
понятных сервера языка:
  * лимит и перегрузка -> статус для pop_rate_limit_status(), и существующий
    спящий режим повторяет запрос сам;
  * суточный лимит, неверный ключ, кончившиеся кредиты, отсутствующая
    модель, переполненный контекст -> честный текст в чат, потому что
    повторять такое бессмысленно и 500-я ошибка тут ничего не объясняет.
"""
import re
import time

import api_history
import api_keys
import md_to_bbcode
import openai_compat as oc
import parser_base
import providers

# Заглушка на месте вырезанного блока действия — ровно та же строка, что
# ставит JS-экстрактор в браузерном режиме, чтобы чат выглядел одинаково.
ACTION_PLACEHOLDER = u"\n" + md_to_bbcode.ACTION_PLACEHOLDER + u"\n"

# Как часто обновляем прогресс во время потока. Панель опрашивает /chat/progress
# раз в секунду, поэтому чаще незачем, а пересобирать строку на каждый токен —
# лишняя работа на длинном ответе.
_PROGRESS_EVERY = 0.2

_ACTION_FENCE_RE = re.compile(
    r"```[ \t]*agent_action[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
_ACTION_OPEN_RE = re.compile(r"```[ \t]*agent_action[ \t]*\r?\n", re.IGNORECASE)

# Статус лимита запросов держим на уровне МОДУЛЯ, а не экземпляра: main.py
# спрашивает про лимит уже после того, как обмен закончился, и бэкенд к тому
# моменту может быть создан заново. Тот же приём, что у BaseSiteParser с его
# монитором на уровне класса — один процесс, один активный обмен.
_LAST_RATE_LIMIT = {"status": None, "retry_after": None}


def pop_rate_limit_status():
    st = _LAST_RATE_LIMIT["status"]
    _LAST_RATE_LIMIT["status"] = None
    return st


def pop_retry_after():
    """Сколько секунд просил подождать провайдер (заголовок Retry-After) или
    None. Читается один раз, как и статус."""
    ra = _LAST_RATE_LIMIT["retry_after"]
    _LAST_RATE_LIMIT["retry_after"] = None
    return ra


def _note_rate_limit(status, retry_after=None):
    _LAST_RATE_LIMIT["status"] = status
    _LAST_RATE_LIMIT["retry_after"] = retry_after


# ---------------------------------------------------------------------------
# Разбор ответа модели
# ---------------------------------------------------------------------------

def split_action_block(text):
    """Отделяет блок ```agent_action от обычного текста ответа.

    Возвращает (сырое_содержимое_блока_или_None, текст_без_блока).

    Берётся ПОСЛЕДНИЙ блок — как и в браузерном режиме («last one wins»):
    модель иногда показывает пример формата, прежде чем прислать настоящее
    действие.

    Незакрытый блок обрабатывается отдельно: если модель упёрлась в лимит
    вывода посреди действия, закрывающих ``` не будет. Отдать
    parse_action_json обрезанный JSON правильнее, чем сделать вид, что
    действия не было: самоисцеление увидит поломку и попросит переслать.
    """
    src = text or ""
    matches = list(_ACTION_FENCE_RE.finditer(src))
    if matches:
        m = matches[-1]
        return m.group(1), (src[:m.start()] + src[m.end():])
    m = _ACTION_OPEN_RE.search(src)
    if m:
        return src[m.end():], src[:m.start()]
    return None, src


def strip_done_marker(text):
    """Убирает служебный маркер ===DONE=== из текста для пользователя.

    Делегируется parser_base: маркер — часть протокола, и его определение
    должно быть в одном месте. Своя копия регулярки означала бы, что при
    изменении маркера один из двух режимов тихо перестанет его вырезать.
    Имя приватное, но это осознанный выбор в пользу единственного источника
    истины (в будущем protocol-часть parser_base планируется вынести
    отдельным модулем — см. ОТЛОЖЕНО.md).
    """
    return parser_base._strip_done_marker(text or "")


def parse_action(raw_text):
    """Действие из ответа модели. Возвращает (action_or_None, текст_без_блока).

    Повторяет поведение браузерного пути (parser_base, «план В»), чтобы оба
    режима вели себя одинаково:
      * блок разобрался — отдаём действие;
      * блок есть, но JSON битый — отдаём {"action": "parse_error", ...}.
        Это НЕ ошибка, а сигнал: main.py по нему запускает самоисцеление и
        просит модель переслать действие;
      * блока нет вовсе — сканируем сырой текст на встроенный JSON с ключом
        "action". Мега-промпт это запрещает, но модели периодически пишут
        действие голым текстом, и терять из-за этого задачу незачем.
    """
    action_raw, prose = split_action_block(raw_text)
    if action_raw is not None:
        action, err = parser_base.parse_action_json(action_raw)
        # Словарь БЕЗ ключа "action" — тоже провал разбора. json_repair
        # чинит мусор очень настойчиво и может вернуть, например,
        # {"это": "", "не": "json"}: формально объект, а действия в нём нет.
        # Пропустить такое дальше значит показать пользователю подтверждение
        # действия без типа, которое ничего не выполнит. Честнее считать это
        # поломкой и дать самоисцелению попросить переслать действие.
        if isinstance(action, dict) and not action.get("action"):
            err = err or (u"в разобранном JSON нет обязательного поля "
                          u"\"action\" (получены ключи: %s)"
                          % u", ".join(list(action.keys())[:8]))
            action = None
        if action is None:
            print("[api_backend] JSON действия не разобран: %s" % err)
            print("[api_backend] RAW (%d симв.): %s"
                  % (len(action_raw), action_raw[:2000]))
            action = {"action": "parse_error", "raw": action_raw, "error": err}
        return action, prose
    if '"action"' in (raw_text or ""):
        for cand in parser_base._find_action_json_candidates(raw_text):
            salvaged, _ = parser_base.parse_action_json(cand)
            if salvaged is not None:
                print("[api_backend] страховка: действие найдено в тексте ответа "
                      "вне блока ```agent_action — забираю его.")
                return salvaged, prose
    return None, prose


def _guess_user_kind(prompt):
    """Реплика пользователя это или результат инструмента.

    Опознаётся по префиксу «[Система]», которым main.py помечает ВСЕ свои
    служебные вставки (содержимое файлов, дерево проекта, справка
    Библиотекаря, отчёты об ошибках). Вид нужен обрезке контекста: старое
    чтение файла можно схлопнуть, реплику пользователя — нельзя.
    """
    head = (prompt or "").lstrip()[:16]
    if head.startswith(u"[Система]") or head.startswith("[System]"):
        return api_history.KIND_TOOL_RESULT
    return api_history.KIND_PROMPT


def describe_api_error(e, provider_name, model=u""):
    """Человеческий текст ошибки провайдера + статус для повтора.

    Возвращает (сообщение, статус_для_повтора_или_None, сколько_ждать_или_None).
    Статус нужен, чтобы отдать ошибку существующему спящему режиму в
    main.py._reply: у него уже есть нарастающие паузы и прерывание кнопкой
    «Стоп», второй такой механизм не нужен. Третье значение — заголовок
    Retry-After: провайдер знает про свои лимиты точнее нашего расписания.

    Вынесено из метода бэкенда, потому что этими же текстами отвечает кнопка
    «Проверить подключение» в настройках — иначе восемь формулировок пришлось
    бы держать в двух местах.
    """
    name = provider_name or u"провайдер"
    msg = api_keys.redact(str(e))
    if isinstance(e, oc.RateLimitError):
        if e.daily:
            # Суточный лимит: спать до его сброса бессмысленно — это часы.
            return (u"[Суточный лимит]: у «%s» закончилась суточная квота "
                    u"запросов (%s). Подождите до сброса лимита, выберите "
                    u"другую модель или другого провайдера." % (name, msg)), None, None
        return (u"[Лимит запросов]: «%s» просит подождать (%s)."
                % (name, msg)), (e.status or 429), e.retry_after
    if isinstance(e, oc.ServerError):
        # Перегрузка сервиса — повтор имеет смысл.
        return (u"[Сервис недоступен]: «%s» ответил ошибкой (%s)."
                % (name, msg)), (e.status or 503), e.retry_after
    if isinstance(e, oc.AuthError):
        return (u"[Ключ API]: «%s» отклонил ключ (%s). Проверьте ключ в "
                u"настройках — возможно, он отозван или скопирован не "
                u"полностью." % (name, msg)), None, None
    if isinstance(e, oc.PaymentRequiredError):
        return (u"[Кредиты закончились]: «%s» больше не принимает запросы по "
                u"этому ключу (%s). Выберите бесплатную модель или пополните "
                u"баланс." % (name, msg)), None, None
    if isinstance(e, oc.ModelNotFoundError):
        return (u"[Модель не найдена]: «%s» не знает модель «%s» (%s). "
                u"Идентификаторы моделей меняются — обновите список в "
                u"настройках и выберите заново." % (name, model, msg)), None, None
    if isinstance(e, oc.ContextTooLongError):
        return (u"[Контекст переполнен]: диалог не влезает в окно модели (%s). "
                u"Начните новый чат — так дешевле и надёжнее, чем продолжать "
                u"этот." % msg), None, None
    if isinstance(e, oc.TransportError):
        return (u"[Сеть]: не удалось связаться с «%s» (%s). Если провайдер "
                u"недоступен в вашем регионе — укажите прокси в настройках "
                u"API-ключа." % (name, msg)), None, None
    return (u"[Ошибка API]: «%s» — %s" % (name, msg)), None, None


# Показывать расход токенов под ответом модели. В браузерном режиме такого
# понятия нет — там запросы «бесплатны» и один раз. По API это главный
# ориентир по деньгам и лимитам, поэтому цифра должна быть на виду, а не в
# логе сервера. Строка почти без слов («1234 → 567 tok · Σ 12345»), чтобы не
# зависеть от языка интерфейса: сервер отвечает панели уже готовым текстом и
# про выбранный язык не знает.
SHOW_USAGE_IN_CHAT = True

_USAGE_FMT = (u"\n[color=#888888]· %s \u2192 %s tok · \u03a3 %s"
              u" · %s \u0437\u0430\u043f\u0440.[/color]")


def _fmt_num(n):
    """Число с тонкими пробелами по три разряда: 12345 -> 12 345."""
    try:
        return u"\u2009".join(re.findall(r"\d{1,3}(?=(?:\d{3})*$)",
                                        str(int(n)))) or u"0"
    except Exception:
        return u"?"


def usage_line(usage, totals):
    """Строка расхода токенов под ответом или "" — если считать нечего.

    usage — от провайдера за ЭТОТ запрос, totals — накопленное по чату
    (api_history). Оценок здесь нет: показываем только те числа, что назвал
    сам провайдер, иначе пользователь ориентировался бы на выдумку.
    """
    if not SHOW_USAGE_IN_CHAT or not isinstance(usage, dict):
        return u""
    pin = usage.get("prompt_tokens")
    pout = usage.get("completion_tokens")
    if pin is None and pout is None:
        return u""
    tot = totals or {}
    total_tokens = int(tot.get("prompt_tokens") or 0) + int(tot.get("completion_tokens") or 0)
    return _USAGE_FMT % (_fmt_num(pin or 0), _fmt_num(pout or 0),
                         _fmt_num(total_tokens), _fmt_num(tot.get("requests") or 0))


# ---------------------------------------------------------------------------
# Бэкенд
# ---------------------------------------------------------------------------

class ApiBackend(object):
    """Отправка запроса напрямую провайдеру по ключу."""

    kind = "api"

    def __init__(self, chat_rec, base_dir, system_text_provider=None,
                 max_tokens=None, temperature=None,
                 budget_tokens=api_history.DEFAULT_CONTEXT_BUDGET,
                 silence_timeout=oc.DEFAULT_SILENCE_TIMEOUT):
        self._rec = chat_rec or {}
        self._base_dir = base_dir
        # Системный блок собирает main.py: он знает про дерево проекта,
        # архитектуру и версию движка. Бэкенд его только запрашивает —
        # иначе получилась бы кольцевая зависимость с main.py.
        self._system_text_provider = system_text_provider
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._budget_tokens = budget_tokens
        self._silence_timeout = silence_timeout

    # -- параметры чата (закреплены за ним при создании) --

    @property
    def provider_id(self):
        return str(self._rec.get("provider") or "")

    @property
    def model(self):
        """Модель ЭТОГО чата. Закреплена при создании и не меняется, когда
        пользователь переключает модель в настройках: смена модели посреди
        диалога меняет и стиль, и точность соблюдения формата действий, а
        разбираться потом в такой истории невозможно."""
        return str(self._rec.get("model") or "")

    @property
    def chat_id(self):
        return str(self._rec.get("id") or "")

    def describe(self):
        return "%s / %s" % (self.provider_id or "?", self.model or "?")

    def pop_rate_limit_status(self):
        return pop_rate_limit_status()

    def pop_retry_after(self):
        return pop_retry_after()

    # -- основной вызов --

    def send(self, prompt, progress_cb=None, cancel_cb=None, prefer_url=None):
        """prefer_url не используется: у чата по ключу нет страницы в браузере."""
        pid, model = self.provider_id, self.model
        base_url = providers.base_url_for(pid)
        if not base_url or not model:
            return self._fail(
                u"[Настройки API]: у этого чата не задан %s. Откройте настройки "
                u"API-ключа и выберите провайдера и модель."
                % (u"адрес провайдера" if not base_url else u"модель"))
        key = api_keys.resolve_key(pid, providers.env_names_for(pid))
        provider = providers.get_provider(pid) or {}
        if provider.get("needs_key") and not key:
            return self._fail(
                u"[Настройки API]: для «%s» не задан ключ. Введите его в "
                u"настройках API-ключа." % (provider.get("name") or pid))

        system_text = ""
        if self._system_text_provider is not None:
            try:
                system_text = self._system_text_provider() or ""
            except Exception as e:
                print("[api_backend] Не удалось собрать системный блок: %s" % e)
        messages = api_history.build_request_messages(
            self._base_dir, self.chat_id, system_text, prompt,
            budget_tokens=self._budget_tokens)

        started = time.time()
        chunks = []
        chars = [0]
        last_push = [0.0]
        phase = u"%s отвечает" % (model.split("/")[-1] or model)

        def push(force=False):
            if progress_cb is None:
                return
            now = time.time()
            if not force and now - last_push[0] < _PROGRESS_EVERY:
                return
            last_push[0] = now
            progress_cb({"phase": phase, "chars": chars[0],
                         "elapsed": int(now - started),
                         "stream": "".join(chunks)})

        def on_delta(piece, is_reasoning):
            # Размышления «думающих» моделей в чат не льём: пользователю нужен
            # ответ, а не поток сознания, и в текст действия они попасть не
            # должны. Их наличие видно по фазе.
            if is_reasoning:
                return
            chunks.append(piece)
            chars[0] += len(piece)
            push()

        if progress_cb is not None:
            progress_cb({"phase": u"запрос к %s" % (provider.get("name") or pid),
                         "chars": 0, "elapsed": 0, "stream": ""})
        try:
            res = oc.stream_chat(
                base_url, key, model, messages,
                max_tokens=self._max_tokens, temperature=self._temperature,
                extra_headers=providers.headers_for(pid),
                proxy=api_keys.proxy_url(),
                silence_timeout=self._silence_timeout,
                cancel_cb=cancel_cb, on_delta=on_delta)
        except oc.Cancelled:
            # Переводим в исключение, которое main.py уже умеет обрабатывать.
            raise parser_base.ParserCancelled(u"Остановлено пользователем.")
        except oc.ApiError as e:
            return self._handle_api_error(e, provider)
        finally:
            push(force=True)

        raw = res.get("text") or ""
        usage = res.get("usage")
        finish = res.get("finish_reason")
        print("<-- API %s: %d симв., finish=%s, событий=%d, %.1f с"
              % (self.describe(), len(raw), finish, res.get("events") or 0,
                 res.get("elapsed") or 0.0))
        if usage:
            print("    токены: запрос %s, ответ %s"
                  % (usage.get("prompt_tokens"), usage.get("completion_tokens")))

        if not raw.strip():
            return self._fail(
                u"[Пустой ответ]: модель «%s» не вернула текста. Попробуйте "
                u"повторить запрос или выбрать другую модель." % model,
                usage=usage)

        # История пишется ТОЛЬКО после успешного ответа и целой парой: если бы
        # мы сохранили запрос при ошибке, память диалога разошлась бы с тем,
        # что модель на самом деле видела.
        api_history.append_exchange(
            self._base_dir, self.chat_id, prompt, raw,
            user_kind=_guess_user_kind(prompt), usage=usage)

        action_raw, prose = split_action_block(raw)
        action, _ = parse_action(raw)
        # Порядок важен: сначала конвертация Markdown -> BBCode, и только потом
        # добавление служебных вставок. Они уже написаны на BBCode, и конвертер
        # экранировал бы их квадратные скобки, превратив теги в текст.
        display = md_to_bbcode.to_bbcode(strip_done_marker(prose))
        if action_raw is not None:
            display = display.rstrip() + ACTION_PLACEHOLDER
        if finish == "length":
            # По API это точный факт, а не догадка: модель упёрлась в лимит
            # вывода. В браузерном режиме это приходилось угадывать по
            # поломанному JSON.
            display += (u"\n[color=#c08040]— ответ обрезан лимитом вывода "
                        u"модели —[/color]\n")
        display += usage_line(usage, api_history.stats(
            self._base_dir, self.chat_id).get("usage_total"))
        return {"text": display, "action": action, "raw": raw,
                "usage": usage, "finish_reason": finish,
                "model": res.get("model") or model}

    # -- ошибки --

    def _fail(self, message, usage=None):
        """Честный текст в чат вместо исключения: пользователю нужно понятное
        объяснение, а не 500-я ошибка сервера."""
        print("<-- API %s: %s" % (self.describe(), message))
        return {"text": message, "action": None, "raw": "", "usage": usage,
                "finish_reason": "error", "model": self.model}

    def _handle_api_error(self, e, provider):
        msg, retry_status, retry_after = describe_api_error(
            e, provider.get("name") or self.provider_id, self.model)
        if retry_status:
            _note_rate_limit(retry_status, retry_after)
        return self._fail(msg)
