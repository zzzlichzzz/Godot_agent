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

import api_keys

# Заголовок с названием приложения. OpenRouter показывает его в статистике
# использования ключа — пользователю полезно видеть, что запросы идут именно
# от плагина, а не от чего-то ещё, зашедшего на его ключ.
APP_TITLE = "Godot Agent"

# ПОЧЕМУ ЗДЕСЬ ЧУЖОЙ USER-AGENT. AgentRouter (панель на new-api) пускает
# только клиентов из своего белого списка и опознаёт их ИСКЛЮЧИТЕЛЬНО по
# User-Agent. С любым другим значением он отвечает 401 и телом
# {"type":"unauthorized_client_error","error":{"message":"unauthorized client
# detected..."}} — на полностью рабочем ключе. Проверено запросами:
#   claude-cli/1.0.119 (external, cli) -> 200    claude-cli/1.0.0 -> 401
#   opencode/1.0.0                     -> 200    opencode        -> 401
#   cline/3.0.0                        -> 200    GodotAgent/0.6  -> 401
# То есть нужно и имя из списка, и версия. Обойти это «правильным» способом
# нельзя: сервис не предлагает регистрации клиента, а сообщение об ошибке
# отправляет в Discord. Значение вынесено в переменную окружения — если
# AgentRouter поменяет список, ключ менять не придётся.
ENV_AGENTROUTER_UA = "GODOT_AGENT_AGENTROUTER_UA"
AGENTROUTER_USER_AGENT = "opencode/1.0.0"


def agentrouter_user_agent():
    return (os.environ.get(ENV_AGENTROUTER_UA) or "").strip() or AGENTROUTER_USER_AGENT

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
        # Без этого User-Agent сервис отвечает 401 на любой запрос, включая
        # GET /models. Подробности — в комментарии к AGENTROUTER_USER_AGENT.
        "user_agent": agentrouter_user_agent,
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
        "note_ru": "GPT-модели работают через OpenAI API; Claude-модели — через Anthropic API. Один ключ AgentRouter подходит для обеих.",
        "note_en": "GPT models use the OpenAI API; Claude models use the Anthropic API. One AgentRouter key works for both.",
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
]

# Провайдер, предлагаемый по умолчанию при первом входе.
DEFAULT_PROVIDER_ID = "openrouter"


# ---------------------------------------------------------------------------
# Доступ к реестру
# ---------------------------------------------------------------------------

def get_provider(provider_id):
    for p in PROVIDERS:
        if p["id"] == str(provider_id or ""):
            return p
    return None


def provider_ids():
    return [p["id"] for p in PROVIDERS]


def env_map():
    """provider_id -> дополнительные имена переменных окружения.
    В таком виде это ждёт api_keys.status()."""
    return {p["id"]: tuple(p.get("env_names") or ()) for p in PROVIDERS}


def env_names_for(provider_id):
    p = get_provider(provider_id)
    return tuple((p or {}).get("env_names") or ())


def base_url_for(provider_id):
    """Адрес endpoint'а: сначала заданный пользователем, потом из реестра.

    Пользовательский адрес выигрывает намеренно — так можно направить
    известного провайдера на зеркало или на локальный прокси-сервис, не
    дожидаясь правки реестра.
    """
    override = api_keys.get_base_url(provider_id)
    if override:
        return override.rstrip("/")
    p = get_provider(provider_id)
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

    Поле user_agent (строка или функция) перекрывает User-Agent транспорта.
    Нужно тем сервисам, которые пускают только клиентов из своего белого
    списка — см. AGENTROUTER_USER_AGENT.
    """
    p = get_provider(provider_id) or {}
    h = dict(p.get("extra_headers") or {})
    ua = p.get("user_agent")
    if callable(ua):
        ua = ua()
    if ua:
        h["User-Agent"] = str(ua)
    return h


def transport_for(provider_id, model=""):
    """Протокол запросов для модели провайдера.

    AgentRouter обслуживает GPT через OpenAI-совместимый endpoint, а Claude
    через Anthropic Messages API; остальные записи используют OpenAI как раньше.
    """
    p = get_provider(provider_id) or {}
    if p.get("transport") == "agentrouter" and str(model or "").lower().startswith("claude-"):
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


def model_for(provider_id):
    """Модель для запроса: выбранная пользователем, иначе из реестра."""
    chosen = api_keys.get_model(provider_id)
    if chosen:
        return chosen
    return str((get_provider(provider_id) or {}).get("default_model") or "")


# ---------------------------------------------------------------------------
# Готовность к работе
# ---------------------------------------------------------------------------

def readiness(provider_id):
    """Можно ли уже отправлять запрос. Возвращает (ok, причина_если_нет).

    Проверяется до создания чата, чтобы пользователь узнал о нехватке
    настроек на экране настроек, а не посреди задачи.
    """
    p = get_provider(provider_id)
    if p is None:
        return False, u"неизвестный провайдер «%s»" % provider_id
    if not base_url_for(provider_id):
        return False, u"не задан адрес endpoint'а"
    if p.get("needs_key") and not api_keys.has_key(provider_id,
                                                  env_names_for(provider_id)):
        return False, u"не задан ключ API"
    if not model_for(provider_id):
        return False, u"не выбрана модель"
    return True, ""


def list_providers():
    """Список для панели: метаданные + состояние ключа. Без секретов."""
    st = api_keys.status(provider_ids(), env_map())
    out = []
    for p in PROVIDERS:
        pid = p["id"]
        key_st = (st.get("providers") or {}).get(pid) or {}
        ok, why = readiness(pid)
        out.append({
            "id": pid,
            "name": p["name"],
            "base_url": base_url_for(pid),
            "base_url_editable": not p.get("base_url"),
            "needs_key": bool(p.get("needs_key")),
            "configured": bool(key_st.get("configured")),
            "key_source": key_st.get("source") or "",
            "masked": key_st.get("masked") or "",
            "model": model_for(pid),
            "models": list(p.get("models") or []),
            "ready": ok,
            "not_ready_reason": why,
            "note_ru": p.get("note_ru", ""),
            "note_en": p.get("note_en", ""),
        })
    return out


# ---------------------------------------------------------------------------
# Разбор списка моделей провайдера
# ---------------------------------------------------------------------------

def is_free_model(rec):
    """Бесплатна ли модель по ответу /models.

    Два признака, потому что сервисы описывают это по-разному: суффикс
    ":free" в идентификаторе (OpenRouter) и нулевая цена в pricing. Цены
    приходят строками ("0", "0.0", "0E-8"), поэтому сравниваем численно
    и терпимо: неизвестный формат — считаем платной, чтобы случайно не
    пообещать пользователю бесплатность.
    """
    if not isinstance(rec, dict):
        return False
    mid = str(rec.get("id") or "")
    if mid.endswith(":free"):
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


def parse_models_response(data, free_only=False):
    """Идентификаторы моделей из ответа /models.

    Формат OpenAI: {"data": [{"id": ...}, ...]}. Некоторые совместимые
    сервисы отдают сразу список — поддерживаем оба варианта, потому что
    падать из-за формы обёртки здесь незачем.
    """
    if isinstance(data, dict):
        items = data.get("data")
    else:
        items = data
    if not isinstance(items, list):
        return []
    seen = {}
    for rec in items:
        if isinstance(rec, str):
            mid, free = rec, rec.endswith(":free")
        elif isinstance(rec, dict):
            mid, free = str(rec.get("id") or ""), is_free_model(rec)
        else:
            continue
        if not mid:
            continue
        if free_only and not free:
            continue
        # Дубли идентификаторов бывают; бесплатный признак сохраняем.
        seen[mid] = seen.get(mid, False) or free
    # Бесплатные — вверх списка, дальше по алфавиту: пользователю без денег
    # (основной случай на старте) не приходится их выискивать. Сортируем по
    # ФАКТИЧЕСКОЙ бесплатности из pricing, а не по суффиксу ":free" — иначе
    # модель с нулевой ценой без суффикса оказалась бы среди платных.
    return sorted(seen, key=lambda m: (not seen[m], m))
