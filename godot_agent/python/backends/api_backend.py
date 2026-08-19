# -*- coding: utf-8 -*-
"""Бэкенд работы по ключу API — сиблинг браузерного, не наследник.

ЧТО ЗДЕСЬ ЕСТЬ И ЧЕГО НЕТ. Есть: сборка messages, вызов транспорта, живая
трансляция в панель, разбор блока agent_action, запись истории. Нет ничего
браузерного: ни вставки текста, ни ожидания тишины DOM, ни маркера ===DONE===
как способа понять конец ответа — по API конец известен точно (finish_reason).

ТЕКСТОВЫЙ ПРОТОКОЛ ДЕЙСТВИЙ СОХРАНЁН. Основной формат — блок
```agent_action, а не нативный function calling. Ответы небольших моделей в
известных XML-обёртках tool call приводятся к той же внутренней схеме, после
чего без отдельной ветки работают parse_action_json, ref-блоки,
самоисцеление, корпус реальных сбоев и весь набор проверок действий.

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
import xml.etree.ElementTree as ET

import api_history
import api_keys
import anthropic_compat
import catalog
import md_to_bbcode
import openai_compat as oc
import parser_base
import providers
from agent_prompts import API_CONTEXT_WINDOW, API_MAX_TOKENS

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
_LEGACY_TOOL_RE = re.compile(
    r"<(dots_function_call|function_call|tool_call)\b[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE)
_LEGACY_TOOL_OPEN_RE = re.compile(
    r"<(dots_function_call|function_call|tool_call)\b[^>]*>", re.IGNORECASE)

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
    # Некоторые небольшие модели используют XML-инструкции вместо нашего
    # текстового протокола. Извлекаем только известные обёртки, чтобы обычный
    # XML из ответа модели не превращался случайно в действие.
    legacy = list(_LEGACY_TOOL_RE.finditer(src))
    if legacy:
        m = legacy[-1]
        return m.group(0), (src[:m.start()] + src[m.end():])
    # Оборванный XML-вызов, как и незакрытый agent_action, должен попасть в
    # самоисцеление, а не отображаться пользователю как якобы готовый ответ.
    opened = list(_LEGACY_TOOL_OPEN_RE.finditer(src))
    if opened:
        m = opened[-1]
        return src[m.start():], src[:m.start()]
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
        if _LEGACY_TOOL_OPEN_RE.match(action_raw.strip()):
            action, err = _parse_legacy_tool_call(action_raw)
            if action is not None:
                print("[api_backend] XML tool call приведён к agent_action")
                return action, prose
            print("[api_backend] XML tool call не разобран: %s" % err)
            return {"action": "parse_error", "raw": action_raw,
                    "error": err}, prose
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


def _parse_legacy_tool_call(raw):
    """Переводит распространённый XML function-call в нашу схему действий.

    Поддерживаем только явные обёртки, уже отобранные _LEGACY_TOOL_RE, и
    arguments-объект. Поля server_name и лишние XML-узлы игнорируются: право
    выполнять действие всё равно остаётся у обычной валидации main.py.
    """
    try:
        root = ET.fromstring(raw.strip())
    except (ET.ParseError, TypeError, ValueError) as exc:
        return None, "XML tool call повреждён: %s" % exc
    action_node = root.find(".//action")
    node = action_node if action_node is not None else root
    tool_name = (node.findtext("tool_name") or node.findtext("name") or "").strip()
    args_text = node.findtext("arguments") or "{}"
    args, err = parser_base.parse_action_json(args_text.strip())
    if not isinstance(args, dict):
        return None, ("в XML arguments ожидался JSON-объект: %s"
                      % (err or "неизвестная ошибка"))
    if not tool_name:
        return None, "в XML tool call отсутствует tool_name"
    args["action"] = tool_name
    args, fixes = parser_base.coerce_action_schema(args)
    if fixes:
        print("[api_backend] XML tool call нормализован: %s" % "; ".join(fixes))
    return args, None


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


# ---------------------------------------------------------------------------
# Бюджеты токенов под КОНКРЕТНУЮ модель
#
# ОТКУДА ЗАДАЧА. Зашитые в agent_prompts числа (окно 32000, история 16000,
# вывод 8000) — это ДОГАДКА «у бесплатных моделей окно обычно 32k», и так и
# написано в комментарии рядом с ними. Каталог models.dev знает настоящие
# лимиты, и замер (19.08.2026, 502 модели наших пяти провайдеров) показал, что
# догадка неверна в ОБЕ стороны:
#
#   * у 27 моделей окно МЕНЬШЕ, чем история+вывод (24000): microsoft/phi-4 —
#     16384, deepseek/deepseek-r1-distill-llama-70b — 8192, google/gemma-2-27b-it
#     — 8192, openai/gpt-3.5-turbo-16k — 16385. Это обычные чат-модели, которые
#     пользователь вполне может выбрать, и с зашитыми числами запрос к ним
#     ГАРАНТИРОВАННО не влезал в окно — отказ провайдера посреди задачи;
#   * у 28 моделей предел ВЫВОДА меньше 8000 (до 2048): строгий провайдер
#     отвечает на такой max_tokens 400, снисходительный молча обрезает;
#   * у 472 моделей окно БОЛЬШЕ 32000 (медиана 262144 у OpenRouter, 400000 у
#     Opencode Zen) — то есть история схлопывалась в разы раньше, чем нужно.
#
# ПОЧЕМУ НЕ БЕРЁМ ОКНО ЦЕЛИКОМ. История уходит провайдеру в КАЖДОМ запросе.
# Отдать под неё половину миллионного окна значит 500k входных токенов на шаг
# агента; на модели за $15/млн это больше семи долларов за шаг, о которых никто
# не просил. Поэтому доли остаются те же, что у подобранных вручную чисел
# (история — половина окна, вывод — четверть), а рост истории ограничен
# HISTORY_CAP.
#
# ГЛАВНОЕ СВОЙСТВО: без данных каталога числа получаются РОВНО прежние
# (32000 -> 16000 и 8000). Это проверяется тестом — Этап 2 не должен менять
# поведение там, где о модели ничего не известно.
# ---------------------------------------------------------------------------

# Доли окна. Взяты из соотношения зашитых чисел: 16000/32000 и 8000/32000.
HISTORY_SHARE = 0.5
OUTPUT_SHARE = 0.25

# Потолок бюджета истории. ЗАМЕРЕНО, а не выбрано на глаз: системный блок даёт
# ~3851 токен на одном шаблоне мега-промпта (11552 символа), а один самый
# большой возможный результат инструмента — 80000 символов (TOTAL_CHAR_BUDGET),
# то есть ~26667 токенов. Вместе 30518. С кэпом 32000 одно полное чтение файла
# перестаёт вытеснять ВСЮ историю — ровно та жалоба, из-за которой числа и
# пересматриваются. Больше — это уже плата за то, чего задача не требует.
HISTORY_CAP = 32000

# Потолок длины одного ответа. Не поднимаем выше зашитых 8000 намеренно: там
# посчитано, что 8000 токенов — это 500–700 строк GDScript, то есть план на
# десяток шагов и крупный файл влезают за один ответ. Для более длинного уже
# есть многочастная передача (continues: true), а больший max_tokens на платной
# модели — просто дороже.
OUTPUT_CAP = API_MAX_TOKENS

# Минимальный осмысленный ответ: короткая фраза плюс блок ```agent_action с
# одним действием — это порядка 100–200 токенов. 512 берём с запасом.
MIN_ANSWER_TOKENS = 512


def budgets_for(provider_id, model, max_tokens=None, budget_tokens=None):
    u"""Бюджеты для конкретной модели: (max_tokens, budget_tokens, окно, откуда).

    «откуда» — "catalog", если окно взято из справочника models.dev, и ""
    (догадка), если каталог про эту модель молчит. Строка нужна вывод сервера:
    число без источника в этом проекте не показывается.

    max_tokens/budget_tokens — то, что передаёт main.py из agent_prompts. Они
    же становятся результатом, когда каталог молчит.

    ВНИМАНИЕ НА АСИММЕТРИЮ. max_tokens от вызывающей стороны — это ПОТОЛОК:
    просить у модели больше, чем попросили здесь, мы не имеем права. А
    budget_tokens — это ДОГАДКА, которую каталог и должен заменить: ограничить
    историю переданным значением значит оставить всё как было и лишить весь
    Этап 2 смысла.
    """
    fallback_out = int(max_tokens or API_MAX_TOKENS)
    fallback_hist = int(budget_tokens or api_history.DEFAULT_CONTEXT_BUDGET)
    info = {}
    try:
        info = catalog.model_info(provider_id, model)
    except Exception as e:
        # Каталог — удобство. Сломался — работаем на прежних догадках, а не
        # роняем чат.
        print("[api_backend] Каталог недоступен, беру зашитые бюджеты (%s)" % e)
    try:
        window = int(info.get("context") or 0)
    except Exception:
        window = 0
    try:
        model_out = int(info.get("max_output") or 0)
    except Exception:
        model_out = 0
    if window <= 0:
        # Про эту модель каталог ничего не знает (у OpenRouter это 62 записи из
        # 415 — варианты с суффиксами вроде «:batch»). Догадку НЕ уточняем
        # ничем: подставить сюда лимиты базовой модели значит выдать чужие числа
        # за факты об этой.
        return fallback_out, fallback_hist, API_CONTEXT_WINDOW, ""
    out = min(fallback_out, OUTPUT_CAP, int(window * OUTPUT_SHARE))
    if model_out > 0:
        # Предел вывода самой модели — жёсткий: больше него провайдер либо
        # откажет, либо обрежет ответ на середине блока действия.
        out = min(out, model_out)
    hist = min(HISTORY_CAP, int(window * HISTORY_SHARE))
    # Ни один из бюджетов не имеет смысла нулевым: у моделей с окном 480
    # (veo-3.1-*) и 512 (llama-prompt-guard) агент не заработает в любом случае,
    # но отдавать транспорту max_tokens=0 нельзя — это «без ограничения».
    return max(1, out), max(1, hist), window, "catalog"


# Что уже напечатано про бюджеты, по чату. Печатать на КАЖДЫЙ запрос нельзя:
# main.py создаёт новый ApiBackend на каждое обращение (_current_backend), и в
# журнале агента эта строка встала бы между каждым шагом. Печатаем только при
# изменении — то есть при первом запросе чата и после обновления каталога.
_budget_notes = {}


def _note_budgets(chat_id, model, out, hist, window, src):
    key = str(chat_id or "")
    value = (model, out, hist, window, src)
    if _budget_notes.get(key) == value:
        return
    if len(_budget_notes) > 64:
        # Страховка от роста: чатов за сессию может быть много, а память под
        # служебную памятку расти не должна.
        _budget_notes.clear()
    _budget_notes[key] = value
    print(u"--> Бюджеты токенов для %s: окно %d (%s), история %d, ответ %d"
          % (model or "?", window,
             u"по каталогу models.dev" if src == "catalog" else u"оценка по умолчанию",
             hist, out))


def _is_client_rejected(msg):
    """Похоже ли на «пустили бы, но не тебя»: сервис отверг программу-клиента,
    а не ключ. Смотрим по тексту, потому что HTTP-статус тут тот же 401."""
    low = str(msg or "").lower()
    return ("unauthorized client" in low or "unauthorized_client" in low
            or "client not allowed" in low or "client not supported" in low)


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
        # Отдельный случай: сервис отверг не ключ, а САМУ ПРОГРАММУ. Так делает
        # AgentRouter — он пускает только приложения из своего списка и узнаёт
        # их по User-Agent. Совет «проверьте ключ» здесь отправляет искать
        # причину не там: ключ можно перевыпускать сколько угодно, ничего не
        # изменится. Выдавать себя за разрешённую программу мы не будем —
        # блокируют в таком случае аккаунт пользователя.
        if _is_client_rejected(msg):
            return (u"[Клиент не в списке]: «%s» отказал не ключу, а самой "
                    u"программе (%s). Сервис принимает запросы только от "
                    u"приложений из своего списка, и Godot Agent в него пока "
                    u"не входит — мы просим разрешение на добавление. Ключ "
                    u"здесь ни при чём; пока выберите другого провайдера."
                    % (name, msg)), None, None
        return (u"[Ключ API]: «%s» отклонил ключ (%s). Проверьте ключ в "
                u"настройках — возможно, он отозван или скопирован не "
                u"полностью." % (name, msg)), None, None
    if isinstance(e, oc.ForbiddenError):
        # 403 без упоминания ключа — почти всегда посредник, а не сервис.
        # Виноватить ключ тут нельзя: человек пойдёт искать проблему не там.
        return (u"[Доступ запрещён]: «%s» ответил «%s» (HTTP 403). Про ключ "
                u"речи нет, поэтому дело, скорее всего, не в нём. Так отвечают "
                u"посредники: фильтр интернет-провайдера, антивирус с проверкой "
                u"HTTPS, корпоративный шлюз — или сам сервис блокирует регион. "
                u"Нажмите «Проверить подключение»: там показывается, кто выдал "
                u"TLS-сертификат, и по нему видно, отвечает ли настоящий сервис "
                u"или его кто-то подменяет." % (name, msg)), None, None
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
        # Если прокси включён, он сам — первый подозреваемый. Советовать
        # «укажите прокси» в этом случае значит сбивать с толку: именно так и
        # вышло, когда в поле хоста оказался адрес DNS-сервиса вместо прокси.
        pr = api_keys.get_proxy()
        if pr.get("enabled") and pr.get("host"):
            return (u"[Сеть]: не удалось связаться с «%s» через прокси %s:%s "
                    u"(%s). Проверьте адрес прокси: нужен обычный HTTP-прокси "
                    u"(хост и порт), а не адрес DNS-сервиса или страницы. "
                    u"Или выключите прокси и попробуйте напрямую."
                    % (name, pr.get("host"), pr.get("port") or "?", msg)), None, None
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
        # Провайдер мог стать недоступен уже ПОСЛЕ создания чата (например,
        # сервис ограничил список клиентов). Молча уходить в сеть за гарантией
        # отказа незачем — объясняем сразу.
        blocked = providers.unavailable_reason(pid)
        if blocked:
            provider_name = (providers.get_provider(pid) or {}).get("name") or pid
            return self._fail(
                u"[Провайдер недоступен]: «%s» — %s Создайте новый чат с другим "
                u"провайдером: модель закреплена за чатом и здесь её не сменить."
                % (provider_name, blocked))
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
        # Бюджеты считаются ЗДЕСЬ, а не в __init__: каталог мог обновиться уже
        # после создания чата (он обновляется раз в неделю внутри обхода
        # провайдеров), и брать лимиты на момент создания значило бы держать
        # устаревшие числа до конца жизни чата.
        max_tokens, budget, window, src = budgets_for(
            pid, model, self._max_tokens, self._budget_tokens)
        _note_budgets(self.chat_id, model, max_tokens, budget, window, src)
        # ОКНО ФИЗИЧЕСКИ НЕ ВМЕЩАЕТ РАБОТУ. Проверяем ДО запроса и по точному
        # размеру системного блока, а не по прикидке: у части моделей каталога
        # окно 480–8192 токенов (veo-3.1-*, llama-prompt-guard-2-*,
        # gemini-embedding-*), а один только мега-промпт — около 3900. Отправить
        # такой запрос значит заплатить за гарантированный отказ провайдера и
        # показать пользователю невнятную ошибку про длину контекста вместо
        # понятного «эта модель для агента не годится».
        sys_tokens = api_history.estimate_tokens(system_text) if system_text else 0
        if src == "catalog" and window < sys_tokens + MIN_ANSWER_TOKENS:
            return self._fail(
                u"[Модель не подходит]: окно контекста «%s» — %d токенов (по "
                u"каталогу models.dev), а одной инструкции агента нужно около "
                u"%d. Запрос заведомо не влезет. Создайте новый чат на модели с "
                u"окном хотя бы %d токенов: модель закреплена за чатом и здесь "
                u"её не сменить."
                % (model, window, sys_tokens, sys_tokens + MIN_ANSWER_TOKENS))
        messages = api_history.build_request_messages(
            self._base_dir, self.chat_id, system_text, prompt,
            budget_tokens=budget)

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
            transport = anthropic_compat if providers.transport_for(pid, model) == "anthropic" else oc
            res = transport.stream_chat(
                base_url, key, model, messages,
                max_tokens=max_tokens, temperature=self._temperature,
                extra_headers=providers.headers_for(pid),
                proxy=api_keys.proxy_url(),
                connect_timeout=providers.connect_timeout_for(pid),
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
