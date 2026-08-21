# -*- coding: utf-8 -*-
"""Реестр провайдеров API — нейросети, доступные по ключу, а не через браузер.

ПОЧЕМУ ОТДЕЛЬНО ОТ sites.py. У записи браузерного сайта есть new_chat_url,
match-домены и needs_visibility_spoof — для работы по ключу это бессмыслица.
Смешивать два реестра значит засорять проверенный список браузерных сайтов
полями, которые там никогда не понадобятся, и наоборот. Записи чатов
различаются полем kind: отсутствует или "browser" — сайт в браузере,
"api" — провайдер отсюда.

ОСНОВНОЙ ФОРМАТ ЗАПРОСА. Большинство провайдеров ниже говорят на одном
протоколе — POST <base_url>/chat/completions с телом {model, messages, stream}. Это
формат OpenAI, и его поддерживают (иногда через слой совместимости) почти
все: OpenRouter, Groq, Gemini, DeepSeek, Qwen, а также локальные llama-server
и Ollama. Поэтому транспорт в openai_compat.py ОДИН на всех, а провайдер —
это всего лишь base_url + модель + ключ.

ПОЧЕМУ СПИСКИ МОДЕЛЕЙ ПУСТЫЕ. Идентификаторы моделей меняются постоянно:
бесплатные варианты появляются и исчезают, к именам добавляются даты.
Зашитый в код список гарантированно устареет и начнёт врать пользователю.
Поэтому список тянется с самого сервиса (models_path) и кэшируется, а поле
модели в панели остаётся редактируемым — можно вписать любой идентификатор
руками, не дожидаясь обновления плагина.

СЕКРЕТОВ ЗДЕСЬ НЕТ. Этот модуль знает только МЕТАДАННЫЕ: адреса, имена
переменных окружения, заголовки. Сами ключи живут в api_keys.py, и получить
их можно единственной функцией api_keys.resolve_key(). Такое разделение
не даёт секрету случайно просочиться в ответ /api/providers.
"""
import os
import time

import api_keys

# Заголовок с названием приложения. OpenRouter показывает его в статистике
# использования ключа — пользователю полезно видеть, что запросы идут именно
# от плагина, а не от чего-то ещё, зашедшего на его ключ.
APP_TITLE = "Godot Agent"

# ПОЧЕМУ AGENTROUTER ВЫКЛЮЧЕН, А НЕ УДАЛЁН. Сервис принимает запросы только от
# программ из своего белого списка и опознаёт их по User-Agent; Godot Agent в
# том списке пока не значится, поэтому на ЛЮБОЙ запрос приходит 401
# {"type":"unauthorized_client_error", ...} — с полностью рабочим ключом.
# Проверено:
#   claude-cli/1.0.119 (external, cli) -> 200    claude-cli/1.0.0 -> 401
#   opencode/1.0.0                     -> 200    opencode        -> 401
#   cline/3.0.0                        -> 200    GodotAgent/0.6  -> 401
# Заработало бы, если представиться чужим клиентом, но это ровно тот обход
# ограничений, за который AgentRouter публично обещает блокировать аккаунты
# (объявление от 18.10.2025), а FAQ на 401 отвечает «используйте официально
# поддерживаемый клиент». Рисковал бы при этом владелец ключа, то есть
# пользователь плагина, — так что плагин представляется своим настоящим именем
# (USER_AGENT в openai_compat) и к сервису не ходит вовсе.
#
# Запись оставлена в реестре намеренно: она видна в настройках вместе с
# объяснением, а не выглядит как «провайдера просто нет». Список клиентов у
# сервиса открытый и растущий (Claude Code, Codex, Cline, Roo Code, Kilo Code,
# Qwen Code, OpenCode, Cursor, Trae...), так что нормальный путь — попросить
# внести туда Godot Agent: Discord из текста ошибки или agent_router_org@163.com.
# КАК ВКЛЮЧИТЬ, КОГДА РАЗРЕШАТ: убрать поле "unavailable" из записи ниже.
# Больше ничего не требуется — транспорт, модели и таймауты уже готовы.
AGENTROUTER_UNAVAILABLE = (
    u"сервис принимает запросы только от программ из своего списка, и Godot "
    u"Agent в него пока не входит — мы просим разрешение на добавление. "
    u"Ключ тут не поможет: обходить это ограничение чужим именем клиента "
    u"значит подставлять под блокировку ваш аккаунт.")

# НЕОБЯЗАТЕЛЬНЫЕ ПОЛЯ ЗАПИСИ, КОТОРЫЕ ВИДИТ ПАНЕЛЬ
#
# "models_public": True — список моделей (/models) отдаётся БЕЗ ключа. Панель
#   пользуется этим, чтобы посчитать модели у провайдера, который ещё не
#   настроен: именно между такими провайдерами человек и выбирает, а у
#   остальных до ввода ключа честный ответ — «неизвестно». Ставить только
#   после фактической проверки запросом без ключа, а не по документации.
#
# "verified": True — с провайдером был ПОЛНЫЙ живой обмен настоящим ключом:
#   сохранение ключа, список моделей, проверка подключения, ответ в чате.
#   СЕЙЧАС ЭТОГО ПОЛЯ НЕТ НИ У ОДНОГО ПРОВАЙДЕРА, И ЭТО ПРАВДА: весь код
#   закрыт офлайновыми тестами с локальным HTTP-сервером вместо провайдера,
#   живого обмена не было ни с одним сервисом (см. ОТЛОЖЕНО.md, раздел
#   «Работа по ключу API — что осталось до релиза»). Поле заведено заранее
#   именно поэтому: пометка «проверен», выставленная по предположению, — это
#   ровно то обещание, за которое пользователь потом ловит 402 или 401 и
#   считает, что плагин соврал. Ставится руками, по одному, после прогона.
PROVIDERS = [
    {
        "id": "openrouter",
        "name": "OpenRouter",
        # Одна точка входа ко множеству моделей разных вендоров, включая
        # бесплатные (идентификатор оканчивается на ":free"). Для региона
        # с ограничениями это ещё и удобно: достаточно доступа к одному хосту.
        "base_url": "https://openrouter.ai/api/v1",
        "needs_key": True,
        "env_names": ("OPENROUTER_API_KEY",),
        "models_path": "/models",
        "models": [],
        "default_model": "",
        # /models открыт без ключа — панель может показать число бесплатных
        # моделей ещё до того, как пользователь где-то зарегистрируется.
        "models_public": True,
        # ЖИВОЙ /models ОТДАЁТ ЦЕНЫ САМ, И ЕДИНИЦА ИЗМЕРЕНИЯ ПРОВЕРЕНА.
        # OpenRouter присылает pricing.prompt / pricing.completion строкой в
        # долларах ЗА ОДИН ТОКЕН ("0.000005"), а каталог models.dev — за
        # МИЛЛИОН. Флаг стоит не по документации, а по сверке: после умножения
        # на 1e6 из 353 моделей, известных обоим источникам, цена совпала у 350,
        # а окно контекста — у всех 353. Если бы единица была другой, разошлись
        # бы ВСЕ 353 ровно в миллион раз.
        #
        # ЗАЧЕМ ЭТО ФЛАГОМ, А НЕ ВСЕГДА. «OpenAI-совместимый» ничего не говорит
        # про единицу цены: другой сервис может присылать за миллион, за тысячу
        # или вообще в своей валюте, и ошибка тут показывает пользователю цену,
        # завышенную или заниженную в миллион раз. Ставить только после сверки
        # живым запросом — как и models_public.
        "live_pricing": "per_token",
        "extra_headers": {"X-Title": APP_TITLE},
        "note_ru": "Много моделей в одном ключе, есть бесплатные (с «:free» в названии).",
        "note_en": "Many models behind one key, including free ones (\":free\" suffix).",
    },
    {
        "id": "groq",
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "needs_key": True,
        "env_names": ("GROQ_API_KEY",),
        "models_path": "/models",
        "models": [],
        "default_model": "",
        "extra_headers": {},
        "note_ru": "Бесплатный уровень, очень быстрая генерация.",
        "note_en": "Free tier, very fast generation.",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        # Слой совместимости Google с форматом OpenAI. Именно ХОСТ API, а не
        # адрес сайта: gemini.google.com и aistudio.google.com — другие хосты,
        # и доступность через прокси у них может отличаться. Кнопка проверки
        # подключения обязана стучаться сюда, а не на сайт.
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "needs_key": True,
        "env_names": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "models_path": "/models",
        "models": [],
        "default_model": "",
        "extra_headers": {},
        "note_ru": "Те же модели, что в AI Studio. Слой совместимости может не отдавать часть возможностей нативного API.",
        "note_en": "Same models as AI Studio. The compatibility layer may not expose every native API feature.",
    },
    {
        "id": "agentrouter",
        "name": "AgentRouter",
        # AgentRouter использует OpenAI-совместимый маршрут для GPT и
        # Anthropic /messages для Claude — transport_for() выбирает его по
        # идентификатору модели. Ключ один для обеих групп моделей.
        "base_url": "https://agentrouter.org/v1",
        "needs_key": True,
        "env_names": ("AGENTROUTER_API_KEY",),
        "models_path": "/models",
        "models": ["gpt-5.6-sol", "claude-opus-4-8", "claude-opus-5"],
        "default_model": "gpt-5.6-sol",
        "transport": "agentrouter",
        "extra_headers": {},
        # Пока сервис не внесёт Godot Agent в свой список клиентов, запросы к
        # нему не отправляются вообще: см. AGENTROUTER_UNAVAILABLE.
        "unavailable": AGENTROUTER_UNAVAILABLE,
        # ПОЧЕМУ БОЛЬШЕ ОБЫЧНОГО. AgentRouter — посредник, и до первого байта
        # ответа Claude он молчит непредсказуемо долго: замеры одного и того же
        # запроса дали 2.8 / 4.4 / 15.6 / 68.7 секунды. Со стандартными 30 с
        # часть запросов срывалась по таймауту, и пользователю показывалось
        # «не удалось связаться» на полностью рабочем провайдере.
        "connect_timeout": 150.0,
        # ПОЧЕМУ ПРОВЕРКА ПОДКЛЮЧЕНИЯ ПОТОКОМ. На non-stream запрос к Claude
        # шлюз отвечает 504 от своего nginx ровно через 120 с — ответ модели
        # не успевает пройти целиком. Поток же отдаёт первые события сразу.
        "test_with_stream": True,
        "note_ru": "Пока недоступен: сервис пускает только программы из своего списка, и Godot Agent в нём ещё нет — мы просим разрешение на добавление. Когда разрешат, GPT-модели пойдут через OpenAI API, Claude-модели — через Anthropic API, одним ключом.",
        "note_en": "Unavailable for now: the service only accepts clients from its own list, and Godot Agent is not on it yet — we have asked to be added. Once allowed, GPT models will use the OpenAI API and Claude models the Anthropic API, with a single key.",
    },
    {
        "id": "custom",
        "name": "Свой адрес (OpenAI-совместимый)",
        # Адрес задаёт пользователь: api_keys.get_base_url("custom"). Сюда же
        # подключится локальный llama-server, когда до него дойдёт очередь —
        # отдельного кода для локальных моделей не потребуется.
        "base_url": "",
        "needs_key": False,
        "env_names": (),
        "models_path": "/models",
        "models": [],
        "default_model": "",
        "extra_headers": {},
        "note_ru": "Любой сервис или локальный сервер с совместимым /chat/completions. Ключ нужен не всегда.",
        "note_en": "Any service or local server with a compatible /chat/completions. A key is not always required.",
    },
    {
        "id": "opencode_zen",
        "name": "Opencode Zen",
        # ВНИМАНИЕ НА АДРЕС. Правильный хост — opencode.ai с путём /zen/v1, а
        # НЕ api.opencode.ai. Ошибиться здесь особенно дорого: api.opencode.ai
        # отвечает не 404, а 200 с текстом "Not Found", то есть транспорт видит
        # успешный ответ без событий и сообщает «модель не вернула текста».
        # Пользователь при этом меняет ключи и модели, а виноват адрес.
        #
        # У сервиса есть и родные маршруты под каждое семейство моделей
        # (/responses для GPT, /messages для Claude, /models/<id> для Gemini),
        # но /chat/completions принимает ВСЕ идентификаторы из /models —
        # проверено запросом с заведомо неверным ключом: на claude-*, gpt-* и
        # gemini-* приходит AuthError (ключ), а не «модель не поддерживается».
        # Поэтому отдельный транспорт не нужен, работает общий OpenAI-путь.
        "base_url": "https://opencode.ai/zen/v1",
        "needs_key": True,
        # ДВА ИМЕНИ ПЕРЕМЕННОЙ НАМЕРЕННО. Первое — наше, по имени провайдера в
        # этом реестре. Второе берёт сам Opencode: в его каталоге моделей
        # (models.dev, запись провайдера "opencode") у ключа указано имя
        # OPENCODE_API_KEY. Кто уже настраивал Opencode CLI по его документации,
        # имеет в окружении именно эту переменную — и без второго имени плагин
        # сообщал бы «ключ не задан», глядя на заданный ключ.
        "env_names": ("OPENCODE_ZEN_API_KEY", "OPENCODE_API_KEY"),
        "models_path": "/models",
        "models": [],
        "default_model": "",
        # Список моделей приходит и без ключа — это проверено тем же запросом,
        # которым выяснялся правильный адрес (см. комментарий выше).
        "models_public": True,
        "extra_headers": {},
        "note_ru": "Отобранные командой Opencode модели (GPT, Claude, Gemini, Qwen, Kimi, GLM, DeepSeek) по одному ключу, оплата по факту. Список моделей загружается без ключа — нажмите «Обновить».",
        "note_en": "A curated set of models (GPT, Claude, Gemini, Qwen, Kimi, GLM, DeepSeek) behind one key, pay as you go. The model list loads without a key — press \"Refresh\".",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "needs_key": True,
        "env_names": ("DEEPSEEK_API_KEY",),
        "models_path": "/models",
        "models": [],
        "default_model": "deepseek-chat",
        "extra_headers": {},
        # Бесплатного уровня у DeepSeek нет — обещать его нельзя. Что есть:
        # скидка в непиковые часы. Пользователь, пришедший сюда за «бесплатно»,
        # упрётся в 402 и будет думать, что плагин соврал.
        "note_ru": "DeepSeek Chat и Coder напрямую у разработчика. Платный: бесплатного уровня нет, но в непиковые часы дешевле.",
        "note_en": "DeepSeek Chat and Coder straight from the vendor. Paid: no free tier, but off-peak hours are cheaper.",
    },
]


# Провайдер, предлагаемый по умолчанию при первом входе.
DEFAULT_PROVIDER_ID = "openrouter"


# ---------------------------------------------------------------------------
# Провайдеры из каталога models.dev — второй, НЕПРОВЕРЕННЫЙ ряд
#
# ПОЧЕМУ ОНИ ОТДЕЛЬНО ОТ PROVIDERS, А НЕ ДОПИСАНЫ В НЕГО. Семь записей выше
# разобраны руками, и в них лежит знание, которого в каталоге нет: белый список
# клиентов AgentRouter, ловушка api.opencode.ai (отвечает 200 с текстом «Not
# Found»), connect_timeout=150 для посредника, test_with_stream, проверенная
# единица цены у OpenRouter. Про остальные 163 записи каталога не проверено
# НИЧЕГО — ни адрес, ни то, что сервис вообще говорит на нашем протоколе.
#
# Смешать их в одном списке значит стереть разницу между «проверено» и «взято из
# справочника». Поэтому:
#   * каталожные записи собираются ЗДЕСЬ, из кэша catalog.py, и всегда несут
#     from_catalog=True — панель показывает их своей группой с пометкой;
#   * реестр ВЫИГРЫВАЕТ при совпадении идентификаторов: openrouter, deepseek и
#     opencode есть и там, и там, и работать надо по разобранной записи;
#   * им НЕ выставляется models_public — значит их список моделей не спрашивают
#     без ключа и не трогают при автоматическом обходе. Обещать публичный
#     /models по справочнику нельзя: это проверяется запросом, а не документацией;
#   * verified у них False всегда — как и у наших семи, потому что живого
#     прогона настоящим ключом не было ни с одним провайдером.
#
# ПОЧЕМУ 166, А НЕ 192. У 26 записей каталога нет адреса endpoint'а — им нужен
# родной SDK провайдера (google, groq, openai, anthropic, azure,
# amazon-bedrock...). У нас единственный транспорт это HTTP, поэтому такие
# записи в список не попадают: предложить их значило бы обещать выбор, который
# заведомо не заработает. Наши groq и gemini — как раз из этих 26, и адреса для
# них знает только наш реестр.
# ---------------------------------------------------------------------------

# Заглушка описания для каталожной записи. Текст ЧЕСТНЫЙ: он не обещает, что
# сервис заработает, и называет источник сведений.
_CATALOG_NOTE_RU = (u"Запись из каталога models.dev, живьём не проверялась: ни "
                    u"адрес, ни поддержка нашего протокола. По каталогу моделей "
                    u"%d%s. Ключ и адрес можно поправить руками.")
_CATALOG_NOTE_EN = (u"Entry from the models.dev catalog, never tested live — "
                    u"neither the address nor support for our protocol. The "
                    u"catalog lists %d models%s. The key and the address can be "
                    u"edited by hand.")
_CATALOG_FREE_RU = u", из них бесплатных %d"
_CATALOG_FREE_EN = u", %d of them free"
# Несколько имён переменных окружения означает, что сервису одного ключа мало
# (cloudflare-workers-ai хочет ACCOUNT_ID + API_KEY, snowflake-cortex —
# ACCOUNT + PAT, infomaniak — API_KEY + PRODUCT_ID; всего таких 6). Наша форма
# умеет один ключ, и об этом надо сказать, а не делать вид, что всё получится.
_CATALOG_MULTI_RU = u" ВНИМАНИЕ: сервису нужно несколько значений (%s), а форма умеет один ключ."
_CATALOG_MULTI_EN = u" NOTE: this service needs several values (%s) while the form holds a single key."


def _catalog_record(meta):
    u"""Запись реестра из метаданных каталога. Формат тот же, что у PROVIDERS,
    чтобы ниже ни одна функция не различала два вида записей."""
    total = int(meta.get("models_total") or 0)
    free = int(meta.get("models_free") or 0)
    env = tuple(meta.get("env") or ())
    free_ru = (_CATALOG_FREE_RU % free) if free else u""
    free_en = (_CATALOG_FREE_EN % free) if free else u""
    multi_ru = (_CATALOG_MULTI_RU % u", ".join(env)) if meta.get("multi_secret") else u""
    multi_en = (_CATALOG_MULTI_EN % u", ".join(env)) if meta.get("multi_secret") else u""
    return {
        "id": str(meta.get("id") or ""),
        "name": str(meta.get("name") or meta.get("id") or ""),
        "base_url": str(meta.get("api") or ""),
        "needs_key": True,
        "env_names": env,
        "models_path": "/models",
        "models": [],
        "default_model": "",
        # models_public НЕ ставим — см. пояснение выше.
        "extra_headers": {},
        "transport": ("anthropic" if str(meta.get("transport")) == "anthropic"
                      else "openai"),
        # Признак для панели и для всего кода ниже: запись НЕ разобрана человеком.
        "from_catalog": True,
        "doc": str(meta.get("doc") or ""),
        "catalog_models": total,
        "catalog_models_free": free,
        "note_ru": (_CATALOG_NOTE_RU % (total, free_ru)) + multi_ru,
        "note_en": (_CATALOG_NOTE_EN % (total, free_en)) + multi_en,
    }


def catalog_records():
    u"""Каталожные записи, которые сейчас показываются: {id: запись}.

    Показываются все пригодные, если полный список включён; иначе только те, у
    которых уже есть настройки, — выбранный провайдер обязан остаться видимым,
    даже если список потом выключили, иначе свой же ключ негде убрать.

    Идентификаторы, занятые реестром или соответствием PROVIDER_MAP, сюда не
    попадают: openrouter, deepseek и opencode есть в каталоге, но работать с
    ними надо по разобранной записи.

    ПОЧЕМУ ЗДЕСЬ КЭШ. Функция вызывается из get_provider(), а тот — из каждой
    проверки готовности, каждого адреса и каждой модели. На семи записях это
    было незаметно, а на ста семидесяти превращается в пятьсот чтений двух
    файлов с диска за один запрос настроек (замерено до кэша: список провайдеров
    собирался секундами). Ключ кэша — время и размер ОБОИХ файлов: и кэша
    каталога, и настроек. Значит любое сохранение ключа, включение полного
    списка или обновление каталога сбрасывают его сами, без явного вызова.
    """
    import catalog

    key = (_stat_key(catalog.catalog_path()), _stat_key(api_keys.config_path()))
    if _records_cache["key"] == key:
        return _records_cache["value"]
    try:
        known = catalog.known_providers()
    except Exception as e:
        print("[providers] Реестр каталога недоступен (%s)" % e)
        known = {}
    out = {}
    if known:
        taken = {p["id"] for p in PROVIDERS} | set(catalog.PROVIDER_MAP.values())
        show_all = api_keys.catalog_enabled()
        configured = set() if show_all else set(api_keys.configured_provider_ids())
        for pid, meta in known.items():
            if pid in taken:
                continue
            if not show_all and pid not in configured:
                continue
            rec = _catalog_record(meta)
            if rec["id"] and rec["base_url"]:
                out[rec["id"]] = rec
    _records_cache["key"] = key
    _records_cache["value"] = out
    return out


def _stat_key(path):
    """(время изменения, размер) файла или None. Через это кэш каталожных
    записей узнаёт, что файл переписали, не читая его целиком."""
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except Exception:
        return None


# Записи каталога, собранные в прошлый раз. Общий на процесс: сервер поднят с
# threaded=True, но здесь только чтение и подстановка целиком, поэтому гонка
# приводит максимум к повторной сборке, а не к порче данных.
_records_cache = {"key": False, "value": {}}


def is_from_catalog(provider_id):
    """Взята ли запись провайдера из каталога, а не разобрана человеком."""
    return bool((get_provider(provider_id) or {}).get("from_catalog"))


# ---------------------------------------------------------------------------
# Доступ к реестру
# ---------------------------------------------------------------------------

def get_provider(provider_id):
    pid = str(provider_id or "")
    for p in PROVIDERS:
        if p["id"] == pid:
            return p
    # Реестр выигрывает: до каталога доходим только если своей записи нет.
    return catalog_records().get(pid)


def provider_ids():
    return [p["id"] for p in PROVIDERS] + sorted(catalog_records())


def all_records():
    u"""Все записи, которые видит панель: сначала разобранные, потом каталожные.

    Порядок важен: разобранные идут первыми, чтобы список открывался тем, что
    проверено, а не алфавитом из ста семидесяти незнакомых названий.
    """
    extras = catalog_records()
    return list(PROVIDERS) + [extras[pid] for pid in sorted(extras)]


def env_map():
    """provider_id -> дополнительные имена переменных окружения.
    В таком виде это ждёт api_keys.status()."""
    return {p["id"]: tuple(p.get("env_names") or ()) for p in all_records()}


def env_names_for(provider_id):
    p = get_provider(provider_id)
    return tuple((p or {}).get("env_names") or ())


def base_url_for(provider_id, rec=None):
    """Адрес endpoint'а: сначала заданный пользователем, потом из реестра.

    Пользовательский адрес выигрывает намеренно — так можно направить
    известного провайдера на зеркало или на локальный прокси-сервис, не
    дожидаясь правки реестра.

    rec — уже найденная запись провайдера. Нужен там, где записей много: с
    полным списком каталога поиск по идентификатору на каждое обращение
    складывался в сотни миллисекунд на сборке списка (замерено).
    """
    override = api_keys.get_base_url(provider_id)
    if override:
        return override.rstrip("/")
    p = rec if rec is not None else get_provider(provider_id)
    return str((p or {}).get("base_url") or "").rstrip("/")


def models_url(provider_id):
    """Адрес списка моделей или "" — если у провайдера его нет."""
    base = base_url_for(provider_id)
    path = str((get_provider(provider_id) or {}).get("models_path") or "")
    if not base or not path:
        return ""
    return base + path


def headers_for(provider_id):
    """Дополнительные заголовки провайдера. Заголовок Authorization ЗДЕСЬ НЕ
    СОБИРАЕТСЯ: секретами занимается транспорт, чтобы ключ не разошёлся по
    модулям и не попал в отладочную печать этого реестра.

    Имя клиента (User-Agent) не переопределяется: транспорт представляется
    настоящим именем плагина, и подменять его на имя чужой программы, чтобы
    пройти чей-то белый список, — не наша задача.
    """
    return dict((get_provider(provider_id) or {}).get("extra_headers") or {})


def unavailable_reason(provider_id, rec=None):
    """Почему провайдер объявлен, но обращаться к нему нельзя. "" — можно.

    Отдельно от readiness() и от отсутствия ключа: там пользователю чего-то не
    хватает и он может это исправить, а здесь исправить нечего — ограничение
    на стороне сервиса. Поэтому такие провайдеры остаются видимыми вместе с
    объяснением, но НИ ОДИН запрос к ним не отправляется.
    """
    p = rec if rec is not None else get_provider(provider_id)
    return str((p or {}).get("unavailable") or "")


def transport_for(provider_id, model=""):
    """Протокол запросов для модели провайдера.

    AgentRouter обслуживает GPT через OpenAI-совместимый endpoint, а Claude
    через Anthropic Messages API; остальные записи реестра используют OpenAI.

    Каталожные записи получают протокол по npm-пакету из каталога: 8 из 166
    помечены «@ai-sdk/anthropic», значит говорят на /messages. Оба транспорта у
    нас уже есть и работают, но живьём с этими сервисами никто не проверял — они
    и помечены «не проверено».
    """
    p = get_provider(provider_id) or {}
    kind = p.get("transport")
    if kind == "agentrouter":
        return "anthropic" if str(model or "").lower().startswith("claude-") else "openai"
    if kind == "anthropic":
        return "anthropic"
    return "openai"


def connect_timeout_for(provider_id):
    """Сколько секунд ждать соединения и ЗАГОЛОВКОВ ответа.

    Значение транспорта рассчитано на сервис, который отвечает сам. Посредник
    ждёт ещё и свой апстрим, поэтому ему нужен запас: иначе рабочий провайдер
    выглядит как недоступный. Задаётся полем connect_timeout в записи.
    """
    import openai_compat
    try:
        v = float((get_provider(provider_id) or {}).get("connect_timeout") or 0)
    except Exception:
        v = 0.0
    return v if v > 0 else openai_compat.DEFAULT_CONNECT_TIMEOUT


def test_with_stream(provider_id):
    """Проверять подключение потоковым запросом, а не обычным.

    Нужно шлюзам, которые не успевают отдать non-stream ответ в свой же
    таймаут и отвечают 504 вместо результата.
    """
    return bool((get_provider(provider_id) or {}).get("test_with_stream"))


def model_for(provider_id, rec=None):
    """Модель для запроса: выбранная пользователем, иначе из реестра."""
    chosen = api_keys.get_model(provider_id)
    if chosen:
        return chosen
    p = rec if rec is not None else get_provider(provider_id)
    return str((p or {}).get("default_model") or "")


# ---------------------------------------------------------------------------
# Готовность к работе
# ---------------------------------------------------------------------------

def _readiness_full(provider_id, rec=None):
    """(ok, причина_словами, код_причины). Внутренняя: наружу идут readiness()
    и readiness_code(), чтобы у каждой не менялась форма ответа.

    ЗАЧЕМ КОД РЯДОМ С ТЕКСТОМ. Текст причины здесь только по-русски: он
    писался под строку в настройках, где язык панели неважен. Как только та же
    причина становится пометкой на карточке провайдера, её нужно переводить, а
    переводить готовую фразу с сервера панель не может. Код — это то, что
    панель находит в своём словаре (agent_locale.gd); текст остаётся для
    журнала сервера и как запасной вариант.

    rec — уже найденная запись: см. пояснение у base_url_for.
    """
    p = rec if rec is not None else get_provider(provider_id)
    if p is None:
        return False, u"неизвестный провайдер «%s»" % provider_id, "unknown_provider"
    # Недоступность сервиса — первой: она не лечится ни ключом, ни моделью, и
    # просить их ввести было бы обманом.
    why = unavailable_reason(provider_id, p)
    if why:
        return False, why, "unavailable"
    if not base_url_for(provider_id, p):
        return False, u"не задан адрес endpoint'а", "no_base_url"
    if p.get("needs_key") and not api_keys.has_key(provider_id,
                                                  tuple(p.get("env_names") or ())):
        return False, u"не задан ключ API", "no_key"
    if not model_for(provider_id, p):
        return False, u"не выбрана модель", "no_model"
    return True, "", ""


def readiness(provider_id):
    """Можно ли уже отправлять запрос. Возвращает (ok, причина_если_нет).

    Проверяется до создания чата, чтобы пользователь узнал о нехватке
    настроек на экране настроек, а не посреди задачи.
    """
    ok, why, _code = _readiness_full(provider_id)
    return ok, why


def readiness_code(provider_id):
    """Причина неготовности одним словом для панели: "" (готов),
    "unknown_provider", "unavailable", "no_base_url", "no_key", "no_model"."""
    _ok, _why, code = _readiness_full(provider_id)
    return code


def models_public(provider_id):
    """Отдаёт ли провайдер список моделей БЕЗ ключа.

    Нужно панели, чтобы понимать, можно ли вообще посчитать модели у ещё не
    настроенного провайдера, или единственный честный ответ — «неизвестно».
    """
    return bool((get_provider(provider_id) or {}).get("models_public"))


def is_verified(provider_id):
    """Был ли с провайдером полный живой обмен настоящим ключом.

    Ни у одного провайдера этого пока нет — см. комментарий к полю "verified"
    у PROVIDERS. Функция существует, чтобы панель группировала провайдеров по
    факту, а не по догадке, и чтобы флаг было где переключить после прогона.
    """
    return bool((get_provider(provider_id) or {}).get("verified"))


# ---------------------------------------------------------------------------
# Автообновление списков моделей
#
# ЗАЧЕМ ЭТО ВООБЩЕ. Числа моделей брались ТОЛЬКО из ручного нажатия «Обновить
# список». Значит они были у провайдеров, которых пользователь и так открывал,
# и отсутствовали у всех остальных — а фильтр «с бесплатными» отбирает как раз
# по этим числам. Снаружи это выглядит как утверждение «бесплатные модели есть
# только у Opencode Zen», хотя на самом деле у OpenRouter их сотни и его просто
# ни разу не спрашивали. Пользователь при этом не может догадаться, что нужно
# зайти в каждого провайдера и нажать кнопку: список ведь уже показан.
#
# ПОЧЕМУ НЕ ОПРАШИВАТЬ ВСЕХ ПОДРЯД. Запрос к провайдеру, у которого нет ни
# ключа, ни публичного /models, гарантированно вернёт 401 — это трата времени
# пользователя и отказ в чужом журнале ни за что. Поэтому спрашиваем только
# тех, у кого ответ вообще возможен: публичный список моделей или сохранённый
# ключ. Недоступные (unavailable) не опрашиваются вовсе — к ним не ходят даже
# за списком моделей.
# ---------------------------------------------------------------------------

# Сколько наблюдение считается свежим. Двенадцать часов: идентификаторы моделей и
# тарифы меняются не ежечасно, а лишний обход провайдеров при каждом открытии
# окна — это чужие лимиты запросов, потраченные на подпись под названием. Ровно
# по этому сроку панель и обновляет списки сама: кнопки «обновить всё» в
# интерфейсе больше нет, обход начинается при открытии окна выбора, а решение
# «пора или нет» принимается здесь.
MODELS_FRESH_SECONDS = 12 * 60 * 60
# Пауза после неудачи. Заметно короче суток: неудача чаще всего значит «в этот
# момент не было сети», и держать провайдера без чисел до завтра из-за
# минутного обрыва незачем. Но и повторять на каждое открытие окна нельзя —
# ожидание ответа от недоступного хоста пользователь видит как задумчивость
# плагина.
MODELS_RETRY_SECONDS = 10 * 60


def can_fetch_models(provider_id):
    """Можно ли получить список моделей ПРЯМО СЕЙЧАС, не спрашивая ничего у
    пользователя: есть адрес, сервис доступен, и либо ключ уже есть, либо
    список отдаётся без ключа."""
    if not models_url(provider_id) or unavailable_reason(provider_id):
        return False
    if models_public(provider_id):
        return True
    p = get_provider(provider_id) or {}
    if not p.get("needs_key"):
        # Провайдер без обязательного ключа (свой адрес, локальный сервер):
        # спрашивать можно, отказ ничего не стоит.
        return True
    return api_keys.has_key(provider_id, env_names_for(provider_id))


def models_stale(provider_id, stats=None, now=None):
    """Пора ли обновлять список моделей этого провайдера.

    Возвращает True, если чисел нет вовсе, они старше MODELS_FRESH_SECONDS
    или последняя попытка была неудачной и с неё прошло больше
    MODELS_RETRY_SECONDS.
    """
    if stats is None:
        stats = api_keys.get_stats(provider_id)
    stats = stats or {}
    now = time.time() if now is None else now
    if stats.get("models_error"):
        return (now - float(stats.get("models_try_at") or 0.0)) >= MODELS_RETRY_SECONDS
    at = float(stats.get("models_at") or 0.0)
    if at <= 0 or int(stats.get("models_total", -1)) < 0:
        return True
    return (now - at) >= MODELS_FRESH_SECONDS


def autoscan_targets(now=None):
    """Провайдеры, чей список моделей стоит обновить сам собой.

    Порядок как в реестре, чтобы вывод сервера читался предсказуемо.

    Каталожные записи попадают сюда только с сохранённым ключом: им не
    выставляется models_public, а значит can_fetch_models() без ключа отвечает
    False. Иначе включение полного списка означало бы сто шестьдесят запросов к
    незнакомым сервисам при открытии окна выбора.
    """
    all_stats = api_keys.get_stats()
    out = []
    for p in all_records():
        pid = p["id"]
        if can_fetch_models(pid) and models_stale(pid, all_stats.get(pid), now):
            out.append(pid)
    return out


def list_providers():
    """Список для панели: метаданные + состояние ключа. Без секретов."""
    records = all_records()
    st = api_keys.status([p["id"] for p in records], env_map())
    all_stats = api_keys.get_stats()
    out = []
    for p in records:
        pid = p["id"]
        key_st = (st.get("providers") or {}).get(pid) or {}
        ok, why, code = _readiness_full(pid, p)
        registry_url = str(p.get("base_url") or "")
        resolved_url = base_url_for(pid, p)
        out.append({
            "id": pid,
            "name": p["name"],
            "base_url": resolved_url,
            # Адрес открыт для правки у ВСЕХ провайдеров, а не только у «своего
            # адреса»: сервис может переехать, и тогда пользователь исправляет
            # адрес сам, не дожидаясь новой версии плагина (base_url_for отдаёт
            # приоритет заданному вручную). Испорченный адрес не пройдёт —
            # api_keys.validate_base_url отклоняет мусор, а пустое поле
            # означает возврат к адресу из реестра, то есть кнопка «сбросить»
            # это просто очистка поля.
            "base_url_editable": True,
            # Что стоит в реестре — панели, чтобы показать это подсказкой в
            # пустом поле и было видно, к чему вернёт очистка.
            "base_url_default": registry_url,
            # Адрес подменён вручную. Отдельным флагом, потому что провайдер с
            # чужим адресом ведёт себя не так, как написано в его описании, и
            # об этом стоит предупредить прежде, чем человек пойдёт искать
            # причину отказов в ключе.
            "base_url_custom": bool(registry_url) and resolved_url != registry_url.rstrip("/"),
            "needs_key": bool(p.get("needs_key")),
            "configured": bool(key_st.get("configured")),
            "key_source": key_st.get("source") or "",
            "masked": key_st.get("masked") or "",
            # Все ключи провайдера с их состоянием (маска, исчерпан ли, до
            # какого срока). Квота бесплатных тарифов считается НА КЛЮЧ, поэтому
            # панель обязана показывать список, а не один ключ: иначе
            # «исчерпано» выглядит как приговор модели, хотя рядом лежит рабочий
            # второй ключ. Сырых ключей здесь нет — только маски (keys_state).
            "keys": key_st.get("keys") or [],
            "keys_total": int(key_st.get("keys_total") or 0),
            "keys_spent": int(key_st.get("keys_spent") or 0),
            "model": model_for(pid, p),
            "models": list(p.get("models") or []),
            "models_public": bool(p.get("models_public")),
            "ready": ok,
            "not_ready_reason": why,
            # Та же причина кодом: текст выше существует только по-русски и
            # непригоден как подпись на карточке в английской локали.
            "not_ready_code": code,
            # Отдельно от ready: панель может показать «нельзя настроить» иначе,
            # чем «не хватает ключа». Пустая строка — обычный провайдер.
            "unavailable": unavailable_reason(pid, p),
            # Пометка разработчика о живом прогоне. Сейчас False у всех — это
            # правда, а не недоделка (см. комментарий к PROVIDERS).
            "verified": bool(p.get("verified")),
            # Запись НЕ разобрана человеком, а взята из каталога models.dev.
            # Панель показывает такие своей группой и с пометкой: про них не
            # проверено ни то, что адрес рабочий, ни то, что сервис говорит на
            # нашем протоколе.
            "from_catalog": bool(p.get("from_catalog")),
            # Ссылка на документацию сервиса — единственное, чем мы можем помочь
            # там, где сами ничего не проверяли.
            "doc": str(p.get("doc") or ""),
            # Сколько моделей у него ПО КАТАЛОГУ. Отдельно от stats: те числа
            # измерены у ЭТОГО ключа, а это утверждение справочника о мире.
            "catalog_models": int(p.get("catalog_models") or 0),
            "catalog_models_free": int(p.get("catalog_models_free") or 0),
            # Наблюдения с ЭТОЙ машины: сколько моделей и бесплатных нашлось
            # при последнем обновлении списка, чем кончилась проверка
            # подключения. Пустой словарь — ничего не измеряли.
            "stats": all_stats.get(pid) or {},
            "note_ru": p.get("note_ru", ""),
            "note_en": p.get("note_en", ""),
        })
    return out


# ---------------------------------------------------------------------------
# Разбор списка моделей провайдера
# ---------------------------------------------------------------------------

def is_free_model(rec):
    """Бесплатна ли модель по ответу /models.

    Три признака, потому что сервисы описывают это по-разному:
      * суффикс ":free" в идентификаторе (OpenRouter);
      * суффикс "-free" (Opencode Zen: deepseek-v4-flash-free, hy3-free и
        прочие — в их ответе /models полей цены нет вовсе, только id, поэтому
        других зацепок не остаётся);
      * нулевая цена в pricing.
    Цены приходят строками ("0", "0.0", "0E-8"), поэтому сравниваем численно
    и терпимо: неизвестный формат — считаем платной, чтобы случайно не
    пообещать пользователю бесплатность.
    """
    if not isinstance(rec, dict):
        return False
    mid = str(rec.get("id") or "")
    if mid.endswith(":free") or mid.endswith("-free"):
        return True
    pricing = rec.get("pricing")
    if not isinstance(pricing, dict):
        return False
    fields = ("prompt", "completion")
    seen = False
    for f in fields:
        if f not in pricing:
            continue
        try:
            if float(pricing[f]) != 0.0:
                return False
        except Exception:
            return False
        seen = True
    return seen


def live_pricing_unit(provider_id):
    """В чём провайдер присылает цену в своём /models: "per_token",
    "per_million" или "" — единица неизвестна, цену НЕ читаем.

    Пустая строка по умолчанию намеренно. «OpenAI-совместимый» про единицу
    цены не говорит ничего, и угадать её нельзя: ошибка здесь показывает
    пользователю цену, завышенную или заниженную в миллион раз. Ставится в
    записи провайдера (live_pricing) после сверки живым запросом.
    """
    return str((get_provider(provider_id) or {}).get("live_pricing") or "")


def _positive_int(value):
    """Целое больше нуля или None. Ноль и отрицательное — это не «неизвестно»,
    а мусор, и подставлять его в лимиты нельзя."""
    if isinstance(value, bool):
        return None
    try:
        n = int(value)
    except Exception:
        return None
    return n if n > 0 else None


def live_extras(rec, provider_id=""):
    u"""Цена, лимиты и признак function calling ИЗ ЖИВОГО ОТВЕТА провайдера.

    Возвращает подмножество полей {cost_in, cost_out, context, max_output,
    tool_call} — ровно те, которые провайдер реально присылает. Остальное потом
    дополнит каталог models.dev (catalog.enrich), и он же подпишет, что это его
    числа, а не провайдера.

    ЗАМЕРЕНО (OpenRouter, 19.08.2026, 416 записей): pricing есть у 416,
    context_length у 416, top_provider.max_completion_tokens у 367,
    supported_parameters с "tools" — по ним и виден родной function calling.
    У Opencode Zen в записи ТОЛЬКО id, object, created, owned_by — оттуда не
    берётся ничего, и это нормально: для него и нужен каталог.

    ЕДИНИЦА ЦЕНЫ НЕ УГАДЫВАЕТСЯ. Если у провайдера в реестре не отмечено
    live_pricing, цена из ответа игнорируется целиком: показать её не в тех
    единицах хуже, чем не показать вовсе.
    """
    if not isinstance(rec, dict):
        return {}
    out = {}
    unit = live_pricing_unit(provider_id)
    if unit:
        mult = 1000000.0 if unit == "per_token" else 1.0
        pricing = rec.get("pricing")
        if isinstance(pricing, dict):
            for src, dst in (("prompt", "cost_in"), ("completion", "cost_out")):
                if src not in pricing:
                    continue
                try:
                    # ОКРУГЛЕНИЕ ОБЯЗАТЕЛЬНО. Цена приходит за один токен
                    # ("0.000000225"), и умножение на миллион в двоичной
                    # плавающей точке даёт 0.22499999999999998 вместо 0.225 —
                    # такое число уезжает в JSON панели и в журнал как есть.
                    # Шесть знаков с запасом: самые дешёвые тарифы у провайдеров
                    # порядка 0.01 за миллион.
                    out[dst] = round(float(pricing[src]) * mult, 6)
                except Exception:
                    # Цена пришла в неожидаемом виде — не показываем ничего.
                    # Строки вроде "-1" у OpenRouter означают «зависит от
                    # маршрута», и превращать их в число значит соврать.
                    out.pop(dst, None)
            if out.get("cost_in", 0.0) < 0 or out.get("cost_out", 0.0) < 0:
                out.pop("cost_in", None)
                out.pop("cost_out", None)
    top = rec.get("top_provider") if isinstance(rec.get("top_provider"), dict) else {}
    ctx = _positive_int(rec.get("context_length")) \
        or _positive_int(top.get("context_length"))
    if ctx:
        out["context"] = ctx
    mout = _positive_int(top.get("max_completion_tokens")) \
        or _positive_int(rec.get("max_completion_tokens")) \
        or _positive_int(rec.get("max_output_tokens"))
    if mout:
        out["max_output"] = mout
    params = rec.get("supported_parameters")
    if isinstance(params, list):
        # Родной function calling виден по наличию "tools" среди поддерживаемых
        # параметров. Плагину он не нужен (действия идут JSON-блоком в тексте),
        # но раз провайдер сказал это сам — его слово точнее справочника.
        out["tool_call"] = "tools" in [str(p) for p in params]
    # КОГДА МОДЕЛЬ ПОЯВИЛАСЬ. В формате OpenAI это created — время в секундах, и
    # его присылают даже те, кто не присылает больше ничего (у Opencode Zen в
    # записи только id, object, created, owned_by). Берётся ради порядка в
    # списке: моделей у провайдера бывает четыреста, новые нужны чаще старых,
    # а по имени свежесть не определить — gpt-4.1 новее gpt-4o, но алфавит
    # считает иначе.
    #
    # Своих догадок нет: не прислал created — модель просто встанет после тех,
    # про кого дата известна. Каталог models.dev здесь не помощник, его
    # release_date отбрасывается намеренно (см. catalog._clean_model: полный
    # каталог 4 МБ против 59 КБ).
    created = _positive_int(rec.get("created"))
    if created:
        out["created"] = created
    return out


def parse_models_detailed(data, free_only=False, provider_id=""):
    """Модели из ответа /models как записи [{"id": ..., "free": ...}, ...].

    Формат OpenAI: {"data": [{"id": ...}, ...]}. Некоторые совместимые
    сервисы отдают сразу список — поддерживаем оба варианта, потому что
    падать из-за формы обёртки здесь незачем.

    ПОЧЕМУ ЗАПИСИ, А НЕ СТРОКИ. Признак бесплатности вычисляется здесь и
    раньше выбрасывался: наружу уходили одни идентификаторы. Панель из-за
    этого не могла отличить бесплатную модель от платной иначе как по
    суффиксу в имени, а модель с нулевой ценой БЕЗ суффикса выглядела
    платной. Теперь признак доходит до панели, и он же даёт счётчик
    бесплатных моделей у провайдера (api_keys.record_models_stats).

    ЧТО ЕЩЁ ЗАБИРАЕТСЯ ИЗ ЖИВОГО ОТВЕТА. Цена, окно контекста, предел ответа и
    поддержка родного function calling — там, где провайдер их присылает
    (см. live_extras). Это ПЕРВИЧНЫЕ числа: каталог models.dev потом только
    заполняет то, чего здесь не оказалось, и никогда не перебивает. Замерено,
    зачем так: у moonshotai/kimi-k2.6 каталог отстал и завышал цену на 47%
    против живого ответа OpenRouter.

    provider_id нужен ровно для единицы измерения цены — она не выводится из
    ответа и берётся из реестра (см. live_pricing).
    """
    if isinstance(data, dict):
        items = data.get("data")
    else:
        items = data
    if not isinstance(items, list):
        return []
    seen = {}
    extras = {}
    for rec in items:
        if isinstance(rec, str):
            # Голая строка вместо объекта: цены нет, судим только по имени —
            # тем же правилом, что и is_free_model, чтобы список и фильтр
            # «только бесплатные» не расходились между двумя ветками.
            mid, free = rec, is_free_model({"id": rec})
            more = {}
        elif isinstance(rec, dict):
            mid, free = str(rec.get("id") or ""), is_free_model(rec)
            more = live_extras(rec, provider_id)
        else:
            continue
        if not mid:
            continue
        if free_only and not free:
            continue
        # Дубли идентификаторов бывают; бесплатный признак сохраняем.
        seen[mid] = seen.get(mid, False) or free
        if more:
            extras.setdefault(mid, {}).update(more)
    # Бесплатные — вверх списка, дальше по алфавиту: пользователю без денег
    # (основной случай на старте) не приходится их выискивать. Сортируем по
    # ФАКТИЧЕСКОЙ бесплатности из pricing, а не по суффиксу ":free" — иначе
    # модель с нулевой ценой без суффикса оказалась бы среди платных.
    order = sorted(seen, key=lambda m: (not seen[m], m))
    out = []
    for m in order:
        item = {"id": m, "free": bool(seen[m])}
        item.update(extras.get(m) or {})
        out.append(item)
    return out


def parse_models_response(data, free_only=False, provider_id=""):
    """Только идентификаторы моделей — прежний формат ответа для панели.

    Обёртка, а не второй разбор: два независимых прохода по одному ответу
    неизбежно разошлись бы в трактовке бесплатности, и список моделей начал
    бы противоречить счётчику «столько-то бесплатных» на том же экране.
    """
    return [rec["id"] for rec in parse_models_detailed(
        data, free_only=free_only, provider_id=provider_id)]


def count_models(records):
    """(всего, бесплатных) по записям parse_models_detailed.

    Считать ОБЯЗАТЕЛЬНО по неотфильтрованному разбору: при free_only=True в
    списке остаются только бесплатные, и «всего» совпало бы с «бесплатных» —
    счётчик у провайдера показывал бы 100% бесплатных моделей у любого
    платного сервиса.
    """
    recs = list(records or [])
    return len(recs), sum(1 for r in recs if r.get("free"))
