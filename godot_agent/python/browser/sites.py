# -*- coding: utf-8 -*-
"""Реестр сайтов-нейросетей, с которыми работает агент.

Сейчас поддержаны: Google AI Studio, DeepSeek. Чтобы добавить новый:
допиши запись в SITES (id, name, new_chat_url, match-домены, parser).
В будущем можно будет добавлять «свои» страницы с универсальным
парсером — заготовки для этого оставлены ниже (register_custom_site /
load_custom_sites), сама реализация пока отложена.
"""
from urllib.parse import urlparse

# v75: PyInstaller (server.exe) kladyot v sborku tolko staticheski
# importirovannye moduli. Parsery zagruzhayutsya dinamicheski cherez
# importlib, poetomu bez etogo bloka ikh net vnutri exe
# (oshibka "No module named 'qwen_parser'").
try:
    import ai_parser as _static_ai_parser  # noqa: F401
    import deepseek_parser as _static_deepseek_parser  # noqa: F401
    import qwen_parser as _static_qwen_parser  # noqa: F401
    import kimi_parser as _static_kimi_parser  # noqa: F401
    import arena_parser as _static_arena_parser  # noqa: F401
except Exception:
    pass

# Встроенные (проверенные) сайты.
SITES = [
    {
        "id": "aistudio",
        "name": "Google AI Studio",
        "new_chat_url": "https://aistudio.google.com/prompts/new_chat",
        "match": ["aistudio.google.com"],
        "parser": "ai_parser",   # модуль, умеющий читать ответы с этой страницы
        "builtin": True,
        # Angular придерживает рендер в свёрнутом окне, а ai_parser читает
        # ответ гибридно (DOM + сеть как страховка) — спуф нужен.
        "needs_visibility_spoof": True,
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "new_chat_url": "https://chat.deepseek.com/",
        "match": ["chat.deepseek.com", "deepseek.com"],
        "parser": "deepseek_parser",   # модуль deepseek_parser.py
        "builtin": True,
        # Единственный сайт, который читается ЧИСТО из DOM — без спуфа ответ
        # в свёрнутом окне может не дорисоваться.
        "needs_visibility_spoof": True,
    },
    # Пример будущего сайта (выключен, оставлен как ориентир):
    # {"id": "chatgpt", "name": "ChatGPT", "new_chat_url": "https://chatgpt.com/",
    #  "match": ["chatgpt.com", "chat.openai.com"], "parser": "universal", "builtin": True},
    {
        "id": "qwen",
        "name": "Qwen",
        "new_chat_url": "https://chat.qwen.ai/",
        "match": ["chat.qwen.ai", "qwen.ai"],
        "parser": "qwen_parser",
        "builtin": True,
        # Читается из сети (SSE), но DOM остаётся рабочим путём: extract_answer
        # начинает с DOM, а сеть подстраховывает (+ Monaco-блоки читаются из DOM).
        "needs_visibility_spoof": True,
    },
    {
        "id": "kimi",
        "name": "Kimi",
        "new_chat_url": "https://www.kimi.com/",
        "match": ["kimi.com"],
        "parser": "kimi_parser",
        "builtin": True,
        # DOM нужен только для печати и отправки, ответ читается ЦЕЛИКОМ из сети
        # (connect+json) — рендер не важен, спуф не ставим.
        "needs_visibility_spoof": False,
    },
    {
        "id": "arena",
        "name": "Arena AI",
        "new_chat_url": "https://arena.ai/text/direct",
        "match": ["arena.ai"],
        "parser": "arena_parser",
        "builtin": True,
        # Ответ читается из сети (Vercel streaming) — рендер не важен, спуф не нужен.
        "needs_visibility_spoof": False,
    },
]


def _host(url):
    try:
        h = (urlparse(url).netloc or "").lower()
    except Exception:
        return ""
    if h.startswith("www."):
        h = h[4:]
    return h


def _all_sites():
    return SITES + load_custom_sites()


def list_sites():
    """Список сайтов для панели (для vbox выбора нейросети)."""
    out = []
    for s in _all_sites():
        out.append({"id": s["id"], "name": s["name"],
                    "new_chat_url": s["new_chat_url"],
                    "builtin": bool(s.get("builtin"))})
    return out


def get_site(site_id):
    for s in _all_sites():
        if s["id"] == site_id:
            return s
    return None


def get_parser_module(site_id=None, url=None):
    """Модуль-парсер для сайта: по id сайта, иначе по адресу страницы,
    иначе ai_parser (Google AI Studio) как парсер по умолчанию."""
    import importlib
    s = get_site(site_id) if site_id else None
    if s is None and url:
        s = detect_site(url)
    name = (s or {}).get("parser") or "ai_parser"
    try:
        return importlib.import_module(name)
    except Exception as e:
        print("[sites] Не удалось загрузить парсер %s (%s) — использую ai_parser." % (name, e))
        import ai_parser
        return ai_parser


def detect_site(url):
    """По адресу страницы определяет, какому сайту она принадлежит."""
    host = _host(url)
    if not host:
        return None
    for s in _all_sites():
        for m in s.get("match", []):
            m = m.lower()
            if host == m or host.endswith("." + m):
                return s
    return None


def same_site(url_a, url_b):
    """True, если оба адреса относятся к одному сайту (по домену)."""
    ha, hb = _host(url_a), _host(url_b)
    if not ha or not hb:
        return False
    if ha == hb:
        return True
    sa, sb = detect_site(url_a), detect_site(url_b)
    return bool(sa and sb and sa["id"] == sb["id"])


def site_name_for_url(url):
    s = detect_site(url)
    if s:
        return s["name"]
    return _host(url) or "неизвестный сайт"


def needs_visibility_spoof(url=None, site_id=None):
    """Нужна ли этому сайту подмена document.visibilityState/hidden.

    Подмена — самый заметный след автоматизации из всего, что делает агент
    (страница видит её одной строкой JS), поэтому она ставится ТОЛЬКО там,
    где без неё ломается чтение ответа: сайт придерживает рендер в свёрнутом
    окне, а ответ читается из DOM. Сайтам, читающим ответ из СЕТИ, рендер
    безразличен — троттлинг Chrome душит таймеры и рендер, но не сетевые потоки.

    Неизвестный сайт (в реестре нет) — False: не оставляем следов там, где
    ещё не доказано, что без спуфа не работает.
    """
    s = get_site(site_id) if site_id else None
    if s is None and url:
        s = detect_site(url)
    if s is None:
        return False
    return bool(s.get("needs_visibility_spoof"))


# ---------------------------------------------------------------------------
# ЗАГОТОВКА на будущее: пользовательские сайты + универсальный парсер.
# Идея: пользователь добавляет свой адрес, универсальный парсер подбирает
# алгоритм чтения ответов, и если он работает — сохраняем «профиль парсера»
# (селекторы/эвристики) в память проекта, чтобы переиспользовать. Пока не
# реализовано: функции ниже — точки расширения, не ломающие текущую работу.
# ---------------------------------------------------------------------------

def load_custom_sites():
    """TODO: загрузка пользовательских сайтов из памяти проекта.
    Пока возвращает пустой список (заготовка под будущую реализацию)."""
    return []


def register_custom_site(name, url, parser_profile=None):
    """TODO: сохранить пользовательский сайт + профиль универсального
    парсера в память проекта. Заглушка под будущую реализацию."""
    raise NotImplementedError("Пользовательские сайты появятся позже (универсальный парсер).")
