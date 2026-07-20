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
from agent_prompts import PROMPT_HASH

chats_bp = Blueprint("chats", __name__)


def _busy_error():
    """Пока идёт обработка запроса, браузер занят парсером — навигация по
    чатам привела бы к вечной загрузке. Возвращаем понятную ошибку."""
    if (S.STATE.get("progress") or {}).get("active"):
        return jsonify({"error": "Агент сейчас обрабатывает запрос — браузер занят. "
                                 "Дождитесь ответа или нажмите «Стоп»."}), 409
    return None


def _navigate(driver, url):
    """Неблокирующая навигация браузера на URL.

    driver.get() у тяжёлого SPA (AI Studio) ждёт полной загрузки страницы
    и может упереться в таймаут HTTP-запроса от плагина — тогда
    браузер уже открыл страницу, а плагин так и не получил ответ и не открыл чат.
    Меняем адрес через JS: браузер начинает грузить страницу, а сервер сразу
    отвечает. Транскрипт диалога хранится локально, полная загрузка для ответа не нужна.
    """
    try:
        # Короткие таймауты: на мёртвой/удалённой странице команды браузеру
        # могут висеть до 300 с (дефолт Selenium) — отсюда «вечное» зависание.
        driver.set_page_load_timeout(20)
        driver.set_script_timeout(10)
    except Exception:
        pass
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


def _check_chat_page(driver, url, wait=6.0):
    """После перехода на страницу чата проверяем (не дольше wait секунд),
    что браузер остался на ней. Если чат удалён на сайте, сайт обычно
    перекидывает на главную — возвращаем текст предупреждения (или "").
    Главное: проверка ОГРАНИЧЕНА ПО ВРЕМЕНИ и никогда не виснет вечно."""
    deadline = time.time() + wait
    last_url = ""
    state = ""
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            last_url = driver.current_url or ""
            state = driver.execute_script("return document.readyState") or ""
        except Exception:
            continue  # страница ещё грузится — команды могут временно падать
        if state == "complete" and last_url:
            break
    if not last_url:
        return ("Браузер не ответил при открытии страницы чата — вкладка могла "
                "зависнуть. Если чат был удалён на сайте — удалите его и здесь.")

    def _path(u):
        return u.split("://", 1)[-1].split("?", 1)[0].split("#", 1)[0].rstrip("/")

    if _path(last_url) != _path(url):
        return ("Похоже, этот чат удалён на сайте: страница не открылась "
                "(браузер оказался на %s). История сообщений сохранена локально. "
                "Отправка сообщений сюда не сработает — удалите чат или создайте новый." % last_url)
    return ""


@chats_bp.route('/sites/list', methods=['POST'])
def sites_list():
    # Список доступных сайтов-нейросетей для vbox на стартовом экране.
    return jsonify({"sites": sites.list_sites()})


@chats_bp.route('/browser/status', methods=['POST'])
def browser_status():
    """Готова ли текущая страница браузера (панель показывает уведомление,
    когда сайт догрузился, чтобы не казалось, что агент завис)."""
    driver = S.get_driver()
    if driver is None:
        return jsonify({"ready": False, "state": "booting", "url": ""})
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
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH),
                    "current_id": S.STATE.get("current_chat_id")})


@chats_bp.route('/chats/new', methods=['POST'])
def chats_new():
    data = request.json or {}
    S._apply_session_context(data)
    busy = _busy_error()
    if busy:
        return busy
    base = S._chats_dir()
    if not base:
        return jsonify({"error": "Нет user_data_dir (отправьте сообщение или Синхронизацию)."}), 400
    site = sites.get_site(data.get("site_id") or "aistudio") or sites.get_site("aistudio")
    target_url = site["new_chat_url"] if site else "https://aistudio.google.com/prompts/new_chat"
    try:
        driver = S.wait_driver()
    except Exception as e:
        return jsonify({"error": str(e)}), 503
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
    # v48: первое сообщение нового чата — системное напоминание выбрать модель.
    chat_store.append_transcript(base, rec["id"], "system",
        "Не забудьте выбрать нейросеть (модель) на странице в браузере, прежде чем отправлять первое сообщение.")
    print("--> Новый чат:", rec["id"], "на сайте", site["name"] if site else "?")
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH), "current_id": rec["id"],
                    "title": rec["title"], "site": site["name"] if site else ""})


@chats_bp.route('/chats/open', methods=['POST'])
def chats_open():
    data = request.json or {}
    S._apply_session_context(data)
    busy = _busy_error()
    if busy:
        return busy
    base = S._chats_dir()
    cid = (data.get("id") or "").strip()
    rec = chat_store.find_chat(base, cid) if base else None
    if rec is None:
        return jsonify({"error": "Чат не найден."}), 404
    page_note = ""
    if rec.get("url"):
        try:
            driver = S.wait_driver()
        except Exception as e:
            return jsonify({"error": str(e)}), 503
        try:
            _navigate(driver, rec["url"])
        except Exception as e:
            return jsonify({"error": "Не удалось открыть страницу чата: %s" % e}), 500
        page_note = _check_chat_page(driver, rec["url"])
        if page_note:
            print("--> ВНИМАНИЕ:", page_note)
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
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH), "current_id": cid,
                    "title": rec.get("title"),
                    "site": rec.get("site_name", ""),
                    "warning": page_note,
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
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH),
                    "current_id": S.STATE.get("current_chat_id")})


@chats_bp.route('/chats/delete', methods=['POST'])
def chats_delete():
    data = request.json or {}
    S._apply_session_context(data)
    busy = _busy_error()
    if busy:
        return busy
    base = S._chats_dir()
    cid = (data.get("id") or "").strip()
    if not base or not cid:
        return jsonify({"error": "Нужен id."}), 400
    chat_store.delete_chat(base, cid)
    S.discard_action_note_for_chat(cid)  # v45: не копим отложенные заметки удалённых чатов
    if S.STATE.get("current_chat_id") == cid:
        S.STATE["current_chat_id"] = None
    return jsonify({"chats": chat_store.list_chats(base, PROMPT_HASH),
                    "current_id": S.STATE.get("current_chat_id")})
