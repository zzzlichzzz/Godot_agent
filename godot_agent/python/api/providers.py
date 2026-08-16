# -*- coding: utf-8 -*-
"""Реестр провайдеров API — нейросети, доступные по ключу, а не через браузер.

ПОЧЕМУ ОТДЕЛЬНО ОТ sites.py. У записи браузерного сайта есть new_chat_url,
match-домены и needs_visibility_spoof — для работы по ключу это бессмыслица.
Смешивать два реестра значит засорять проверенный список браузерных сайтов
полями, которые там никогда не понадобятся, и наоборот. Записи чатов
различаются полем kind: отсутствует или "browser" — сайт в браузере,
"api" — провайдер отсюда.

ЕДИНЫЙ ФОРМАТ ЗАПРОСА. Все провайдеры ниже говорят на одном протоколе —
POST <base_url>/chat/completions с телом {model, messages, stream}. Это
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
import api_keys

# Заголовок с названием приложения. OpenRouter показывает его в статистике
# использования ключа — пользователю полезно видеть, что запросы идут именно
# от плагина, а не от чего-то ещё, зашедшего на его ключ.
APP_TITLE = "Godot Agent"

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
    модулям и не попал в отладочную печать этого реестра."""
    return dict((get_provider(provider_id) or {}).get("extra_headers") or {})


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
