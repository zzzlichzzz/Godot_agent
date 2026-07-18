# -*- coding: utf-8 -*-
"""Маршруты стартового экрана и чатов: список сайтов, список чатов,
создание нового чата на выбранном сайте, открытие сохранённого чата
(с переходом браузера на его страницу), переименование и удаление.
Вынесено из main.py в отдельный Blueprint.
"""
import time
from flask import Blueprint, request, jsonify

import chat_store
import sites
import server_state as S
import history_manager as history

chats_bp = Blueprint("chats", __name__)


def _navigate(driver, url):
    """Неблокирующая навигация браузера на URL.

    driver.get() у тяжёлого SPA (AI Studio) ждёт полной загрузки страницы
    и может упереться в таймаут HTTP-запроса от плагина — тогда
    браузер уже открыл страницу, а плагин так и не получил ответ и не открыл чат.
    Меняем адрес через JS: браузер начинает грузить страницу, а сервер сразу
    отвечает. Транскрипт диалога хранится локально, полная загрузка для ответа не нужна.
    """
    try:
        driver.switch_to.window(driver.window_handles[-1])
    except Exception:
        pass
    try:
        driver.execute_script("window.location.href = arguments[0];", url)
        return
    except Exception:
        pass
    # Фолбэк: обычная навигация с ограничением по времени, чтобы не зависнуть.
    try:
        driver.set_page_load_timeout(10)
    except Exception:
        pass
    try:
        driver.get(url)
    except Exception:
        pass


@chats_bp.route('/sites/list', methods=['POST'])
def sites_list():
    # Список доступных сайтов-нейросетей для vbox на стартовом экране.
    return jsonify({"sites": sites.list_sites()})


@chats_bp.route('/browser/status', methods=['POST'])
def browser_status():
    """Готова ли текущая страница браузера (панель показывает уведомление,
    когда сайт догрузился, чтобы не казалось, что агент завис)."""
    driver = S.get_driver()
    state = ""
    url = ""
    try:
        url = driver.current_url or ""
        state = driver.execute_script("return document.readyState") or ""
    except Exception as e:
        return jsonify({"ready": False, "state": "error", "url": url, "error": str(e)})
    return jsonify({"ready": state == "complete", "state": state, "url": url})


@chats_bp.route('/chats/list', methods=['POST'])
def chats_list():
    data = request.json or {}
    S._apply_session_context(data)
    base = S._chats_dir()
    if not base:
        return jsonify({"chats": [], "current_id": None})
    return jsonify({"chats": chat_store.list_chats(base),
                    "current_id": S.STATE.get("current_chat_id")})


@chats_bp.route('/chats/new', methods=['POST'])
def chats_new():
    data = request.json or {}
    S._apply_session_context(data)
    base = S._chats_dir()
    if not base:
        return jsonify({"error": "Нет user_data_dir (отправьте сообщение или Синхронизацию)."}), 400
    site = sites.get_site(data.get("site_id") or "aistudio") or sites.get_site("aistudio")
    target_url = site["new_chat_url"] if site else "https://aistudio.google.com/prompts/new_chat"
    driver = S.get_driver()
    try:
        _navigate(driver, target_url)
        time.sleep(1.5)
    except Exception as e:
        return jsonify({"error": "Не удалось открыть новую страницу: %s" % e}), 500
    url = ""
    try:
        url = driver.current_url or ""
    except Exception:
        pass
    rec = chat_store.create_chat(base, url=url, primed=False)
    if site:
        chat_store.update_chat(base, rec["id"], site_id=site["id"], site_name=site["name"])
        rec = chat_store.find_chat(base, rec["id"]) or rec
    S.STATE["current_chat_id"] = rec["id"]
    S.STATE["is_primed"] = False
    S._save_primed(S.STATE.get("project_root"), False)
    S.STATE["pending_action"] = None
    S.STATE["pending_batch"] = None
    S.STATE["stale_note"] = ""  # новый чат праймится свежим деревом — сводка не нужна
    print("--> Новый чат:", rec["id"], "на сайте", site["name"] if site else "?")
    return jsonify({"chats": chat_store.list_chats(base), "current_id": rec["id"],
                    "title": rec["title"], "site": site["name"] if site else ""})


@chats_bp.route('/chats/open', methods=['POST'])
def chats_open():
    data = request.json or {}
    S._apply_session_context(data)
    base = S._chats_dir()
    cid = (data.get("id") or "").strip()
    rec = chat_store.find_chat(base, cid) if base else None
    if rec is None:
        return jsonify({"error": "Чат не найден."}), 404
    if rec.get("url"):
        driver = S.get_driver()
        try:
            _navigate(driver, rec["url"])
        except Exception as e:
            return jsonify({"error": "Не удалось открыть страницу чата: %s" % e}), 500
    S.STATE["current_chat_id"] = cid
    S.STATE["is_primed"] = bool(rec.get("primed"))
    S._save_primed(S.STATE.get("project_root"), S.STATE["is_primed"])
    S.STATE["pending_action"] = None
    S.STATE["pending_batch"] = None
    prev_used = rec.get("last_used", 0)
    chat_store.touch_chat(base, cid)
    # Сводка «что изменилось в проекте, пока чат был неактивен» — уйдёт
    # модели вместе со СЛЕДУЮЩИМ сообщением пользователя. Защита от полотна —
    # внутри summarize_changes_since (лимит строк / короткий абзац).
    S.STATE["stale_note"] = ""
    _root = S.STATE.get("project_root")
    if _root:
        try:
            _note = history.summarize_changes_since(_root, prev_used, exclude_chat_id=cid)
            if _note:
                S.STATE["stale_note"] = _note
                print("--> Подготовлена сводка изменений проекта для чата (%d симв.)" % len(_note))
        except Exception:
            pass
    print("--> Открыт чат:", rec.get("title"), cid)
    return jsonify({"chats": chat_store.list_chats(base), "current_id": cid,
                    "title": rec.get("title"),
                    "site": rec.get("site_name", ""),
                    "transcript": rec.get("transcript", [])})


@chats_bp.route('/chats/rename', methods=['POST'])
def chats_rename():
    data = request.json or {}
    S._apply_session_context(data)
    base = S._chats_dir()
    cid = (data.get("id") or "").strip()
    title = (data.get("title") or "").strip()
    if not base or not cid or not title:
        return jsonify({"error": "Нужны id и title."}), 400
    chat_store.update_chat(base, cid, title=title, manual_title=True)
    return jsonify({"chats": chat_store.list_chats(base),
                    "current_id": S.STATE.get("current_chat_id")})


@chats_bp.route('/chats/delete', methods=['POST'])
def chats_delete():
    data = request.json or {}
    S._apply_session_context(data)
    base = S._chats_dir()
    cid = (data.get("id") or "").strip()
    if not base or not cid:
        return jsonify({"error": "Нужен id."}), 400
    chat_store.delete_chat(base, cid)
    if S.STATE.get("current_chat_id") == cid:
        S.STATE["current_chat_id"] = None
    return jsonify({"chats": chat_store.list_chats(base),
                    "current_id": S.STATE.get("current_chat_id")})
