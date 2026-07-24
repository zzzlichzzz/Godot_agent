# -*- coding: utf-8 -*-
"""Состояние сессии сервера + общие помощники.

Здесь живёт единое STATE, держатель драйвера браузера, привязка чатов,
флаг primed и живой прогресс. Вынесено из main.py, чтобы и основные
маршруты, и chat_routes.py работали с ОДНИМ состоянием.
"""
import os
import json as _json
import threading

import history_manager as history
import chat_store
import sites
import project_tools

# Глобальное состояние сессии
STATE = {
    "project_root": None,
    "pending_action": None,   # ожидающее подтверждения WRITE-действие
    "current_chat_id": None,  # активный чат (см. chat_store.py)
    "pending_batch": None,    # ожидающая подтверждений пачка файлов на чтение
    "pending_plan": None,     # ожидающий подтверждения/выполнения план (plan-режим, цепочка шагов)
    "is_primed": False,
    # v45: заметки о результате действия/плана (принято/откачено/отклонено) —
    # ЭТО НЕ строка, а словарь chat_id -> текст заметки. Раньше это была одна
    # общая строка на весь сервер, из-за чего откат/отказ, случившийся в одном
    # чате, мог "прилипнуть" к следующему сообщению ЛЮБОГО чата (в т.ч. только
    # что созданного нового) — модель получала чужой системный отчёт об откате.
    # Теперь заметка помечается chat_id того чата, где произошло действие, и
    # отдаётся только этому же чату; см. queue_action_note/pop_action_note_for_current.
    "action_notes": {},
    "user_data_dir": None,       # user:// папка проекта (логи игры, хранилище истории)
    "addon_dir": None,            # папка аддона на диске (для вшитого справочника API)
    "pending_log_report": None,  # подготовленный отчёт об ошибках запуска
    "progress": {"active": False},
    "fs_snapshot": None,       # отпечаток файлов проекта (mtime+size) для обнаружения ВНЕШНИХ изменений
    "fs_snapshot_root": None,
    "file_cache": None,       # rel_path -> содержимое, которое уже видела модель (для точечных diff)  # корень проекта, для которого снят fs_snapshot,
    "content_parts": None,     # v86.26: накопитель частей многочастного create_file (path/chunks/parts_total/count)
}

# Драйвер браузера храним в держателе: он создаётся уже после импорта.
_holder = {"driver": None, "driver_error": None}

# v88.11: флаг «идёт обмен промпт->ответ» — на это время живой ввод
# (/chat/live_input) не трогает браузер, чтобы не мешать конвейеру отправки
# (вставка финального промпта, сверка v88.4, ожидание ответа).
_exchange = {"count": 0}
_exchange_lock = threading.Lock()


def begin_exchange():
    with _exchange_lock:
        _exchange["count"] += 1


def end_exchange():
    with _exchange_lock:
        _exchange["count"] = max(0, _exchange["count"] - 1)


def exchange_active():
    with _exchange_lock:
        return _exchange["count"] > 0


def set_driver(d):
    _holder["driver"] = d


def get_driver():
    return _holder["driver"]


def set_driver_error(msg):
    _holder["driver_error"] = str(msg or "")


def wait_driver(timeout=90.0):
    """Браузер теперь стартует В ФОНЕ: HTTP-сервер поднимается сразу,
    а Chrome догоняет параллельно. Кому нужен браузер — ждёт его здесь.
    Возвращает driver или бросает RuntimeError с понятным текстом."""
    import time as _time
    deadline = _time.time() + timeout
    while _time.time() < deadline:
        if _holder["driver"] is not None:
            return _holder["driver"]
        if _holder["driver_error"]:
            raise RuntimeError("Браузер агента не запустился: %s" % _holder["driver_error"])
        _time.sleep(0.25)
    raise RuntimeError("Браузер агента ещё запускается — подождите пару секунд и повторите.")


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


def queue_action_note(note, chat_id=None):
    """v45: сохраняет системную заметку (откат/отказ/завершение шага
    плана и т.п.), строго привязанную к chat_id того чата, где произошло действие.
    По умолчанию — текущий STATE["current_chat_id"]. Без chat_id (никакого текущего
    чата ещё нет) заметка тихо пропадает — лучше потерять её, чем отдать не
    тому чату."""
    cid = chat_id or STATE.get("current_chat_id")
    if not cid:
        return
    STATE.setdefault("action_notes", {})[cid] = note


def pop_action_note_for_current():
    """v45: возвращает и убирает заметку ТОЛЬКО для текущего активного чата.
    Заметки других чатов при этом НЕ трогаются и остаются дожидаться своих
    собственных чатов (а не любого, кто первым отправит сообщение)."""
    cid = STATE.get("current_chat_id")
    notes = STATE.get("action_notes") or {}
    if not cid or cid not in notes:
        return ""
    return notes.pop(cid) or ""


def discard_action_note_for_chat(chat_id):
    """v45: убирает (без выдачи) отложенную заметку конкретного чата —
    используется при удалении чата, чтобы словарь заметок не рос бесконечно."""
    notes = STATE.get("action_notes") or {}
    notes.pop(chat_id, None)


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


# Флаг «остановить текущую обработку запроса» (кнопка «Стоп» в панели).
_cancel = {"requested": False}


def request_cancel():
    _cancel["requested"] = True


def clear_cancel():
    _cancel["requested"] = False


def cancel_requested():
    return _cancel["requested"]


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
        # v104.3: папка плагина не должна попадать в дерево/сводку/поиск/снапшот
        project_tools.exclude_agent_addon_dirs(data["addon_dir"])
    udd = data.get("user_data_dir")
    if udd and udd != STATE.get("user_data_dir"):
        STATE["user_data_dir"] = udd
        history.set_storage_dir(udd)
        if history.migrate_from_project(STATE.get("project_root")):
            print("--> История изменений перенесена из проекта в:",
                  history.get_storage_dir(STATE.get("project_root")))


def chat_already_primed(current_prompt_hash=None):
    """v104.2: True, если ТЕКУЩИЙ чат уже обучен мега-промптом этой версии.

    Источник истины — запись САМОГО чата (флаг primed + prompt_hash), а не
    глобальный флаг проекта: тот перетирается при создании/открытии других
    чатов и перезапусках сервера, из-за чего мега-промпт улетал повторно
    в чат, где он уже есть (репорт 23.07). Пустой prompt_hash у старых
    записей считаем совпадением — лучше не слать лишний раз, чем заспамить."""
    rec = get_current_chat()
    if not rec or not rec.get("primed"):
        return False
    return rec.get("prompt_hash") in (None, "", current_prompt_hash)


def mark_chat_prompt_version():
    """v48: текущий чат только что обучен актуальным мега-промптом —
    запоминаем версию промпта, чтобы панель могла показать «промпт устарел»
    для чатов, обученных более старой версией PRIMING_TEMPLATE."""
    try:
        from agent_prompts import PROMPT_HASH
        base = _chats_dir()
        chat = get_current_chat()
        if base and chat:
            chat_store.update_chat(base, chat.get("id"), prompt_hash=PROMPT_HASH)
    except Exception:
        pass
