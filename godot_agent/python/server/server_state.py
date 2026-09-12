# -*- coding: utf-8 -*-
"""Состояние сессии сервера + общие помощники.

Здесь живёт единое STATE, держатель драйвера браузера, привязка чатов,
флаг primed и живой прогресс. Вынесено из main.py, чтобы и основные
маршруты, и chat_routes.py работали с ОДНИМ состоянием.
"""
import os
import json as _json
import threading
import hmac
import time

import history_manager as history
import chat_store
import sites
import project_tools

# Глобальное состояние сессии
STATE = {
    "project_root": None,
    "pending_action": None,   # ожидающее подтверждения WRITE-действие
    "pending_refactor": None, # private prepared multi-file rename transaction
    "pending_scene_action": None, # private editor-side scene transaction
    "pending_project_settings_action": None, # private editor-side ProjectSettings transaction
    "pending_resource_action": None, # private editor-side resource transaction
    "pending_validation": None, # private Godot headless receipt for the pending write
    "pending_transaction": None, # private prepared atomic multi-file transaction
    "current_chat_id": None,  # активный чат (см. chat_store.py)
    "current_site_id": None,  # явный режим сайта, включая arena vs arena_battle
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
    "godot_executable": None,      # trusted editor executable path from OS.get_executable_path()
    "pending_log_report": None,  # подготовленный отчёт об ошибках запуска
    "editor_context": None,     # снимок только текущего хода для gather_context
    "runtime_status": None,
    "pending_runtime_request": None,
    "pending_runtime_check": None,
    "runtime_turn_id": 0,
    "runtime_inspections_this_turn": 0,
    "progress": {"active": False},
    "fs_snapshot": None,       # отпечаток файлов проекта (mtime+size) для обнаружения ВНЕШНИХ изменений
    "fs_snapshot_root": None,
    "file_cache": None,       # rel_path -> содержимое, которое уже видела модель (для точечных diff)  # корень проекта, для которого снят fs_snapshot,
    "content_parts": None,     # v86.26: накопитель частей многочастного create_file (path/chunks/parts_total/count)
    "battle_choice_summary": None,
    # Системный блок API-режима, собранный на текущий ход пользователя
    # ({"root": ..., "text": ...}). Внутри хода он обязан быть неизменным —
    # иначе не работает кэш промпта у провайдера и заново обходится проект.
    "api_system_cache": None,
    # Сколько СЕКУНД уже потрачено на паузы перед повторами в ТЕКУЩЕМ ходе
    # пользователя. Бюджет общий на весь ход, а не на один запрос, потому что
    # один ход — это несколько запросов к модели (самоисцеление, дочитывание
    # файлов, шаги плана), и у каждого своё расписание пауз. Считаем время, а
    # не число попыток: опасность — не «много повторов», а «редактор занят
    # часами», и время выражает это прямо. Побочно оно само расставляет
    # приоритеты: быстрые повторы после сбоя связи почти не тратят бюджет и
    # длинный план их переживает, а медленные паузы лимита съедают его сразу —
    # и правильно, раз четыре нарастающие паузы лимит не отпустили, следующий
    # запрос его тоже не отпустит. Сбрасывается в chat(); см.
    # main._retry_wait_left.
    "retry_wait_this_turn": 0.0,
}

# Драйвер браузера храним в держателе: он создаётся уже после импорта.
_holder = {"driver": None, "driver_error": None}

# v88.11: флаг «идёт обмен промпт->ответ» — на это время живой ввод
# (/chat/live_input) не трогает браузер, чтобы не мешать конвейеру отправки
# (вставка финального промпта, сверка v88.4, ожидание ответа).
_exchange = {"count": 0}
_exchange_lock = threading.Lock()
_runtime_request_lock = threading.RLock()


def claim_runtime_request(data):
    """Validate and reserve one result while holding the runtime-turn lock."""
    _runtime_request_lock.acquire()
    pending = STATE.get("pending_runtime_request")
    if not isinstance(pending, dict):
        _runtime_request_lock.release()
        return None, "missing"
    if str(data.get("request_id") or "") != str(pending.get("request_id") or ""):
        _runtime_request_lock.release()
        return None, "request"
    if not hmac.compare_digest(
            str(data.get("result_token") or ""), str(pending.get("result_token") or "")):
        _runtime_request_lock.release()
        return None, "token"
    if time.time() > float(pending.get("deadline") or 0):
        STATE["pending_runtime_request"] = None
        _runtime_request_lock.release()
        return None, "expired"
    if (int(data.get("session_id", -1)) != int(pending.get("session_id", -2))
            or str(data.get("run_id") or "") != str(pending.get("run_id") or "")):
        _runtime_request_lock.release()
        return None, "session"
    if (pending.get("chat_id") != STATE.get("current_chat_id")
            or int(pending.get("turn_id") or 0) != int(STATE.get("runtime_turn_id") or 0)):
        _runtime_request_lock.release()
        return None, "turn"
    return pending, None


def release_runtime_request(pending):
    """Consume a reserved request and release the runtime-turn lock."""
    try:
        current = STATE.get("pending_runtime_request")
        if (isinstance(current, dict) and isinstance(pending, dict)
                and current.get("request_id") == pending.get("request_id")):
            STATE["pending_runtime_request"] = None
    finally:
        _runtime_request_lock.release()


def reset_runtime_turn(status=None, increment=False):
    """Serialize chat/initialization changes against accepted runtime results."""
    with _runtime_request_lock:
        STATE["runtime_status"] = status
        STATE["pending_runtime_request"] = None
        STATE["pending_runtime_check"] = None
        if increment:
            STATE["runtime_turn_id"] = int(STATE.get("runtime_turn_id") or 0) + 1
        else:
            STATE["runtime_turn_id"] = 0
        STATE["runtime_inspections_this_turn"] = 0


def bind_runtime_check(data):
    """Bind one confirmed check to the new bridge-ready run."""
    with _runtime_request_lock:
        pending = STATE.get("pending_runtime_check")
        if not isinstance(pending, dict):
            return None, "missing"
        if str(data.get("request_id") or "") != pending.get("request_id"):
            return None, "request"
        if not hmac.compare_digest(str(data.get("result_token") or ""), pending.get("result_token") or ""):
            return None, "token"
        if time.time() > float(pending.get("deadline") or 0):
            STATE["pending_runtime_check"] = None
            return None, "expired"
        if pending.get("chat_id") != STATE.get("current_chat_id") or int(pending.get("turn_id") or 0) != int(STATE.get("runtime_turn_id") or 0):
            return None, "turn"
        session_id = int(data.get("session_id", -1))
        run_id = str(data.get("run_id") or "")
        if session_id < 0 or not run_id:
            return None, "session"
        supplied_status = data.get("runtime_status")
        if isinstance(supplied_status, dict):
            # The check starts a new game after the user turn, so the status
            # stored by /chat is necessarily stale. Keep only the protocol
            # allowlisted shape before using the freshly reported run.
            import runtime_debug
            STATE["runtime_status"] = runtime_debug.normalize_status(supplied_status)
        sessions = (STATE.get("runtime_status") or {}).get("sessions") or []
        matching = [item for item in sessions if isinstance(item, dict)
                    and int(item.get("session_id", -2)) == session_id
                    and str(item.get("run_id") or "") == run_id]
        if (len(matching) != 1 or not matching[0].get("active")
                or not matching[0].get("bridge_ready")
                or "run_check_v1" not in (matching[0].get("capabilities") or [])):
            return None, "session"
        if pending.get("state") == "bound":
            if (int(pending.get("session_id", -2)) == session_id
                    and str(pending.get("run_id") or "") == run_id):
                return pending, None
            return None, "state"
        if pending.get("state") != "awaiting_bind":
            return None, "state"
        pending["session_id"] = session_id
        pending["run_id"] = run_id
        pending["state"] = "bound"
        return pending, None


def claim_runtime_check(data, allow_unbound=False):
    _runtime_request_lock.acquire()
    pending = STATE.get("pending_runtime_check")
    if not isinstance(pending, dict):
        _runtime_request_lock.release()
        return None, "missing"
    if str(data.get("request_id") or "") != pending.get("request_id"):
        _runtime_request_lock.release()
        return None, "request"
    if not hmac.compare_digest(str(data.get("result_token") or ""), pending.get("result_token") or ""):
        _runtime_request_lock.release()
        return None, "token"
    if time.time() > float(pending.get("deadline") or 0):
        STATE["pending_runtime_check"] = None
        _runtime_request_lock.release()
        return None, "expired"
    if pending.get("state") != "bound" and not (allow_unbound and pending.get("state") == "awaiting_bind"):
        _runtime_request_lock.release()
        return None, "state"
    if (pending.get("state") == "bound"
            and (int(data.get("session_id", -1)) != int(pending.get("session_id", -2))
                 or str(data.get("run_id") or "") != pending.get("run_id"))):
        _runtime_request_lock.release()
        return None, "session"
    if pending.get("chat_id") != STATE.get("current_chat_id") or int(pending.get("turn_id") or 0) != int(STATE.get("runtime_turn_id") or 0):
        _runtime_request_lock.release()
        return None, "turn"
    return pending, None


def release_runtime_check(pending):
    try:
        current = STATE.get("pending_runtime_check")
        if isinstance(current, dict) and current.get("request_id") == pending.get("request_id"):
            STATE["pending_runtime_check"] = None
    finally:
        _runtime_request_lock.release()


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


# Ленивый запуск браузера. Раньше Chrome стартовал безусловно при запуске
# сервера, но в режиме работы по ключу API браузер не нужен вообще — это было
# бы лишнее окно, лишний профиль и лишний расход памяти. Теперь функцию
# запуска регистрирует main.py, а вызывается она при первом же обращении
# к wait_driver(), то есть только когда браузер действительно понадобился.
_boot = {"started": False, "fn": None, "lock": threading.Lock()}


def set_browser_booter(fn):
    """Регистрирует функцию запуска браузера (main.py)."""
    _boot["fn"] = fn


def browser_boot_started():
    return bool(_boot["started"])


def ensure_browser_booting():
    """Запускает браузер в фоне, если он ещё не запускался. Повторные вызовы
    ничего не делают — запуск строго один раз за жизнь процесса."""
    with _boot["lock"]:
        if _boot["started"] or _boot["fn"] is None:
            return
        _boot["started"] = True
        fn = _boot["fn"]
    print("--> Браузер понадобился — запускаю его в фоне.")
    threading.Thread(target=fn, name="browser-boot", daemon=True).start()


def wait_driver(timeout=90.0):
    """Браузер стартует В ФОНЕ и ТОЛЬКО ПО ТРЕБОВАНИЮ: HTTP-сервер поднимается
    сразу, а Chrome догоняет параллельно с первого обращения сюда.
    Возвращает driver или бросает RuntimeError с понятным текстом."""
    import time as _time
    ensure_browser_booting()
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


def chat_kind(rec):
    """Вид чата: "browser" (сайт в браузере) или "api" (провайдер по ключу).

    У всех уже существующих записей поля kind нет — они браузерные. Поэтому
    отсутствие поля означает "browser", и никакой миграции старых чатов не
    требуется.
    """
    return (rec or {}).get("kind") or "browser"


def current_chat_kind():
    return chat_kind(get_current_chat())


def current_chat_is_api():
    return current_chat_kind() == "api"


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
    # Arena /text becomes /c/<id>; the URL itself does not say Direct or
    # Battle. Reuse its saved chat record before host-based site detection.
    rec = chat_store.find_chat_by_url(base, url)
    if rec is not None:
        STATE["current_chat_id"] = rec["id"]
        STATE["current_site_id"] = rec.get("site_id")
        print("--> Восстановлен чат: %s (%s)" % (rec["title"], rec["id"]))
        return rec
    rec = chat_store.create_chat(base, url=url,
                                 title=chat_store.title_from_prompt(first_prompt),
                                 primed=bool(STATE.get("is_primed")))
    site = sites.detect_site(url)
    if site:
        chat_store.update_chat(base, rec["id"], site_id=site["id"], site_name=site["name"])
        rec = chat_store.find_chat(base, rec["id"]) or rec
    STATE["current_chat_id"] = rec["id"]
    STATE["current_site_id"] = rec.get("site_id")
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


def clear_pending_confirmations():
    """Discard confirmations that belong to the chat being left."""
    STATE["pending_action"] = None
    STATE["pending_refactor"] = None
    STATE["pending_scene_action"] = None
    STATE["pending_project_settings_action"] = None
    STATE["pending_resource_action"] = None
    STATE["pending_validation"] = None
    STATE["pending_transaction"] = None
    STATE["pending_batch"] = None
    STATE["pending_plan"] = None
    STATE["plan_parts"] = None
    STATE["content_parts"] = None
    with _runtime_request_lock:
        STATE["pending_runtime_request"] = None
        STATE["pending_runtime_check"] = None


def _sync_chat_after_reply():
    """После ответа обновляет URL страницы и флаг primed текущего чата."""
    base = _chats_dir()
    cid = STATE.get("current_chat_id")
    if not base or not cid:
        return
    rec = chat_store.find_chat(base, cid)
    if chat_kind(rec) == "api":
        # У чата по ключу нет страницы в браузере: адрес обновлять нечем, а
        # трогать драйвер незачем — в API-режиме он может быть вообще не
        # запущен.
        try:
            chat_store.touch_chat(base, cid, primed=bool(STATE.get("is_primed")))
        except Exception:
            pass
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
    if chat_kind(rec) == "api":
        # Чат по ключу не привязан к странице: сверять нечего, и обращаться
        # к драйверу нельзя — браузер в этом режиме может не запускаться.
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
    executable = str(data.get("godot_executable") or "").strip()
    if executable and os.path.isfile(executable):
        STATE["godot_executable"] = os.path.abspath(executable)
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
