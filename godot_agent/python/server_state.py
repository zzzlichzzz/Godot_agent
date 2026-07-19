# -*- coding: utf-8 -*-
"""Состояние сессии сервера + общие помощники.

Здесь живёт единое STATE, держатель драйвера браузера, привязка чатов,
флаг primed и живой прогресс. Вынесено из main.py, чтобы и основные
маршруты, и chat_routes.py работали с ОДНИМ состоянием.
"""
import os
import json as _json

import history_manager as history
import chat_store
import sites

# Глобальное состояние сессии
STATE = {
    "project_root": None,
    "pending_action": None,   # ожидающее подтверждения WRITE-действие
    "current_chat_id": None,  # активный чат (см. chat_store.py)
    "pending_batch": None,    # ожидающая подтверждений пачка файлов на чтение
    "pending_plan": None,     # ожидающий подтверждения/выполнения план (plan-режим, цепочка шагов)
    "is_primed": False,
    "action_note": "",
    "user_data_dir": None,       # user:// папка проекта (логи игры, хранилище истории)
    "addon_dir": None,            # папка аддона на диске (для вшитого справочника API)
    "pending_log_report": None,  # подготовленный отчёт об ошибках запуска
    "progress": {"active": False},
}

# Драйвер браузера храним в держателе: он создаётся уже после импорта.
_holder = {"driver": None}


def set_driver(d):
    _holder["driver"] = d


def get_driver():
    return _holder["driver"]


def _prime_flag_path(project_root):
    # Флаг «primed» храним рядом с историей изменений (в user://), чтобы
    # перезапуск сервера НЕ заставлял заново отправлять дерево проекта.
    try:
        base = history.get_storage_dir(project_root)
    except Exception:
        return None
    if not base:
        return None
    return os.path.join(base, "agent_prime.json")


def _load_primed(project_root):
    p = _prime_flag_path(project_root)
    if not p or not os.path.isfile(p):
        return False
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = _json.load(f)
        return bool(data.get("primed")) and data.get("root") == project_root
    except Exception:
        return False


def _save_primed(project_root, val):
    p = _prime_flag_path(project_root)
    if not p:
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            _json.dump({"primed": bool(val), "root": project_root}, f)
    except Exception:
        pass


def _chats_dir():
    return STATE.get("user_data_dir")


def get_current_chat():
    base = _chats_dir()
    cid = STATE.get("current_chat_id")
    if not base or not cid:
        return None
    return chat_store.find_chat(base, cid)


def _ensure_current_chat(first_prompt=""):
    """Гарантирует, что текущая переписка привязана к записи чата."""
    base = _chats_dir()
    if not base:
        return None
    if STATE.get("current_chat_id"):
        rec = chat_store.find_chat(base, STATE["current_chat_id"])
        if rec is not None:
            return rec
    url = ""
    try:
        url = get_driver().current_url or ""
    except Exception:
        pass
    rec = chat_store.create_chat(base, url=url,
                                 title=chat_store.title_from_prompt(first_prompt),
                                 primed=bool(STATE.get("is_primed")))
    site = sites.detect_site(url)
    if site:
        chat_store.update_chat(base, rec["id"], site_id=site["id"], site_name=site["name"])
        rec = chat_store.find_chat(base, rec["id"]) or rec
    STATE["current_chat_id"] = rec["id"]
    print("--> Создана запись чата: %s (%s)" % (rec["title"], rec["id"]))
    return rec


def _remember(role, text):
    """Дописывает реплику в сохранённый диалог текущего чата."""
    base = _chats_dir()
    cid = STATE.get("current_chat_id")
    if not base or not cid or not text:
        return
    try:
        chat_store.append_transcript(base, cid, role, text)
    except Exception:
        pass


def _sync_chat_after_reply():
    """После ответа обновляет URL страницы и флаг primed текущего чата."""
    base = _chats_dir()
    cid = STATE.get("current_chat_id")
    if not base or not cid:
        return
    url = ""
    try:
        url = get_driver().current_url or ""
    except Exception:
        pass
    try:
        chat_store.touch_chat(base, cid, url=url, primed=bool(STATE.get("is_primed")))
    except Exception:
        pass


def site_mismatch_for_current():
    """Проверяет, что браузер сейчас на том же сайте, что и текущий чат.
    Возвращает None, если всё ок (или сравнивать не с чем), иначе dict
    с ожидаемым адресом — панель тогда спросит про переход."""
    rec = get_current_chat()
    if not rec:
        return None
    expected = rec.get("url") or ""
    if not expected:
        return None
    try:
        cur = get_driver().current_url or ""
    except Exception:
        return None
    if not cur or cur in ("about:blank", "data:,"):
        return None
    if sites.same_site(cur, expected):
        return None
    return {
        "expected_url": expected,
        "site": rec.get("site_name") or sites.site_name_for_url(expected),
        "current_url": cur,
    }


def _set_progress(info):
    """Живая трансляция: ai_parser присылает фазу/символы/хвост ответа."""
    data = {"active": True}
    data.update(info or {})
    STATE["progress"] = data


def _clear_progress():
    STATE["progress"] = {"active": False}


def _apply_session_context(data):
    """Обновляет project_root и user_data_dir из запроса панели.
    user_data_dir переключает хранение истории/снапшотов в user:// (вне
    проекта) и один раз переносит туда старую .agent_history из проекта."""
    if data.get("project_root"):
        STATE["project_root"] = data["project_root"]
    if data.get("addon_dir"):
        STATE["addon_dir"] = data["addon_dir"]
    udd = data.get("user_data_dir")
    if udd and udd != STATE.get("user_data_dir"):
        STATE["user_data_dir"] = udd
        history.set_storage_dir(udd)
        if history.migrate_from_project(STATE.get("project_root")):
            print("--> История изменений перенесена из проекта в:",
                  history.get_storage_dir(STATE.get("project_root")))
