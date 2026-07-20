# -*- coding: utf-8 -*-
"""Реестр сайтов-нейросетей, с которыми работает агент.

Сейчас поддержаны: Google AI Studio, DeepSeek. Чтобы добавить новый:
допиши запись в SITES (id, name, new_chat_url, match-домены, parser).
В будущем можно будет добавлять «свои» страницы с универсальным
парсером — заготовки для этого оставлены ниже (register_custom_site /
load_custom_sites), сама реализация пока отложена.
"""
from urllib.parse import urlparse

# Встроенные (проверенные) сайты.
SITES = [
    {
        "id": "aistudio",
        "name": "Google AI Studio",
        "new_chat_url": "https://aistudio.google.com/prompts/new_chat",
        "match": ["aistudio.google.com"],
        "parser": "ai_parser",   # модуль, умеющий читать ответы с этой страницы
        "builtin": True,
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "new_chat_url": "https://chat.deepseek.com/",
        "match": ["chat.deepseek.com", "deepseek.com"],
        "parser": "deepseek_parser",   # модуль deepseek_parser.py
        "builtin": True,
    },
    # Пример будущего сайта (выключен, оставлен как ориентир):
    # {"id": "chatgpt", "name": "ChatGPT", "new_chat_url": "https://chatgpt.com/",
    #  "match": ["chatgpt.com", "chat.openai.com"], "parser": "universal", "builtin": True},
    {
        "id": "qwen",
        "name": "Qwen (заготовка)",
        "new_chat_url": "https://chat.qwen.ai/",
        "match": ["chat.qwen.ai", "qwen.ai"],
        "parser": "qwen_parser",   # модуль qwen_parser.py — ЗАГОТОВКА: селекторы уточнить
        "builtin": True,
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
            if host == m or host.endswith("." + m) or m in host:
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
