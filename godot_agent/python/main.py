import _bootstrap  # noqa: F401  # v104-restructure: пути к parsers/, browser/, godot_tools/, server/
import os
import time
import traceback
from flask import Flask, request, jsonify

from browser_manager import setup_browser
from ai_parser import send_message_and_get_response
from project_tools import (
    build_project_tree,
    build_project_overview,
    describe_architecture,
    ensure_standard_architecture,
    snapshot_files,
    diff_snapshots,
    format_fs_changes,
    unified_diff_text,
    action_diff_preview,
    read_project_file,
    create_project_file,
    patch_project_file,
    move_project_file,
    MoveRecoveryError,
    copy_project_file,
    search_project_text,
    describe_scene,
    clean_dangling_autoloads,
    _resolve_safe_path,
)
import re as _re
import history_manager as history
import gd_lint
import gd_api_cache
import gd_api_check
import tscn_lint
import scene_deps
import minilich
import gd_functions
import librarian
import log_reader
import editor_context
import runtime_debug
import runtime_checks
import gather_context
import symbol_refactor
import file_refactor
import node_refactor
import scene_actions
import project_settings_actions
import resource_actions
import transaction_actions
import high_level_actions
import godot_headless_validation
import chat_store
import dashboard
import json as _json
dashboard.install()  # v80: zerkalim konsol servera v zhurnal dlya /dashboard
from agent_prompts import (
    PRIMING_TEMPLATE,
    CODE_EXTS,
    PRIME_TREE_MAX_ENTRIES,
    PRIME_COMPACT_THRESHOLD,
    MAX_BATCH_FILES,
    PER_FILE_CHAR_LIMIT,
    TOTAL_CHAR_BUDGET,
    MAX_ACTION_FIX_RETRIES,
    MAX_PLAN_STEPS,
    MAX_PLAN_TOTAL_STEPS,
    MAX_PLAN_PARTS,
    MAX_CONTENT_PARTS,
    API_MAX_TOKENS,
)

# шаги plan-режима ограничены теми же write-действиями, что и одиночные действия,
# без copy_file (оно применяется автоматически и не требует отдельного подтверждения)
# и без read_file/search_project/list_files/list_scene (они не меняют диск и им нечего откатывать).
PLAN_ALLOWED_ACTIONS = {"create_file", "patch_file", "move_file"}

# Защита аддонов: модель не должна сама лезть в res://addons/... (читать,
# создавать, патчить, перемещать, копировать) — только когда пользователь ЯВНО
# попросил об этом в своём последнем сообщении (см. _ADDON_INTENT_RE / STATE["addon_intent"]).
# Иначе модель регулярно предлагала действия над чужими аддонами "на автомате",
# и пользователю приходилось отклонять их вручную каждый раз.
_ADDON_INTENT_RE = _re.compile(r"\b(\u0430\u0434\u0434\u043e\u043d|addon|\u0430\u0434\u0434\u043e\u043d\u044b|addons)\b", _re.IGNORECASE)


def _is_addon_path(path):
    """True, если путь res://... указывает внутрь папки addons/ проекта."""
    if not path:
        return False
    from project_tools import is_addon_path
    return is_addon_path(path, STATE.get("project_root"))


def _is_project_settings_path(path):
    p = str(path or "").replace("\\", "/").strip().lower()
    return p in ("project.godot", "res://project.godot")


def _is_text_scene_path(path):
    return isinstance(path, str) and path.replace("\\", "/").lower().endswith(".tscn")


def _addon_blocked_message(path):
    return (
        "Путь %s находится в папке аддона (res://addons/...). Правки аддонов разрешены ТОЛЬКО "
        "когда пользователь явно попросил об этом в своём сообщении (словами \u00abаддон\u00bb/\u00abaddon\u00bb). "
        "Если это действительно нужно — спроси пользователя напрямую, прежде чем предлагать действие "
        "над файлами аддона; не запрашивай и не изменяй файлы аддона по своей инициативе." % path
    )
import live_input
import rate_limit  # v104.12: детект 429/лимитов + спящий режим
import server_state
from server_state import (
    STATE, get_driver, set_driver, set_driver_error, claim_runtime_request,
    reset_runtime_turn, bind_runtime_check, claim_runtime_check,
    _load_primed, _save_primed,
    _apply_session_context, _ensure_current_chat, _remember,
    _sync_chat_after_reply, _set_progress, _clear_progress,
)
import sites

# PyInstaller кладёт в exe только СТАТИЧЕСКИ импортированные модули.
# Парсеры сайтов подгружаются динамически (sites.get_parser_module), поэтому
# перечисляем их здесь явно — иначе их не окажется в сборке и DeepSeek молча
# обслуживался бы парсером AI Studio (баг «текст вводится, но не отправляется»).
import parser_base      # noqa: F401
import ai_parser        # noqa: F401
import deepseek_parser  # noqa: F401
import kimi_parser      # noqa: F401
import arena_parser     # noqa: F401
import answer_judge     # noqa: F401

# Бэкенды отправки: браузер (обёртка над парсерами) и работа по ключу API.
# Выбор между ними — в _current_backend(); ниже этой функции main.py не знает,
# с чем разговаривает.
import browser_backend
import api_backend
import api_history      # noqa: F401  (нужен /chats/delete: убрать историю чата)
import api_keys         # noqa: F401  (статические импорты для PyInstaller)
import providers        # noqa: F401

from chat_routes import chats_bp
import server_auth

app = Flask(__name__)
app.register_blueprint(chats_bp)
app.teardown_request(server_state.clear_turn_chat)
app.teardown_request(server_state.clear_request_activity)

# Bound and authenticate request bodies before any stateful admission hook.
server_auth.install(app, jsonify, body_limits={
    "/init": 128 * 1024,
    "/chat/runtime_inspect/result": runtime_debug.MAX_HTTP_BODY_BYTES,
    "/chat/runtime_check/result": runtime_checks.MAX_HTTP_BODY_BYTES,
})

_CHAT_CONTINUATION_PATHS = {
    "/chat/confirm_action", "/chat/editor_action/result",
    "/chat/runtime_inspect/result", "/chat/runtime_check/bind",
    "/chat/runtime_check/result",
    "/chat/rollback/preview", "/chat/rollback",
    "/chat/plan/step", "/chat/plan/stop",
    "/chat/plan/rollback_chain", "/project/send_log_errors",
}


@app.before_request
def _admit_chat_continuation():
    """Serialize stateful continuations with user turns and navigation."""
    if request.path not in _CHAT_CONTINUATION_PATHS:
        return None
    # Continuations are not fresh user turns: keep any pending cancel so
    # «Стоп» stays effective across plan steps / confirmations / results.
    if server_state.try_begin_turn_exchange(reset_cancel=False):
        return None
    if request.path in ("/chat/runtime_inspect/result", "/chat/runtime_check/result"):
        return jsonify({"error": "Runtime result processing is busy; retry this result.",
                        "code": "busy", "retryable": True}), 503, {"Retry-After": "1"}
    return jsonify({"error": "Агент уже обрабатывает другой запрос или переключает чат.",
                    "code": "busy"}), 409
_EDITOR_ACTION_RESULTS = {}
_RUNTIME_RESULTS = {}
_RUNTIME_RESULT_TTL = 300.0
_RUNTIME_RESULT_LIMIT = 32


def _current_parser():
    """Модуль-парсер по сайту ТЕКУЩЕГО чата (aistudio -> ai_parser,
    deepseek -> deepseek_parser, ...). Если чат не помнит сайт (старые чаты) —
    определяем по адресу открытой страницы браузера."""
    site_id = None
    try:
        base = server_state._chats_dir()
        cid = server_state.turn_chat_id()
        if base and cid:
            rec = chat_store.find_chat(base, cid) or {}
            site_id = rec.get("site_id")
    except Exception:
        site_id = None
    url = None
    if not site_id:
        try:
            d = get_driver()
            if d is not None:
                url = d.current_url or ""
        except Exception:
            url = None
    return sites.get_parser_module(site_id, url)


def _api_system_text():
    """Системный блок для чата по ключу.

    По API модель не помнит ничего, поэтому мега-промпт уходит СИСТЕМНЫМ
    сообщением в КАЖДОМ запросе — в отличие от браузерного режима, где он
    отправляется один раз за чат и дальше живёт в переписке на сайте.
    Собирает его main.py, потому что только здесь есть дерево проекта,
    архитектура и версия движка; бэкенд лишь вызывает эту функцию.

    РЕЗУЛЬТАТ КЭШИРУЕТСЯ НА ОДИН ХОД ПОЛЬЗОВАТЕЛЯ, и это принципиально, а не
    ради скорости:

    1. _build_priming_context обходит весь проект (build_project_overview) и
       вызывает _refresh_fs_snapshot. Один ход пользователя — это несколько
       запросов к модели (самоисцеление, дочитывание файлов, шаги плана), и
       без кэша каждый из них заново обходил бы файловую систему и СБРАСЫВАЛ
       отпечаток, по которому определяются правки пользователя руками.
    2. Кэш промпта у провайдеров работает только на НЕИЗМЕННОМ префиксе. Если
       системный блок пересобирается на каждый запрос, любое отличие (а дерево
       меняется после create_file) обнуляет кэш и делает мега-промпт полностью
       платным каждый раз.

    Сбрасывается в начале каждого сообщения пользователя (см. chat()), чтобы
    свежее дерево проекта попадало в следующий ход.
    """
    root = STATE.get("project_root")
    cached = STATE.get("api_system_cache")
    if isinstance(cached, dict) and cached.get("root") == root and cached.get("text"):
        return cached["text"]
    text = _build_priming_context(root)
    STATE["api_system_cache"] = {"root": root, "text": text}
    return text


def _drop_api_system_cache():
    """Забыть системный блок: следующий запрос соберёт его заново со свежим
    деревом проекта."""
    STATE["api_system_cache"] = None


# Сколько ВРЕМЕНИ агент вправе провести в паузах перед повторами за один ход
# пользователя, секунд. Расписание пауз ограничивает один запрос, но не ход:
# _reply вызывается заново на каждое самоисцеление, дочитывание файла и шаг
# плана, и счётчик попыток у каждого свой. У флапающего провайдера план из
# десяти шагов давал 10 x 510 с — больше часа заблокированного редактора, ни
# разу не нарушив правило «не больше четырёх пауз».
#
# ПОЧЕМУ ВРЕМЯ, А НЕ ЧИСЛО ПОПЫТОК. Опасность — не «много повторов», а «редактор
# занят часами»; время выражает это прямо, а число попыток — только через
# расписание, которых теперь два. Побочно время само расставляет приоритеты:
# быстрые повторы после обрыва связи (около минуты на все попытки) почти не
# тратят бюджет, и длинный план их спокойно переживает, а медленные паузы лимита
# съедают его за один запрос — и это правильно, потому что если лимит не
# отпустили четыре нарастающие паузы, то не отпустит и следующий запрос.
#
# Десять минут: столько ожидания на одной задаче человек ещё может себе
# позволить, не считая редактор зависшим.
MAX_RETRY_WAIT_PER_TURN = 600.0


def _reset_retry_budget():
    """Новый ход пользователя — новый бюджет ожидания повторов."""
    STATE["retry_wait_this_turn"] = 0.0


def _retry_wait_left():
    """Сколько секунд ожидания ещё разрешено в этом ходе."""
    return MAX_RETRY_WAIT_PER_TURN - float(STATE.get("retry_wait_this_turn") or 0.0)


def _current_backend():
    """Чем отправляем запрос: браузером или напрямую по ключу API.

    Единственная точка выбора. Ниже неё main.py не знает, с чем работает:
    оба бэкенда отдают одинаковый словарь ответа и умеют сообщить про лимит
    запросов. Записи чатов без поля kind (все существующие) — браузерные,
    поэтому миграция не нужна.
    """
    rec = server_state.get_current_chat() or {}
    if (rec.get("kind") or "browser") == "api":
        return api_backend.ApiBackend(
            rec, server_state._chats_dir(),
            system_text_provider=_api_system_text,
            max_tokens=API_MAX_TOKENS)
    return browser_backend.BrowserBackend(_current_parser())


def _giveup_text(kind, reason, retry_after, backend_text):
    """Что сказать пользователю, когда повторы кончились.

    Диагнозы разные, и советы к ним разные. При лимите ждать бесполезно —
    надо менять модель или приходить позже. При сбое сервиса или связи
    пользователю нужен ИСХОДНЫЙ текст от бэкенда: там названы и провайдер, и
    конкретная причина (обрыв потока, отказ прокси, HTTP 502), и туда же
    бэкенд дописал недополученную часть ответа. Подменять это общей фразой
    про лимит запросов, как было раньше, значит выбросить всю диагностику.
    """
    if kind == rate_limit.KIND_OUTAGE:
        return (backend_text or u"").rstrip() + (
            u"\n[color=#c08040]— повторил запрос %d раз(а), сбой не прошёл. "
            u"Проверьте связь и состояние сервиса, затем повторите —[/color]\n"
            % len(rate_limit.schedule_for(kind)))
    if retry_after:
        # Провайдер назвал срок, который мы ждать не готовы: держать
        # редактор заблокированным полчаса-час нельзя.
        return (u"[Лимит запросов]: сервис просит подождать %d с (%s). "
                u"Это слишком долго для ожидания в редакторе — "
                u"попробуйте позже или выберите другую модель."
                % (int(retry_after), reason))
    return (u"[Лимит запросов]: сайт ограничивает запросы (%s). "
            u"Подождите несколько минут и повторите запрос." % reason)


def _reply(prompt):
    """v104.12: обёртка над _reply_once — повтор запроса при лимитах и сбоях.

    Признаки повтора: HTTP 429/5xx на чат-эндпоинте (сетевой монитор в
    браузерном режиме, точный статус ответа — по ключу), метка
    rate_limit.TRANSPORT при обрыве связи (только по ключу) или короткий
    ответ-баннер («Высокая нагрузка», too many requests — см.
    rate_limit.MARKERS). Реакция: нарастающие паузы с повтором ТОГО ЖЕ
    запроса; пауза прерывается кнопкой «Стоп». Если не отпустило — честная
    остановка с сообщением в панель.

    РАСПИСАНИЕ ЗАВИСИТ ОТ ВИДА СБОЯ, И ТОЛЬКО ПО КЛЮЧУ. Лимит отпускает
    минутами, перегрузка шлюза и обрыв соединения — секундами, и ждать по
    полминуты на каждом сетевом чихе незачем. Браузерный режим сознательно
    оставлен на прежнем медленном расписании при ЛЮБОМ статусе: за 5xx там
    стоит не шлюз, а сам сайт бесплатного чата, и частые повторы к нему —
    прямой путь к настоящей блокировке аккаунта.
    """
    attempt = 0
    while True:
        text, action = _reply_once(prompt)
        if server_state.cancel_requested():
            raise parser_base.ParserCancelled("остановлено пользователем")
        backend = _current_backend()
        try:
            net_status = backend.pop_rate_limit_status()
        except Exception:
            net_status = None
        try:
            # Сколько просил подождать сам сервис (Retry-After). У браузерных
            # сайтов всегда None — там ориентир только наше расписание.
            retry_after = backend.pop_retry_after()
        except Exception:
            retry_after = None
        reason = rate_limit.reason_from_status(net_status)
        kind = rate_limit.kind_from_status(net_status)
        if reason is None and backend.kind != "api":
            # Поиск маркеров лимита ПО ТЕКСТУ ответа нужен только браузерному
            # режиму: там о лимите часто сообщает баннер на странице, а не
            # статус запроса. По API статус известен точно, и угадывание по
            # тексту может только навредить — например, собственное сообщение
            # «[Суточный лимит]: … (Rate limit exceeded)» содержит маркер
            # «rate limit», и агент уходил бы спать там, где мы намеренно
            # решили не спать (до сброса суточной квоты — часы).
            reason = rate_limit.reason_from_text(text, action)
            kind = rate_limit.KIND_LIMIT if reason else None
        if backend.kind != "api":
            # Быстрое расписание — только для работы по ключу (см. докстринг).
            kind = rate_limit.KIND_LIMIT
        if not reason:
            return text, action
        wait_s = rate_limit.sleep_seconds(attempt, retry_after, kind=kind)
        if wait_s is None:
            print("<-- [повтор] не помогло после %d пауз (%s) — "
                  "останавливаюсь честно." % (attempt, kind))
            return _giveup_text(kind, reason, retry_after, text), None
        if wait_s > _retry_wait_left():
            # Бюджет хода кончился. Останавливаемся ДО паузы, а не после:
            # ждать, чтобы потом всё равно сдаться, — чистая потеря времени.
            print("<-- [повтор] бюджет ожидания хода исчерпан (%.0f с из %.0f) "
                  "— останавливаюсь честно."
                  % (float(STATE.get("retry_wait_this_turn") or 0.0),
                     MAX_RETRY_WAIT_PER_TURN))
            return (text or u"").rstrip() + (
                u"\n[color=#c08040]— на этот ход уже ушло %d мин ожидания "
                u"из-за сбоев и лимитов, дальше не повторяю, чтобы не держать "
                u"редактор занятым. Повторите запрос вручную —[/color]\n"
                % int(round(float(STATE.get("retry_wait_this_turn") or 0.0) / 60.0))), None
        attempt += 1
        STATE["retry_wait_this_turn"] = (
            float(STATE.get("retry_wait_this_turn") or 0.0) + wait_s)
        print("--> [повтор] %s — пауза %d с (попытка %d/%d%s, вид: %s)"
              % (reason, wait_s, attempt, len(rate_limit.schedule_for(kind)),
                 ", по Retry-After" if retry_after else "", kind))
        # Фаза называет причину: раньше здесь всегда было написано «лимит
        # запросов», и на обрыве связи это была прямая ложь. Номер попытки —
        # чтобы замерший редактор отличался от работающего повтора.
        _set_progress({"phase": u"%s — повтор %d/%d через %d с"
                                % (u"лимит запросов"
                                   if kind == rate_limit.KIND_LIMIT
                                   else u"сбой сервиса",
                                   attempt, len(rate_limit.schedule_for(kind)),
                                   wait_s)})
        t_end = time.time() + wait_s
        try:
            while time.time() < t_end:
                if server_state.cancel_requested():
                    print("<-- [повтор] пауза прервана кнопкой «Стоп».")
                    raise parser_base.ParserCancelled("остановлено пользователем")
                time.sleep(0.5)
        finally:
            _clear_progress()


def _reply_once(prompt):
    """Один запрос-ответ к модели, без какой-либо логики восстановления."""
    if server_state.cancel_requested():
        return "[Остановлено] Запрос прерван кнопкой «Стоп».", None
    # v88.11: на время обмена «промпт->ответ» живой ввод (/chat/live_input)
    # не трогает браузер — конвейер сам вставит и сверит финальный промпт.
    server_state.begin_exchange()
    _set_progress({"phase": "отправляю запрос"})
    try:
        # v54: адрес текущего чата — чтобы печатать в ЕГО вкладку, а не в первую
        # попавшуюся вкладку сайта (у пользователя могла быть открыта вкладка старого чата).
        _chat_rec = server_state.get_current_chat() or {}
        result = _current_backend().send(
            prompt, progress_cb=_set_progress,
            cancel_cb=server_state.cancel_requested,
            prefer_url=_chat_rec.get("url") or None)
    except parser_base.ParserCancelled:
        server_state.request_cancel()
        print("<-- Запрос остановлен пользователем.")
        return "[Остановлено] Запрос прерван кнопкой «Стоп».", None
    finally:
        _clear_progress()
        server_state.end_exchange()
    if server_state.cancel_requested():
        return "[Остановлено] Запрос прерван кнопкой «Стоп».", None
    if isinstance(result, dict):
        text, action = result.get("text") or "", result.get("action")
        choice = result.get("battle_choice")
        if isinstance(choice, dict):
            STATE["battle_choice_summary"] = choice
    else:
        text, action = result or "", None
    act_name = action.get("action") if isinstance(action, dict) else "нет"
    print(f"<-- Ответ модели: {len(text)} симв., действие: {act_name}")
    return text, action


def _describe_action(action):
    if not action:
        return None
    act = action.get("action")
    path = action.get("path", "")
    if act == "create_file": return f"Агент хочет создать файл: {path}"
    if act == "patch_file": return f"Агент хочет изменить код в: {path}"
    if act == "move_file": return f"Агент хочет переместить {path} в {action.get('dest', '')}"
    if act == "copy_file": return "Агент копирует файлы внутри проекта (адаптация)"
    if act == "search_project": return "Агент хочет выполнить поиск по всем файлам проекта: «%s»" % action.get("query", "")
    if act == "list_files":
        return "Агент хочет получить свежее дерево файлов проекта" + ((" (папка %s)" % action.get("dir")) if action.get("dir") else "")
    if act == "list_scene": return f"Агент хочет посмотреть структуру сцены: {path}"
    if act == "gather_context":
        symbols = action.get("symbols") if isinstance(action.get("symbols"), list) else []
        details = []
        if action.get("query"):
            details.append("запрос «%s»" % str(action.get("query"))[:120])
        if symbols:
            details.append("символы: " + ", ".join(str(x) for x in symbols[:4]))
        return "Агент хочет одним проходом собрать контекст проекта" + ((": " + "; ".join(details)) if details else "")
    if act == "inspect_runtime":
        sections = action.get("sections") or []
        selectors = action.get("properties") or []
        property_count = sum(len(item.get("names") or []) for item in selectors if isinstance(item, dict))
        return "Агент хочет прочитать состояние запущенной игры: %s (%d свойств)" % (
            ", ".join(str(item) for item in sections), property_count)
    if act == "run_check":
        return "Агент хочет локально проверить сцену %s (%d шагов)" % (
            action.get("scene", ""), len(action.get("steps") or []))
    if act == "rename_symbol":
        return "Агент хочет безопасно переименовать %s в %s (%d файл(ов), %d ссылок)" % (
            action.get("old_name", ""), action.get("new_name", ""),
            int(action.get("file_count") or 0), int(action.get("reference_count") or 0))
    if act == "rename_file":
        return "Агент хочет безопасно переименовать файл %s в %s (%d обновлений ссылок)" % (
            action.get("path", ""), action.get("dest", ""), int(action.get("reference_count") or 0))
    if act == "rename_node":
        return "Агент хочет безопасно переименовать узел %s в %s в сцене %s (%d обновлений)" % (
            action.get("node_path") or action.get("node", ""),
            action.get("new_name", ""),
            action.get("scene", ""),
            int(action.get("reference_count") or 0))
    if act == "reparent_node":
        return "Агент хочет переместить узел %s в %s в сцене %s (%d обновлений)" % (
            action.get("node_path") or action.get("node", ""),
            action.get("new_parent", ""),
            action.get("scene", ""),
            int(action.get("reference_count") or 0))
    if act == "delete_node":
        return "Агент хочет безопасно удалить узел %s из сцены %s (%d обновлений)" % (
            action.get("node_path") or action.get("node", ""),
            action.get("scene", ""),
            int(action.get("reference_count") or 0))
    if act in ("edit_scene", "create_scene"):
        verb = "создать" if act == "create_scene" else "структурно изменить"
        return "Агент хочет %s сцену %s (%d операций)" % (
            verb, action.get("scene", ""), len(action.get("operations") or []))
    if act == "edit_project_settings":
        return "Агент хочет изменить настройки проекта через API Godot (%d операций)" % len(
            action.get("operations") or [])
    if act == "edit_resource":
        return "Агент хочет структурно изменить ресурс %s (%d операций)" % (
            action.get("resource", ""), len(action.get("operations") or []))
    if act == "transaction":
        return "Агент хочет атомарно изменить %d файл(ов) (%d операций)" % (
            int(action.get("file_count") or 0), int(action.get("operation_count") or 0))
    if act == "plan":
        total = action.get("total", len(action.get("steps") or []))
        desc = action.get("description", "")
        return "Агент хочет выполнить план из %d шаг(ов): %s" % (total, desc)
    if act == "parse_error": return "⚠ Агент прислал поврежённый JSON действия — самоисцеление (включая точечное восстановление шагов плана, если это был план) не помогло — действие пропущено."
    return f"Агент запросил неизвестное действие: {act}"


def _validate_plan_steps(steps, max_steps=None):
    """Валидация списка шагов action=plan ДО показа плана пользователю.
    Возвращает (ok, error_message)."""
    limit = max_steps if max_steps is not None else MAX_PLAN_STEPS
    if not isinstance(steps, list) or not steps:
        return False, "План должен содержать непустой список 'steps'."
    if len(steps) > limit:
        return False, (
            "в плане %d шаг(ов) — максимум %d. Раздели шаги на несколько сообщений через \"continues\": true (см. формат plan) или разбей механику на несколько меньших планов."
            % (len(steps), limit)
        )
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            return False, "шаг %d плана не является объектом действия." % (i + 1)
        act = step.get("action")
        if act not in PLAN_ALLOWED_ACTIONS:
            return False, (
                "шаг %d имеет недопустимое действие '%s' (разрешены только %s)."
                % (i + 1, act, ", ".join(sorted(PLAN_ALLOWED_ACTIONS)))
            )
        if not step.get("path"):
            return False, "шаг %d (%s) не содержит 'path'." % (i + 1, act)
        if _is_project_settings_path(step.get("path")) or _is_project_settings_path(step.get("dest")):
            return False, "шаг %d пытается править project.godot как текст. Используй edit_project_settings." % (i + 1)
        if (not STATE.get("addon_intent")) and (_is_addon_path(step.get("path")) or _is_addon_path(step.get("dest"))):
            return False, (
                "шаг %d трогает файл аддона (res://addons/...), а пользователь это явно не запрашивал. "
                "Не включай аддоны в план, если пользователь явно не попросил изменить аддон." % (i + 1)
            )
        if _is_text_scene_path(step.get("path")) or _is_text_scene_path(step.get("dest")):
            return False, "шаг %d пишет .tscn как текст. Используй create_scene/edit_scene." % (i + 1)
        if act == "create_file" and not isinstance(step.get("content"), str):
            return False, "шаг %d (create_file) не содержит текстового 'content'." % (i + 1)
        if act == "patch_file" and (not step.get("search") or not isinstance(step.get("replace"), str)):
            return False, "шаг %d (patch_file) должен содержать непустой 'search' и текстовый 'replace'." % (i + 1)
        if act == "move_file" and not step.get("dest"):
            return False, "шаг %d (move_file) не содержит 'dest'." % (i + 1)
    return True, None


def _plan_part_add(action):
    """Принимает ЧАСТЬ многочастного плана (action=plan с \"continues\": true):
    у модели может не хватать выходного лимита токенов на все шаги за один
    ответ — шаги копятся в STATE[\"plan_parts\"], пока не придёт последняя часть
    (без continues). Возвращает (ok, followup_для_модели); при ошибке
    накопленное сбрасывается."""
    steps = action.get("steps")
    ok, err = _validate_plan_steps(steps, max_steps=MAX_PLAN_STEPS)
    if not ok:
        STATE["plan_parts"] = None
        return False, ("[Система]: часть плана отклонена: %s Накопленные части сброшены — "
                       "пришли план заново (можно частями через \"continues\": true)." % err)
    parts = STATE.get("plan_parts") or {"steps": [], "description": "", "count": 0}
    if parts["count"] >= MAX_PLAN_PARTS - 1:
        STATE["plan_parts"] = None
        return False, ("[Система]: превышен лимит частей плана (максимум %d, включая последнюю). "
                       "Накопленные части сброшены — разбей механику на несколько планов поменьше." % MAX_PLAN_PARTS)
    if len(parts["steps"]) + len(steps) > MAX_PLAN_TOTAL_STEPS:
        STATE["plan_parts"] = None
        return False, ("[Система]: суммарно получается больше %d шагов — слишком много для одного плана. "
                       "Накопленные части сброшены — разбей механику на несколько планов поменьше." % MAX_PLAN_TOTAL_STEPS)
    parts["steps"].extend(steps)
    parts["count"] += 1
    if not parts["description"]:
        parts["description"] = action.get("description", "")
    STATE["plan_parts"] = parts
    print(f"--> Принята часть {parts['count']} многочастного плана: +{len(steps)} шаг(ов), всего {len(parts['steps'])}.")
    return True, ("[Система]: часть %d плана принята (+%d шаг(ов), всего накоплено %d). "
                  "Пришли СЛЕДУЮЩУЮ часть шагов одним блоком agent_action (action=plan): "
                  "с \"continues\": true, если после неё будут ещё шаги, или БЕЗ \"continues\", "
                  "если это последняя часть. Уже присланные шаги НЕ повторяй. "
                  "Осталось запаса: %d шаг(ов)."
                  % (parts["count"], len(steps), len(parts["steps"]),
                     MAX_PLAN_TOTAL_STEPS - len(parts["steps"])))


def _plan_collect_final(action):
    """Последняя часть многочастного плана (или обычный одночастный план):
    склеивает накопленные части (если были) с шагами из текущего action.
    Возвращает (steps, description) и очищает накопитель."""
    steps = list(action.get("steps") or [])
    description = action.get("description", "")
    parts = STATE.get("plan_parts")
    if parts:
        steps = list(parts["steps"]) + steps
        description = parts.get("description") or description
        STATE["plan_parts"] = None
        print(f"--> Многочастный план склеен: {len(steps)} шаг(ов) из {parts['count'] + 1} частей.")
    return steps, description


# v86.26: многочастная передача большого content для create_file (та же идея, что и
# у многочастного plan выше: модели может не хватить выходного лимита токенов
# на весь файл целиком — содержимое копится в STATE["content_parts"], пока не придёт
# последняя часть (без continues).
def _content_part_add(action):
    """Принимает часть многочастной передачи content (action=create_file с
    \"continues\": true, поля content_part/content_parts_total). Возвращает
    (ok, followup_для_модели); при ошибке накопленное сбрасывается."""
    if action.get("action") != "create_file":
        STATE["content_parts"] = None
        return False, ("[Система]: многочастная передача (\"continues\": true) поддерживается "
                       "только для create_file. Пришли файл заново одним действием или частями "
                       "create_file.")
    path = action.get("path")
    chunk = action.get("content")
    if not path or not isinstance(chunk, str):
        STATE["content_parts"] = None
        return False, ("[Система]: часть файла отклонена: нужны непустой 'path' и текстовый "
                       "'content' (саму часть, можно через content_ref). Накопленное сброшено — "
                       "пришли заново с первой части.")
    try:
        part_no = int(action.get("content_part"))
        parts_total = int(action.get("content_parts_total"))
    except (TypeError, ValueError):
        STATE["content_parts"] = None
        return False, ("[Система]: часть файла отклонена: нужны числовые 'content_part' и "
                       "'content_parts_total'. Накопленное сброшено — пришли заново с первой части.")
    parts = STATE.get("content_parts")
    if parts and parts.get("path") != path:
        parts = None  # части для другого файла — считаем, что начинается новая передача
    if not parts:
        if part_no != 1:
            STATE["content_parts"] = None
            return False, ("[Система]: часть файла отклонена: первая часть должна иметь "
                           "\"content_part\": 1. Пришли заново с первой части.")
        if parts_total < 2 or parts_total > MAX_CONTENT_PARTS:
            STATE["content_parts"] = None
            return False, ("[Система]: часть файла отклонена: 'content_parts_total' должен быть "
                           "от 2 до %d. Если файл столько не весит — пришли его ОДНИМ действием, "
                           "без continues." % MAX_CONTENT_PARTS)
        parts = {"path": path, "chunks": [], "parts_total": parts_total, "count": 0}
    if part_no != parts["count"] + 1:
        STATE["content_parts"] = None
        return False, ("[Система]: часть файла отклонена: ожидалась часть %d, а пришла %d. "
                       "Накопленное сброшено — пришли заново с первой части." % (parts["count"] + 1, part_no))
    if parts_total != parts["parts_total"]:
        STATE["content_parts"] = None
        return False, ("[Система]: часть файла отклонена: 'content_parts_total' изменился по ходу "
                       "передачи (%d -> %d). Накопленное сброшено — пришли заново с первой части."
                       % (parts["parts_total"], parts_total))
    parts["chunks"].append(chunk)
    parts["count"] += 1
    STATE["content_parts"] = parts
    print("--> Принята часть %d/%d содержимого файла %s (v86.26)." % (parts["count"], parts["parts_total"], path))
    return True, ("[Система]: часть %d/%d файла %s принята (%d симв.). Пришли СЛЕДУФЩУю часть тем же "
                  "действием (action=create_file, тот же 'path'): \"content_part\": %d, "
                  "\"content_parts_total\": %d, \"continues\": true — если после неё будут ещё части, "
                  "или без \"continues\", если это последняя. Уже присланное НЕ повторяй."
                  % (parts["count"], parts["parts_total"], path, len(chunk),
                     parts["count"] + 1, parts["parts_total"]))


def _content_collect_final(action):
    """Последняя часть многочастной передачи content (или обычный
    одночастный create_file): склеивает накопленные части (если были) с content
    из текущего action. Возвращает целый текст файла и очищает накопитель."""
    chunk = action.get("content") if isinstance(action.get("content"), str) else ""
    parts = STATE.get("content_parts")
    if parts and parts.get("path") == action.get("path"):
        full = "".join(parts["chunks"]) + chunk
        declared_total = action.get("content_total_lines")
        part_count = parts["count"]
        STATE["content_parts"] = None
        try:
            declared_total = int(declared_total) if declared_total is not None else None
        except (TypeError, ValueError):
            declared_total = None
        if declared_total is not None:
            actual = len(full.split("\n"))
            if declared_total != actual:
                print(u"[main] ВНИМАНИЕ: для %s объявлено %d строк(и) итогового файла, а "
                      u"собрано %d — возможна потеря части при склейке (v86.26)." % (action.get("path"), declared_total, actual))
        print("--> Многочастная передача файла %s склеена: %d частей." % (action.get("path"), part_count + 1))
        return full
    STATE["content_parts"] = None
    return chunk


def _apply_write_step(action, project_root, chain_id=None, validation=None):
    """Применяет ОДНО write-действие (create_file/patch_file/move_file) на диске,
    с записью в журнал изменений. Общий путь для одиночных действий
    и для шагов плана (chain_id задаётся только во втором случае).
    Возвращает dict: {"ok", "message", "changed_path", "changed_block", "entry_id"}.

    entry_id — идентификатор записи журнала. Он обязан доходить до панели:
    именно по нему кнопка отката на карточке сообщения отменяет ИМЕННО ЭТО
    изменение. Раньше id оставался локальной переменной, панель просила
    «откатить последнее», и кнопка на старом облачке чата отменяла чужое,
    самое свежее изменение проекта.
    """
    act_type = action.get("action")
    path = action.get("path", "")
    dest = action.get("dest", "")
    if _is_project_settings_path(path) or _is_project_settings_path(dest):
        return {"ok": False, "message": "project.godot изменяется только через edit_project_settings.",
                "changed_path": None, "changed_block": None}
    if _is_text_scene_path(path) or _is_text_scene_path(dest):
        return {"ok": False, "message": ".tscn изменяются только через create_scene/edit_scene.",
                "changed_path": None, "changed_block": None}
    if (not STATE.get("addon_intent")) and (_is_addon_path(path) or _is_addon_path(dest)):
        return {"ok": False, "message": _addon_blocked_message(path if _is_addon_path(path) else dest),
                "changed_path": None, "changed_block": None}
    if validation is not None:
        try:
            godot_headless_validation.verify_receipt(
                project_root, validation.get("batch"), validation.get("receipt"))
        except Exception as exc:
            return {"ok": False, "message": str(exc),
                    "changed_path": None, "changed_block": None}
    entry_id = history.record_change(project_root, action, *_current_chat_info(), chain_id=chain_id)
    try:
        if act_type == "create_file":
            overwrote = create_project_file(project_root, path, action.get("content", ""))
        elif act_type == "patch_file":
            patch_project_file(project_root, path, action.get("search", ""), action.get("replace", ""))
            overwrote = None
        elif act_type == "move_file":
            move_project_file(project_root, path, action.get("dest", ""))
            overwrote = None
        else:
            history.abort_change(project_root, entry_id)
            return {"ok": False, "message": "Неизвестный тип действия: %s" % act_type, "changed_path": None, "changed_block": None}
    except MoveRecoveryError as e:
        return {"ok": False, "message": str(e), "changed_path": None, "changed_block": None,
                "recovery_required": True, "recovery_entry_id": entry_id}
    except Exception as e:
        history.abort_change(project_root, entry_id)
        return {"ok": False, "message": str(e), "changed_path": None, "changed_block": None}
    history.commit_change(project_root, entry_id)
    _refresh_fs_snapshot(project_root)  # своя запись — не «внешнее» изменение
    if act_type in ("create_file", "patch_file"):
        _remember_file(project_root, path)   # модель знает, что сама написала
    elif act_type == "move_file":
        _forget_file(path)
        _remember_file(project_root, action.get("dest", ""))
    try:
        # v105: микро-обновление индекса Библиотекаря (без полной пересборки)
        if act_type == "move_file":
            librarian.note_files_changed(project_root, [action.get("dest", "")], deleted=[path])
        else:
            librarian.note_files_changed(project_root, [path])
    except Exception:
        pass
    if act_type != "move_file":
        _touch_file_read(path)
    if act_type == "create_file":
        message = ("Файл полностью перезаписан: %s" % path) if overwrote else ("Файл успешно создан: %s" % path)
        return {"ok": True, "message": message, "changed_path": path,
                "changed_block": action.get("content", ""), "entry_id": entry_id}
    if act_type == "patch_file":
        return {"ok": True, "message": "Изменения успешно внесены в файл: %s" % path,
                "changed_path": path, "changed_block": action.get("replace", ""),
                "entry_id": entry_id}
    return {"ok": True, "message": "Файл успешно перемещён в: %s" % action.get("dest", ""),
            "changed_path": None, "changed_block": None, "entry_id": entry_id}


# ---------------------------------------------------------------------------
# Пакетное чтение файлов: модель запрашивает несколько файлов ОДНИМ
# действием, пользователь подтверждает каждый по очереди (без обращений
# к браузеру!), и только после последнего решения в браузер уходит ОДИН
# запрос со всеми одобренными файлами и пометками об отказах.
# ---------------------------------------------------------------------------

def _start_read_batch(action, project_root):
    if action.get("action") == "read_function":
        # v48: запрошены не файлы целиком, а конкретные функции из .gd-скриптов.
        entries = []
        raw = action.get("requests")
        if isinstance(raw, list):
            for r in raw:
                if isinstance(r, dict) and r.get("path"):
                    entries.append((r.get("path"), r.get("names") or r.get("functions") or []))
        elif action.get("path"):
            entries.append((action.get("path"), action.get("names") or action.get("functions") or []))
    else:
        paths = action.get("paths") or ([action.get("path")] if action.get("path") else [])
        entries = [(p, None) for p in paths]
    seen, files = set(), []
    for p, names in entries[:MAX_BATCH_FILES]:
        if not p or p in seen:
            continue
        seen.add(p)
        if _is_addon_path(p) and not STATE.get("addon_intent"):
            # Модель не должна САМА запрашивать файлы аддона без явной просьбы
            # пользователя в этом сообщении — отмечаем "blocked" и не спрашиваем
            # пользователя вообще (см. _addon_blocked_message в _finish_read_batch).
            files.append({"path": p, "status": "blocked"})
            continue
        status = "pending"
        try:
            if not os.path.isfile(_resolve_safe_path(project_root, p)):
                status = "missing"
        except Exception:
            status = "missing"
        rec = {"path": p, "status": status}
        if names is not None:  # v48: read_function — список запрошенных функций
            rec["names"] = [str(n).strip() for n in names if str(n).strip()][:10]
        files.append(rec)
    return {"files": files, "reason": action.get("reason", "")}


def _next_batch_confirmation():
    batch = STATE.get("pending_batch")
    if not batch:
        return None
    files = batch["files"]
    # "blocked" (аддон без явной просьбы) никогда не доходит до вопроса пользователю —
    # он просто прошёл, как если бы уже разрешён/обработан (см. _finish_read_batch).
    for i, f in enumerate(files):
        if f["status"] == "pending":
            if f.get("names") is not None:
                what = ", ".join(f["names"]) if f.get("names") else "(список имён функций)"
                desc = "Агент хочет прочитать функции из файла (%d из %d): %s\nФункции: %s" % (i + 1, len(files), f["path"], what)
            else:
                desc = "Агент хочет прочитать файл (%d из %d): %s" % (i + 1, len(files), f["path"])
            if batch.get("reason"):
                desc += "\nПричина: " + str(batch["reason"])
            return {"path": f["path"], "description": desc}
    return None


def _finish_read_batch(project_root):
    """Собирает ОДНО сообщение для модели из всех решений по пачке."""
    batch = STATE["pending_batch"]
    STATE["pending_batch"] = None
    parts, total = [], 0
    fence = "`" * 3
    for f in batch["files"]:
        if f["status"] == "approved":
            if f.get("names") is not None:  # v48: точечное чтение функций
                part = _read_functions_part(project_root, f)
                total += len(part)
                parts.append(part)
                continue
            try:
                content, truncated = read_project_file(project_root, f["path"], max_chars=PER_FILE_CHAR_LIMIT)
            except Exception as e:
                parts.append("[Система]: Ошибка чтения %s: %s" % (f["path"], e))
                continue
            if total + len(content) > TOTAL_CHAR_BUDGET:
                content = content[:max(0, TOTAL_CHAR_BUDGET - total)]
                truncated = True
            total += len(content)
            note = " (файл обрезан)" if truncated else ""
            parts.append("Содержимое файла %s%s:\n%s\n%s\n%s" % (f["path"], note, fence, content, fence))
            _touch_file_read(f["path"])  # чат теперь знает актуальное содержимое
            _remember_file(project_root, f["path"])  # для точечных diff ручных правок
        elif f["status"] == "rejected":
            parts.append("[Система]: Пользователь ОТКАЗАЛСЯ показывать файл %s. НЕ запрашивай его повторно; работай без него или объясни пользователю, зачем он нужен." % f["path"])
        elif f["status"] == "missing":
            parts.append("[Система]: Файл %s не найден в проекте. Сверься со структурой проекта." % f["path"])
        elif f["status"] == "blocked":
            parts.append("[Система]: " + _addon_blocked_message(f["path"]))
    return "\n\n".join(parts) or "[Система]: Ни один файл не был предоставлен."


def _read_functions_part(project_root, f):
    """v48: read_function — фрагмент ответа модели по одному файлу: только
    запрошенные функции, а не файл целиком. Для отсутствующих имён модель
    получает список имеющихся функций и может дозапросить нужные ещё одним
    read_function — чтение работает по цепочке."""
    fence = "`" * 3
    path = f["path"]
    if not str(path).endswith(".gd"):
        return ("[Система]: read_function работает только для .gd-скриптов. "
                "Файл %s запроси целиком через read_file." % path)
    try:
        content, _truncated = read_project_file(project_root, path, max_chars=PER_FILE_CHAR_LIMIT * 4)
    except Exception as e:
        return "[Система]: Ошибка чтения %s: %s" % (path, e)
    all_names = gd_functions.list_functions(content)
    names = f.get("names") or []
    if not names:
        return "[Система]: Функции файла %s: %s." % (path, ", ".join(all_names) or "(функций не найдено)")
    found, missing = gd_functions.extract_functions(content, names)
    out = []
    for item in found:
        out.append(
            "Функция %s из файла %s (строки %d–%d; блок дословный — можно использовать как search в patch_file):\n%s\n%s\n%s"
            % (item["name"], path, item["start_line"], item["end_line"], fence, item["snippet"], fence))
    if missing:
        out.append(
            "[Система]: В файле %s НЕТ функций: %s. Доступные функции: %s. Нужное можешь дозапросить ещё одним read_function."
            % (path, ", ".join(missing), ", ".join(all_names) or "(функций не найдено)"))
    return "\n\n".join(out)


def _package_model_reply(text, action, project_root, depth=0, allow_followup=True):
    """Единая упаковка ответа модели в HTTP-ответ для Godot:
    parse_error / запрос чтения / write-действие / просто текст."""
    if action and action.get("action") == "parse_error":
        STATE["pending_action"] = None
        return jsonify({
            "answer": text + "\n\n[Система]: ⚠ Не удалось получить корректный JSON действия даже после нескольких повторных попыток (включая точечное восстановление шагов плана, если сломанный ответ был похож на план).",
            "pending_action": None,
        })
    # v86.26: многочастная передача большого content для create_file: если это не последняя часть
    # ("continues": true) — копим и просим следующую, не доводя дело до подтверждения.
    if action and action.get("action") == "create_file" and action.get("continues"):
        STATE["pending_action"] = None
        ok_part, followup = _content_part_add(action)
        if not allow_followup or depth >= MAX_CONTENT_PARTS + 3 or (not ok_part and depth >= 2):
            STATE["content_parts"] = None
            return jsonify({"answer": (text + "\n\n" + followup).strip(), "pending_action": None})
        text2, act2 = _reply_with_self_heal(followup, project_root)
        return _package_model_reply(text2, act2, project_root, depth + 1)
    # Последняя часть (или обычный одночастный create_file) — склеиваем с накопленным и выкусываем
    # служебные поля из действия (не-multi-part create_file проходит через то же без изменений).
    if action and action.get("action") == "create_file" and not action.get("continues"):
        merged = _content_collect_final(action)
        if (merged != action.get("content") or "content_part" in action
                or "content_parts_total" in action or "content_total_lines" in action):
            action = dict(action)
            action["content"] = merged
            action.pop("content_part", None)
            action.pop("content_parts_total", None)
            action.pop("content_total_lines", None)
    if not allow_followup and action and action.get("action") in ("create_file", "patch_file"):
        problems = _lint_action_code(action, project_root)
        if problems:
            STATE["pending_action"] = None
            return jsonify({"answer": text + "\n\n" + problems, "pending_action": None})
    if action and action.get("action") in ("read_file", "read_files", "read_function"):
        STATE["pending_action"] = None
        STATE["pending_batch"] = _start_read_batch(action, project_root)
        nxt = _next_batch_confirmation()
        if nxt is None:
            # Все запрошенные файлы missing — сообщаем модели сразу (1 запрос),
            # но не глубже 2 раз — защита от зацикливания на несуществующих путях.
            followup = _finish_read_batch(project_root)
            if not allow_followup or depth >= 2:
                return jsonify({"answer": text + "\n\n" + followup, "pending_action": None})
            text2, act2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, act2, project_root, depth + 1)
        return jsonify({"answer": text, "next_confirmation": nxt})
    if action and action.get("action") == "ask_librarian":
        # v105: справка Библиотекаря — read-only, диск не меняется, поэтому
        # выполняется АВТОМАТИЧЕСКИ, без подтверждения (как copy_file).
        STATE["pending_action"] = None
        query = str(action.get("query") or action.get("q") or "").strip()
        print("--> ask_librarian: «%s»" % query)
        try:
            followup = librarian.answer(project_root, query,
                                        addon_dir=STATE.get("addon_dir"))
        except Exception as e:
            followup = ("[Librarian]: internal error: %s. Fall back to search_project / "
                        "list_files / read_file." % e)
        if not allow_followup or depth >= 3:
            return jsonify({"answer": (text + "\n\n" + followup).strip(), "pending_action": None})
        # A follow-up generated by the agent should not appear immediately
        # after the previous answer; the ordinary send pipeline adds its own
        # post-paste delay as well.
        time.sleep(1.5)
        text2, act2 = _reply_with_self_heal(followup, project_root)
        return _package_model_reply(text2, act2, project_root, depth + 1)
    if action and action.get("action") == "inspect_runtime":
        try:
            normalized = runtime_debug.normalize_action(action)
            if int(STATE.get("runtime_inspections_this_turn") or 0) >= 1:
                raise runtime_debug.RuntimeDebugError(
                    "only one inspect_runtime action is allowed per user turn")
            runtime_debug.select_session(
                STATE.get("runtime_status"), normalized.get("session_id"))
        except Exception as exc:
            STATE["pending_action"] = None
            return jsonify({"answer": (text + "\n\n[Система]: inspect_runtime отклонён: %s" % exc).strip(),
                            "pending_action": None})
        STATE["pending_action"] = normalized
        _remember("agent", text)
        _sync_chat_after_reply()
        return jsonify({"answer": text, "pending_action": normalized,
                        "pending_action_description": _describe_action(normalized),
                         "pending_action_code": None})
    if action and action.get("action") == "run_check":
        try:
            normalized = runtime_checks.normalize_action(
                project_root, action, allow_addons=bool(STATE.get("addon_intent")))
            if int(STATE.get("runtime_inspections_this_turn") or 0) >= 1:
                raise runtime_checks.RuntimeCheckError(
                    "only one inspect_runtime or run_check action is allowed per user turn")
        except Exception as exc:
            STATE["pending_action"] = None
            return jsonify({"answer": (text + "\n\n[Система]: run_check отклонён: %s" % exc).strip(),
                            "pending_action": None})
        STATE["pending_action"] = normalized
        _remember("agent", text)
        _sync_chat_after_reply()
        return jsonify({"answer": text, "pending_action": normalized,
                        "pending_action_description": _describe_action(normalized),
                        "pending_action_code": None})
    if action and action.get("action") == "copy_file":
        STATE["pending_action"] = None
        raw_copies = action.get("copies")
        pairs = []
        if isinstance(raw_copies, list):
            for c in raw_copies:
                if isinstance(c, dict):
                    s = c.get("src") or c.get("path") or c.get("from")
                    d = c.get("dest") or c.get("to")
                    if s and d:
                        pairs.append((s, d))
        else:
            s = action.get("path") or action.get("src")
            d = action.get("dest") or action.get("to")
            if s and d:
                pairs.append((s, d))
        results = []
        for s, d in pairs[:20]:
            if _is_project_settings_path(s) or _is_project_settings_path(d):
                results.append("✗ %s -> %s: project.godot изменяется только через edit_project_settings" % (s, d))
                continue
            if _is_text_scene_path(s) or _is_text_scene_path(d):
                results.append("✗ %s -> %s: сцены создаются и изменяются только через create_scene/edit_scene" % (s, d))
                continue
            if (not STATE.get("addon_intent")) and (_is_addon_path(s) or _is_addon_path(d)):
                results.append("\u2717 %s -> %s: %s" % (s, d, _addon_blocked_message(s if _is_addon_path(s) else d)))
                continue
            synthetic = {"action": "create_file", "path": d}
            entry_id = history.record_change(project_root, synthetic, *_current_chat_info())
            try:
                copy_project_file(project_root, s, d)
            except Exception as e:
                history.abort_change(project_root, entry_id)
                results.append("\u2717 %s -> %s: %s" % (s, d, e))
                continue
            history.commit_change(project_root, entry_id)
            results.append("\u2713 %s -> %s" % (s, d))
            print("--> copy_file %s -> %s" % (s, d))
            _remember_file(project_root, d)
            librarian.note_files_changed(project_root, [d])  # v105: индекс Библиотекаря
        if pairs:
            _refresh_fs_snapshot(project_root)
        if not pairs:
            followup = ("[Система]: copy_file пришёл без пар src/dest. Пришли заново: "
                        '{"action":"copy_file","copies":[{"src":"res://...","dest":"res://..."}]}.')
        else:
            followup = ("[Система]: Результат копирования (файлы скопированы БЕЗ изменений; "
                        "адаптацию под проект делай через patch_file, он потребует подтверждения):\n"
                        + "\n".join(results))
        if not allow_followup or depth >= 3:
            return jsonify({"answer": (text + "\n\n" + followup).strip(), "pending_action": None})
        text2, act2 = _reply_with_self_heal(followup, project_root)
        return _package_model_reply(text2, act2, project_root, depth + 1)
    if action and action.get("action") == "project_command":
        try:
            compiled = high_level_actions.compile_action(
                project_root, action, allow_addons=bool(STATE.get("addon_intent")))
        except Exception as exc:
            followup = ("[Система]: project_command отклонена локальным компилятором: %s. "
                        "Исправь схему команды; не заменяй её небезопасными текстовыми правками." % exc)
            if not allow_followup or depth >= MAX_ACTION_FIX_RETRIES:
                return jsonify({"answer": (text + "\n\n" + followup).strip(),
                                "pending_action": None})
            text2, action2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, action2, project_root, depth + 1)
        return _package_model_reply(text, compiled, project_root, depth, allow_followup=allow_followup)
    if action and action.get("action") == "plan":
        STATE["pending_action"] = None
        # Многочастный план: модель присылает шаги несколькими сообщениями
        # ("continues": true), если все шаги не помещаются в один ответ
        # (не хватает выходного лимита токенов). Пользователь увидит и
        # подтвердит склеенный план ОДИН раз — целиком, за один проход.
        if action.get("continues"):
            ok_part, followup = _plan_part_add(action)
            if not allow_followup or depth >= MAX_PLAN_PARTS + 4 or (not ok_part and depth >= 2):
                STATE["plan_parts"] = None
                return jsonify({"answer": (text + "\n\n" + followup).strip(), "pending_action": None})
            text2, act2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, act2, project_root, depth + 1)
        steps, plan_description = _plan_collect_final(action)
        ok, err = _validate_plan_steps(steps, max_steps=MAX_PLAN_TOTAL_STEPS)
        if not ok:
            followup = "[Система]: план отклонён автоматически: %s Исправь и пришли agent_action заново (action=plan; если все шаги не помещаются в один ответ — частями через \"continues\": true)." % err
            if not allow_followup or depth >= 2:
                return jsonify({"answer": (text + "\n\n" + followup).strip(), "pending_action": None})
            text2, act2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, act2, project_root, depth + 1)
        chain_id = history.new_chain_id()
        pending_plan = {
            "chain_id": chain_id,
            "steps": steps,
            "index": 0,
            "description": plan_description,
            "total": len(steps),
            "applied_paths": [],
        }
        STATE["pending_plan"] = pending_plan
        synthetic = {"action": "plan", "description": plan_description,
                     "steps": steps, "total": len(steps)}
        STATE["pending_action"] = synthetic
        _remember("agent", text)
        _sync_chat_after_reply()
        return jsonify({
            "answer": text,
            "pending_action": synthetic,
            "pending_action_description": _describe_action(synthetic),
            "pending_action_code": None,
        })
    if action and action.get("action") == "transaction":
        receipt = None
        try:
            prepared = transaction_actions.prepare(
                project_root, action, allow_addons=bool(STATE.get("addon_intent")),
                addon_dir=STATE.get("addon_dir"))
            if prepared["batch"] is not None:
                receipt = godot_headless_validation.validate_batch(
                    project_root, prepared["batch"], executable=STATE.get("godot_executable"))
                engine_error = godot_headless_validation.blocking_message(receipt)
                if engine_error:
                    raise transaction_actions.TransactionError(engine_error)
                godot_headless_validation.verify_receipt(project_root, prepared["batch"], receipt)
                transaction_actions.attach_validation(prepared, receipt)
            if prepared.get("already_satisfied"):
                STATE["pending_action"] = None
                STATE["pending_transaction"] = None
                check_note = " Запрошенные проверки Godot пройдены." if prepared["batch"] else ""
                message = (text + "\n\n[Система]: Пакет уже полностью выполнен в проекте; "
                           "запись файлов, подтверждение и дополнительный запрос к модели не требуются."
                           + check_note).strip()
                return jsonify({"answer": message, "pending_action": None,
                                "already_satisfied": True, "changed_paths": [],
                                "effective_operation_count": 0,
                                "skipped_operation_count": prepared.get("skipped_operation_count", 0)})
        except Exception as exc:
            STATE["pending_action"] = None
            STATE["pending_transaction"] = None
            followup = ("[Система]: transaction отклонена локальной пакетной проверкой: %s. "
                        "Исправь операции и пришли весь пакет заново; не разбивай его на небезопасные частичные правки." % exc)
            report = (receipt or {}).get("report") or {}
            infrastructure_failure = receipt is not None and not (
                report.get("new_diagnostics") or report.get("check_diagnostics"))
            if not allow_followup or depth >= 2 or infrastructure_failure:
                return jsonify({"answer": (text + "\n\n" + followup).strip(),
                                "pending_action": None})
            text2, action2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, action2, project_root, depth + 1)
        public = transaction_actions.public_prepared(prepared)
        STATE["pending_transaction"] = prepared
        STATE["pending_action"] = public
        _remember("agent", text)
        _sync_chat_after_reply()
        return jsonify({"answer": text, "pending_action": public,
                        "pending_action_description": _describe_action(public),
                        "pending_action_code": None,
                        "pending_action_diffs": transaction_actions.prepared_diffs(prepared)})
    if action and action.get("action") == "rename_symbol":
        try:
            prepared = symbol_refactor.prepare_rename(
                project_root, action, allow_addons=bool(STATE.get("addon_intent")),
                addon_dir=STATE.get("addon_dir"))
        except Exception as exc:
            STATE["pending_action"] = None
            STATE["pending_refactor"] = None
            followup = ("[Система]: rename_symbol отклонён безопасным локальным анализом: %s. "
                        "Не заменяй имя слепыми patch_file; исправь locator/имя или объясни "
                        "пользователю найденную неоднозначность." % exc)
            if not allow_followup or depth >= 2:
                return jsonify({"answer": (text + "\n\n" + followup).strip(),
                                "pending_action": None})
            text2, action2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, action2, project_root, depth + 1)
        batch = godot_headless_validation.batch_from_rename(project_root, prepared)
        receipt = godot_headless_validation.validate_batch(
            project_root, batch, executable=STATE.get("godot_executable"))
        engine_error = godot_headless_validation.blocking_message(receipt)
        if engine_error:
            STATE["pending_action"] = None
            STATE["pending_refactor"] = None
            report = receipt.get("report") or {}
            if allow_followup and depth < MAX_ACTION_FIX_RETRIES and report.get("new_diagnostics"):
                text2, action2 = _reply_with_self_heal(engine_error, project_root)
                return _package_model_reply(text2, action2, project_root, depth + 1)
            return jsonify({"answer": (text + "\n\n" + engine_error).strip(),
                            "pending_action": None})
        prepared["validation"] = {"batch": batch, "receipt": receipt}
        public = dict(action)
        public.update(symbol_refactor.public_prepared(prepared))
        STATE["pending_refactor"] = prepared
        STATE["pending_action"] = public
        _remember("agent", text)
        _sync_chat_after_reply()
        diffs = symbol_refactor.prepared_diffs(prepared)
        return jsonify({"answer": text, "pending_action": public,
                        "pending_action_description": _describe_action(public),
                        "pending_action_code": None,
                        "pending_action_diff": diffs[0] if len(diffs) == 1 else None,
                         "pending_action_diffs": diffs})
    if action and action.get("action") == "rename_file":
        try:
            prepared = file_refactor.prepare_file_rename(
                project_root, action.get("path"), action.get("dest") or action.get("new_path"),
                update_references=bool(action.get("update_references", True)),
                allow_addons=bool(STATE.get("addon_intent")))
        except Exception as exc:
            STATE["pending_action"] = None
            STATE["pending_file_refactor"] = None
            followup = ("[Система]: rename_file отклонён: %s. "
                        "Исправь пути или проверь существование файлов." % exc)
            if not allow_followup or depth >= 2:
                return jsonify({"answer": (text + "\n\n" + followup).strip(),
                                "pending_action": None})
            text2, action2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, action2, project_root, depth + 1)
        public = dict(action)
        public["dest"] = prepared["new_path"]
        public["reference_count"] = prepared["reference_count"]
        public["file_count"] = len(prepared["files"])
        public["affected_paths"] = prepared["affected_paths"]
        public["is_directory"] = prepared.get("is_directory", False)
        STATE["pending_file_refactor"] = prepared
        STATE["pending_action"] = public
        _remember("agent", text)
        _sync_chat_after_reply()
        diffs = [item["diff"] for item in prepared["files"]]
        return jsonify({"answer": text, "pending_action": public,
                        "pending_action_description": _describe_action(public),
                        "pending_action_code": None,
                        "pending_action_diff": diffs[0] if len(diffs) == 1 else None,
                        "pending_action_diffs": diffs})
    if action and action.get("action") == "rename_node":
        try:
            prepared = node_refactor.prepare_node_rename(
                project_root,
                action.get("scene"),
                action.get("node_path") or action.get("node"),
                action.get("new_name") or action.get("name"),
                allow_addons=bool(STATE.get("addon_intent"))
            )
        except Exception as exc:
            STATE["pending_action"] = None
            STATE["pending_node_refactor"] = None
            followup = ("[Система]: rename_node отклонён: %s. "
                        "Исправь имя узла или путь к сцене." % exc)
            if not allow_followup or depth >= 2:
                return jsonify({"answer": (text + "\n\n" + followup).strip(),
                                "pending_action": None})
            text2, action2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, action2, project_root, depth + 1)
        public = dict(action)
        public["scene"] = prepared["scene_res"]
        public["node_path"] = prepared["target_node_path"]
        public["new_name"] = prepared["new_name"]
        public["reference_count"] = prepared["reference_count"]
        public["file_count"] = len(prepared["files"])
        public["affected_paths"] = prepared["affected_paths"]
        STATE["pending_node_refactor"] = prepared
        STATE["pending_action"] = public
        _remember("agent", text)
        _sync_chat_after_reply()
        diffs = [item["diff"] for item in prepared["files"]]
        return jsonify({"answer": text, "pending_action": public,
                        "pending_action_description": _describe_action(public),
                        "pending_action_code": None,
                        "pending_action_diff": diffs[0] if len(diffs) == 1 else None,
                        "pending_action_diffs": diffs})
    if action and action.get("action") == "reparent_node":
        try:
            prepared = node_refactor.prepare_node_reparent(
                project_root,
                action.get("scene"),
                action.get("node_path") or action.get("node"),
                action.get("new_parent") or action.get("parent"),
                allow_addons=bool(STATE.get("addon_intent"))
            )
        except Exception as exc:
            STATE["pending_action"] = None
            STATE["pending_node_refactor"] = None
            followup = ("[Система]: reparent_node отклонён: %s. "
                        "Исправь имя узла, нового родителя или путь к сцене." % exc)
            if not allow_followup or depth >= 2:
                return jsonify({"answer": (text + "\n\n" + followup).strip(),
                                "pending_action": None})
            text2, action2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, action2, project_root, depth + 1)
        public = dict(action)
        public["scene"] = prepared["scene_res"]
        public["node_path"] = prepared["target_node_path"]
        public["new_parent"] = prepared["new_parent"]
        public["reference_count"] = prepared["reference_count"]
        public["file_count"] = len(prepared["files"])
        public["affected_paths"] = prepared["affected_paths"]
        STATE["pending_node_refactor"] = prepared
        STATE["pending_action"] = public
        _remember("agent", text)
        _sync_chat_after_reply()
        diffs = [item["diff"] for item in prepared["files"]]
        return jsonify({"answer": text, "pending_action": public,
                        "pending_action_description": _describe_action(public),
                        "pending_action_code": None,
                        "pending_action_diff": diffs[0] if len(diffs) == 1 else None,
                        "pending_action_diffs": diffs})
    if action and action.get("action") == "delete_node":
        try:
            prepared = node_refactor.prepare_node_deletion(
                project_root,
                action.get("scene"),
                action.get("node_path") or action.get("node"),
                cleanup_code=bool(action.get("cleanup_code", True)),
                allow_addons=bool(STATE.get("addon_intent"))
            )
        except Exception as exc:
            STATE["pending_action"] = None
            STATE["pending_node_refactor"] = None
            followup = ("[Система]: delete_node отклонён: %s. "
                        "Исправь имя узла или путь к сцене." % exc)
            if not allow_followup or depth >= 2:
                return jsonify({"answer": (text + "\n\n" + followup).strip(),
                                "pending_action": None})
            text2, action2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, action2, project_root, depth + 1)
        public = dict(action)
        public["scene"] = prepared["scene_res"]
        public["node_path"] = prepared["target_node_path"]
        public["deleted_nodes"] = prepared["deleted_nodes"]
        public["reference_count"] = prepared["reference_count"]
        public["file_count"] = len(prepared["files"])
        public["affected_paths"] = prepared["affected_paths"]
        public["warnings"] = prepared.get("warnings", [])
        STATE["pending_node_refactor"] = prepared
        STATE["pending_action"] = public
        _remember("agent", text)
        _sync_chat_after_reply()
        diffs = [item["diff"] for item in prepared["files"]]
        return jsonify({"answer": text, "pending_action": public,
                        "pending_action_description": _describe_action(public),
                        "pending_action_code": None,
                        "pending_action_diff": diffs[0] if len(diffs) == 1 else None,
                        "pending_action_diffs": diffs})
    if action and action.get("action") in ("edit_scene", "create_scene"):
        try:
            prepared = scene_actions.prepare(
                project_root, action, allow_addons=bool(STATE.get("addon_intent")))
        except Exception as exc:
            STATE["pending_action"] = None
            STATE["pending_scene_action"] = None
            followup = ("[Система]: структурное действие сцены отклонено локальной проверкой схемы: %s. "
                        "Исправь пути/операции; не заменяй структурную операцию сырой правкой .tscn."
                        % exc)
            if not allow_followup or depth >= 2:
                return jsonify({"answer": (text + "\n\n" + followup).strip(),
                                "pending_action": None})
            text2, action2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, action2, project_root, depth + 1)
        public = dict(prepared["action"])
        public.update(scene_actions.public_prepared(prepared))
        STATE["pending_scene_action"] = prepared
        STATE["pending_action"] = public
        _remember("agent", text)
        _sync_chat_after_reply()
        return jsonify({"answer": text, "pending_action": public,
                        "pending_action_description": _describe_action(public),
                        "pending_action_code": None,
                         "scene_prepare": scene_actions.public_prepared(prepared)})
    if action and action.get("action") == "edit_project_settings":
        try:
            prepared = project_settings_actions.prepare(
                project_root, action, allow_addons=bool(STATE.get("addon_intent")))
        except Exception as exc:
            STATE["pending_action"] = None
            STATE["pending_project_settings_action"] = None
            followup = ("[Система]: edit_project_settings отклонён локальной проверкой схемы: %s. "
                        "Исправь операции; не правь project.godot через patch_file/create_file/move_file."
                        % exc)
            if not allow_followup or depth >= 2:
                return jsonify({"answer": (text + "\n\n" + followup).strip(),
                                "pending_action": None})
            text2, action2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, action2, project_root, depth + 1)
        public = dict(prepared["action"])
        public.update(project_settings_actions.public_prepared(prepared))
        STATE["pending_project_settings_action"] = prepared
        STATE["pending_action"] = public
        _remember("agent", text)
        _sync_chat_after_reply()
        return jsonify({"answer": text, "pending_action": public,
                        "pending_action_description": _describe_action(public),
                        "pending_action_code": None,
                        "project_settings_prepare": project_settings_actions.public_prepared(prepared)})
    if action and action.get("action") == "edit_resource":
        try:
            prepared = resource_actions.prepare(
                project_root, action, allow_addons=bool(STATE.get("addon_intent")))
        except Exception as exc:
            STATE["pending_action"] = None
            STATE["pending_resource_action"] = None
            followup = ("[Система]: edit_resource отклонён локальной проверкой схемы: %s. "
                        "Исправь ресурс/операции; не заменяй структурную операцию сырой правкой .tres."
                        % exc)
            if not allow_followup or depth >= 2:
                return jsonify({"answer": (text + "\n\n" + followup).strip(),
                                "pending_action": None})
            text2, action2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, action2, project_root, depth + 1)
        public = dict(prepared["action"])
        public.update(resource_actions.public_prepared(prepared))
        STATE["pending_resource_action"] = prepared
        STATE["pending_action"] = public
        _remember("agent", text)
        _sync_chat_after_reply()
        return jsonify({"answer": text, "pending_action": public,
                        "pending_action_description": _describe_action(public),
                        "pending_action_code": None,
                        "resource_prepare": resource_actions.public_prepared(prepared)})
    if action and action.get("action") in ("create_file", "patch_file", "move_file"):
        if _is_text_scene_path(action.get("path")) or _is_text_scene_path(action.get("dest")):
            engine_error = ("[Система]: сырая запись .tscn отклонена. Для новой сцены используй "
                            "create_scene, для существующей — edit_scene; не обходи структурный API.")
            STATE["pending_action"] = None
            STATE["pending_validation"] = None
            if allow_followup and depth < MAX_ACTION_FIX_RETRIES:
                text2, action2 = _reply_with_self_heal(engine_error, project_root)
                return _package_model_reply(text2, action2, project_root, depth + 1)
            return jsonify({"answer": (text + "\n\n" + engine_error).strip(),
                            "pending_action": None})
        try:
            batch = godot_headless_validation.batch_from_action(project_root, action)
            receipt = godot_headless_validation.validate_batch(
                project_root, batch, executable=STATE.get("godot_executable"))
        except Exception as exc:
            receipt = None
            engine_error = "[Система]: не удалось подготовить изолированную проверку Godot: %s" % exc
        else:
            engine_error = godot_headless_validation.blocking_message(receipt)
        if engine_error:
            STATE["pending_action"] = None
            STATE["pending_validation"] = None
            report = (receipt or {}).get("report") or {}
            if allow_followup and depth < MAX_ACTION_FIX_RETRIES and report.get("new_diagnostics"):
                text2, action2 = _reply_with_self_heal(engine_error, project_root)
                return _package_model_reply(text2, action2, project_root, depth + 1)
            return jsonify({"answer": (text + "\n\n" + engine_error).strip(),
                            "pending_action": None})
        STATE["pending_validation"] = {"batch": batch, "receipt": receipt}
    if not text and action is None:
        # Пустой ответ из браузера: парсер мог не дождаться конца генерации
        # длинного ответа. Не молчим — пользователь должен это увидеть.
        text = ("[Система]: ⚠ Из браузера пришёл ПУСТОЙ ответ. Скорее всего, модель "
                "ещё генерировала текст, а парсер не дождался конца. Ответ, вероятно, "
                "виден во вкладке AI Studio. Можно написать модели: 'повтори последний ответ'.")
    _remember("agent", text)
    _sync_chat_after_reply()
    STATE["pending_action"] = action
    # Чистый код для красивого предпросмотра в панели (без JSON-обёртки).
    code_preview = None
    if isinstance(action, dict):
        if action.get("action") == "patch_file":
            code_preview = action.get("replace")
        elif action.get("action") == "create_file":
            code_preview = action.get("content")
    if not (isinstance(code_preview, str) and code_preview.strip()):
        code_preview = None
    elif len(code_preview) > 1500:
        code_preview = code_preview[:1500] + "\n… (показано начало, применится полный код)"
    return jsonify({
        "answer": text,
        "pending_action": action,
        "pending_action_description": _describe_action(action),
        "pending_action_code": code_preview,
        # Разобранный дифф (что именно добавится и удалится) — панель красит по нему
        # строки и сворачивает всё в одну строку с именем файла. Старые панели поля
        # не знают и продолжают показывать pending_action_code как раньше.
        "pending_action_diff": action_diff_preview(project_root, action),
    })


def _attach_battle_choice(response):
    summary = STATE.pop("battle_choice_summary", None)
    if not isinstance(summary, dict):
        return response
    try:
        payload = response.get_json(silent=True)
    except Exception:
        payload = None
    if not isinstance(payload, dict):
        return response
    payload["battle_choice"] = summary
    return jsonify(payload)


def _current_chat_info():
    """(chat_id, chat_title) текущего чата — для меток в журнале изменений."""
    chat = server_state.get_current_chat()
    if not chat:
        return None, None
    return chat.get("id"), chat.get("title")


def _touch_file_read(path):
    """Отмечает: ТЕКУЩИЙ чат видел актуальное содержимое файла."""
    try:
        base = server_state._chats_dir()
        cid, _ = _current_chat_info()
        if base and cid and path:
            chat_store.touch_file_read(base, cid, path)
    except Exception:
        pass


def _create_overwrite_is_stale(action, project_root):
    """create_file поверх СУЩЕСТВУЮЩЕГО файла, который менял другой чат
    ПОСЛЕ того, как текущий чат в последний раз видел его содержимое, —
    опасен: модель молча сотрёт чужую работу. Возвращает текст системного
    сообщения для модели или None, если всё свежо."""
    path = action.get("path", "")
    try:
        abs_path = _resolve_safe_path(project_root, path)
    except Exception:
        return None
    if not os.path.isfile(abs_path):
        return None  # обычное создание нового файла — проверять нечего
    chat = server_state.get_current_chat()
    if not chat:
        return None
    others_ts = history.last_write_ts_by_others(project_root, path, chat.get("id"))
    if not others_ts:
        return None
    seen_ts = (chat.get("file_reads") or {}).get(path, 0)
    if seen_ts >= others_ts:
        return None
    return (
        f"[Система]: СТОП. Ты предлагаешь ПОЛНОСТЬЮ перезаписать файл {path}, "
        "но он изменялся из ДРУГОГО чата после того, как ты в последний раз видел его содержимое. "
        "Слепая перезапись уничтожит эти изменения. Сначала запроси этот файл через read_file, "
        "изучи актуальную версию и только потом предлагай правку (patch_file для точечных "
        "изменений или create_file, если полная замена всё ещё нужна)."
    )


def _deps_enrich_scene_action(action, candidate, path, project_root):
    """v47: анализ зависимостей для СЦЕНЫ, которая вот-вот запишется.
    Если в привязанных скриптах есть обработчики _on_..., которые нигде не
    подключены и трактуются ОДНОЗНАЧНО — тихо добавляем [connection] в сцену.
    Спорные случаи — только заметка модели, никаких блокировок."""
    try:
        new_text, added, notes = scene_deps.analyze_scene_action(candidate, path, project_root)
    except Exception:
        return
    if added and new_text != candidate:
        action["action"] = "create_file"
        action["content"] = new_text
        action.pop("search", None)
        action.pop("replace", None)
    msg_parts = []
    if added:
        msg_parts.append(
            "анализ зависимостей автоматически добавил в сцену " + path
            + " подключения сигналов: " + "; ".join(added)
            + ". Не добавляй их повторно"
        )
    if notes:
        msg_parts.append("заметки анализа зависимостей: " + "; ".join(notes[:4]))
    if msg_parts:
        server_state.queue_action_note("[Система: " + ". ".join(msg_parts) + ".]")


def _deps_note_script_action(candidate, path, project_root):
    """v47: анализ зависимостей для СКРИПТА: если сцены на диске уже
    используют этот скрипт, а в нём появился неподключённый обработчик —
    мягкая заметка модели (чужие файлы не правим автоматически)."""
    try:
        notes = scene_deps.analyze_script_action(candidate, path, project_root)
    except Exception:
        return
    if notes:
        server_state.queue_action_note(
            "[Система: анализ зависимостей — " + "; ".join(notes[:4]) + ".]"
        )


def _broken_encoding_note(action, kind, path):
    """Текст для модели, если в присланном фрагменте есть U+FFFD, иначе None.

    Проверяются ИМЕННО присланные поля (content/replace/search), а не итоговый
    текст файла: файл на диске мог быть побит раньше, и тогда виноват не этот
    ответ — требовать переделки за чужую поломку значит зацикливать модель.
    """
    for field in ("content", "replace", "search"):
        value = action.get(field)
        if isinstance(value, str) and "\ufffd" in value:
            return (
                "[Система]: в поле %s для %s пришли символы повреждённой "
                "кодировки (U+FFFD, в редакторе это «?» или пустой квадрат). "
                "Так теряются буквы, а какая именно потерялась — восстановить "
                "невозможно, поэтому действие НЕ применено. Пришли agent_action "
                "заново (%s для %s) целиком и без обрезанных фрагментов."
                % (field, path or "?", kind or "?", path or "?")
            )
    return None


def _lint_action_code(action, project_root, planned_paths=None):
    """Самопроверка кода ДО показа действия пользователю: гоняем лёгкий
    линтер по ИТОГОВОМУ тексту .gd-файла (каким он станет после create/patch).
    Возвращает текст системного сообщения для модели или None, если код чист."""
    kind = action.get("action")
    path = action.get("path", "") or ""
    # ПОБИТАЯ КОДИРОВКА ПРОВЕРЯЕТСЯ У ЛЮБОГО ФАЙЛА, а не только у .gd.
    #
    # Это не гипотетическая опасность, а уже случившаяся: в исходниках самого
    # аддона (main.py, parser_base.py, selfcheck.py, librarian.py и даже
    # agent_panel.gd) накопилось 55 таких мест — то есть 55 букв, стёртых
    # молча, включая текст «[Система]: Действие отклонено пользователем.»,
    # который пользователь видел в чате как набор вопросительных знаков.
    #
    # Откуда берётся: ответ модели читается из сети по частям, и декодирование
    # оборванного куска (errors="replace") превращает каждый недобранный байт
    # многобайтового символа в U+FFFD. Дальше текст записывается на диск как
    # совершенно правильный UTF-8 — поэтому НИ ОДНА проверка кодировки такой
    # файл не забракует, и заметить это можно только глазами.
    #
    # Чинить автозаменой нельзя: какая буква пропала, знает только модель.
    # Поэтому не «вычищаем» символ (это оставило бы слово без буквы), а
    # заставляем прислать фрагмент заново — sanitize_llm_text по той же причине
    # U+FFFD НЕ удаляет, хотя рядом удаляет U+FFFE и U+FFFF.
    broken = _broken_encoding_note(action, kind, path)
    if broken:
        return broken
    if tscn_lint.is_scene_path(path):
        return _lint_action_scene(action, project_root, kind, path, planned_paths=planned_paths)
    if not path.endswith(".gd"):
        return None
    if kind == "create_file":
        candidate = action.get("content", "") or ""
    elif kind == "patch_file":
        try:
            abs_path = _resolve_safe_path(project_root, path)
            with open(abs_path, "r", encoding="utf-8-sig", errors="replace") as f:
                disk = f.read()
        except Exception:
            return None
        norm = disk.replace("\r\n", "\n")
        search = (action.get("search", "") or "").replace("\r\n", "\n")
        replace = (action.get("replace", "") or "").replace("\r\n", "\n")
        if not search or norm.count(search) != 1:
            return None  # этим случаем занимается _validate_patch_against_disk
        candidate = norm.replace(search, replace, 1)
    else:
        return None
    try:
        problems = list(gd_lint.lint_gdscript(candidate))
    except Exception:
        problems = []
    try:
        problems += gd_api_check.check_api_usage(project_root, candidate, path, STATE.get("addon_dir"))
    except Exception:
        pass
    if not problems:
        _deps_note_script_action(candidate, path, project_root)
        return None
    # Все замечания уходят модели ОДНИМ сообщением, а не по одному: иначе
    # каждая мелочь стоила бы отдельного обращения к модели (по API — ещё и
    # отдельного оплаченного запроса). Список ограничен, но об остатке модель
    # предупреждается явно — иначе она считала бы, что исправила всё.
    shown = problems[:8]
    listing = "\n".join("- %s" % p for p in shown)
    if len(problems) > len(shown):
        listing += ("\n- …и ещё %d замечани(й) — исправь все перечисленные, "
                    "остальные придут следующей проверкой."
                    % (len(problems) - len(shown)))
    msg_head = "[Sistema]"
    return (
        "[" + "\u0421\u0438\u0441\u0442\u0435\u043c\u0430" + "]: \u0422\u0432\u043e\u0439 \u043a\u043e\u0434 \u0434\u043b\u044f \u0444\u0430\u0439\u043b\u0430 " + path + " \u043d\u0435 \u043f\u0440\u043e\u0448\u0451\u043b \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0443\u044e \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443. "
        + "\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u043b\u0441\u044f \u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0439 \u0442\u0435\u043a\u0441\u0442 \u0444\u0430\u0439\u043b\u0430 \u043f\u043e\u0441\u043b\u0435 \u043f\u0440\u0438\u043c\u0435\u043d\u0435\u043d\u0438\u044f \u0442\u0432\u043e\u0435\u0433\u043e \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u044f. \u041f\u0440\u043e\u0431\u043b\u0435\u043c\u044b:\n" + listing + "\n"
        + "\u0418\u0441\u043f\u0440\u0430\u0432\u044c \u043a\u043e\u0434 \u0438 \u043f\u0440\u0438\u0448\u043b\u0438 agent_action \u0437\u0430\u043d\u043e\u0432\u043e (" + kind + " \u0434\u043b\u044f " + path + "). "
        + "\u0415\u0441\u043b\u0438 \u0442\u044b \u043f\u0440\u0438\u0441\u043b\u0430\u043b \u043e\u0431\u0440\u0435\u0437\u0430\u043d\u043d\u044b\u0439 \u0444\u0440\u0430\u0433\u043c\u0435\u043d\u0442 \u2014 \u043f\u0440\u0438\u0448\u043b\u0438 \u0435\u0433\u043e \u0446\u0435\u043b\u0438\u043a\u043e\u043c."
    )


def _lint_action_scene(action, project_root, kind, path, planned_paths=None):
    """Самопроверка сцены (.tscn/.scn) до показа действия пользователю.
    Механически исправимые вещи (load_steps) правит и применяет к action тихо —
    модель этого даже не увидит. Недетерминированные структурные проблемы
    (битые ссылки, несуществующий parent, дубли, чужие типы) — как и для кода,
    возвращаются модели на самоисправление."""
    if kind == "create_file":
        candidate = action.get("content", "") or ""
    elif kind == "patch_file":
        try:
            abs_path = _resolve_safe_path(project_root, path)
            with open(abs_path, "r", encoding="utf-8-sig", errors="replace") as f:
                disk = f.read()
        except Exception:
            return None
        norm = disk.replace("\r\n", "\n")
        search = (action.get("search", "") or "").replace("\r\n", "\n")
        replace = (action.get("replace", "") or "").replace("\r\n", "\n")
        if not search or norm.count(search) != 1:
            return None  # этим случаем занимается _validate_patch_against_disk
        candidate = norm.replace(search, replace, 1)
    else:
        return None
    try:
        fixed, problems = tscn_lint.lint_and_fix_tscn(candidate, project_root, STATE.get("addon_dir"), planned_paths=planned_paths)
    except Exception:
        return None
    if fixed != candidate:
        # механически исправлено (сейчас — только load_steps). Применяем тихо, не беспокоя
        # модель: для patch_file проще переключиться в полную перезапись файла готовым
        # итоговым текстом — результат на диске идентичен, а место исправления (заголовок
        # load_steps) могло оказаться вне search/replace окна.
        action["action"] = "create_file"
        action["content"] = fixed
        action.pop("search", None)
        action.pop("replace", None)
        candidate = fixed
    if not problems:
        _deps_enrich_scene_action(action, candidate, path, project_root)
        try:
            if minilich.is_enabled(project_root):
                minilich.note_scene_ok(project_root, path, candidate)
        except Exception:
            pass
        return None
    # mini-lich: локальная попытка починки сцены без большой модели (только если галочка включена).
    # Любой результат mini-lich обязан заново пройти линтер без единой проблемы —
    # иначе штатно возвращаем задачу большой модели (испортить сцену он не может).
    try:
        _ml_enabled = minilich.is_enabled(project_root)
    except Exception:
        _ml_enabled = False
    if _ml_enabled:
        try:
            _ml_training = minilich.is_training_mode(project_root)
        except Exception:
            _ml_training = True
        try:
            minilich.note_scene_bad(path, candidate, problems)
            healed = minilich.try_fix_scene(candidate, problems, project_root, STATE.get("addon_dir"))
        except Exception:
            healed = None
        if healed and _ml_training:
            print(u"--> [mini-lich] (обучение) сам починил сцену — но в теневом режиме применяем ответ большой модели")
            healed = None
        if healed:
            action["action"] = "create_file"
            action["content"] = healed
            action.pop("search", None)
            action.pop("replace", None)
            _deps_enrich_scene_action(action, healed, path, project_root)
            print("--> [mini-lich] \u0441\u0446\u0435\u043d\u0430 \u043f\u043e\u0447\u0438\u043d\u0435\u043d\u0430 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e \u0431\u0435\u0437 \u0431\u043e\u043b\u044c\u0448\u043e\u0439 \u043c\u043e\u0434\u0435\u043b\u0438: %s" % path)
            return None
    listing = "\n".join("- %s" % p for p in problems[:8])
    return (
        "[" + "\u0421\u0438\u0441\u0442\u0435\u043c\u0430" + "]: \u0442\u0432\u043e\u044f \u0441\u0446\u0435\u043d\u0430 \u0434\u043b\u044f \u0444\u0430\u0439\u043b\u0430 " + path + " \u043d\u0435 \u043f\u0440\u043e\u0448\u043b\u0430 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0443\u044e \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443 \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u044b. "
        + "\u041f\u0440\u043e\u0432\u0435\u0440\u044c \u0438\u0442\u043e\u0433\u043e\u0432\u044b\u0439 \u0442\u0435\u043a\u0441\u0442 \u0441\u0446\u0435\u043d\u044b. \u041f\u0440\u043e\u0431\u043b\u0435\u043c\u044b:\n" + listing + "\n"
        + "\u0418\u0441\u043f\u0440\u0430\u0432\u044c \u0441\u0446\u0435\u043d\u0443 \u0438 \u043f\u0440\u0438\u0448\u043b\u0438 agent_action \u0437\u0430\u043d\u043e\u0432\u043e (create_file \u0434\u043b\u044f " + path + "). "
        + "\u041d\u043e\u0432\u044b\u0435 [sub_resource]/[ext_resource] \u043e\u0431\u044a\u044f\u0432\u043b\u044f\u0442\u044c \u041c\u041e\u0416\u041d\u041e \u2014 \u044d\u0442\u043e \u043d\u043e\u0440\u043c\u0430\u043b\u044c\u043d\u044b\u0439 \u043f\u0443\u0442\u044c \u0434\u043b\u044f \u043d\u043e\u0432\u043e\u0433\u043e \u043a\u043e\u043d\u0442\u0435\u043d\u0442\u0430 (uid \u0443 \u043d\u043e\u0432\u044b\u0445 \u0440\u0435\u0441\u0443\u0440\u0441\u043e\u0432 \u0443\u043a\u0430\u0437\u044b\u0432\u0430\u0442\u044c \u043d\u0435 \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u043e: Godot \u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u0435\u0442 \u0435\u0433\u043e \u0441\u0430\u043c \u043f\u0440\u0438 \u043f\u0435\u0440\u0432\u043e\u043c \u043e\u0442\u043a\u0440\u044b\u0442\u0438\u0438). \u0413\u043b\u0430\u0432\u043d\u043e\u0435: \u043e\u0431\u044a\u044f\u0432\u0438 \u0440\u0435\u0441\u0443\u0440\u0441 \u0432 \u0444\u0430\u0439\u043b\u0435 \u0420\u0410\u041d\u042c\u0428\u0415 \u043f\u0435\u0440\u0432\u043e\u0433\u043e \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u044f \u0438 \u0441\u0441\u044b\u043b\u0430\u0439\u0441\u044f \u043d\u0430 \u0435\u0433\u043e id \u0434\u043e\u0441\u043b\u043e\u0432\u043d\u043e, \u0430 \u0443\u0437\u0435\u043b-parent \u043e\u0431\u044a\u044f\u0432\u043b\u044f\u0439 \u0432\u044b\u0448\u0435 \u0435\u0433\u043e \u0434\u0435\u0442\u0435\u0439 (\u0432\u044b\u0437\u043e\u0432\u0438 list_scene, \u0435\u0441\u043b\u0438 \u043d\u0443\u0436\u043d\u043e \u0443\u0432\u0438\u0434\u0435\u0442\u044c \u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u043e\u0435 \u0441\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435 \u0441\u0446\u0435\u043d\u044b)."
    )


def _guess_step_path(raw_step_text):
    """Извлекает 'path' из СЫРОГО (возможно, невалидного JSON) текста ОДНОГО
    шага плана — только для сообщений пользователю/модели о том, какой из
    шагов не распознан (парсить сам JSON тут не пытаемся)."""
    if not raw_step_text:
        return None
    m = _re.search(r'"path"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_step_text)
    if not m:
        return None
    try:
        return _json.loads('"' + m.group(1) + '"')
    except Exception:
        return m.group(1)


# ---------------------------------------------------------------------------
# Self-heal: битый JSON или несовпадающий patch чиним без участия пользователя.
#
# v44: раньше один БИТЫЙ шаг плана (action=plan) ронял ВЕСЬ план целиком —
# parse_action_json не мог разобрать общий JSON, если хотя бы один шаг
# содержал несогласованное экранирование кавычек (типичный случай — большой
# .tscn-контент, где часть кавычек внутри значения экранирована, а часть —
# нет). Модель получала общий "пришли всё заново", план терялся целиком, и
# пользователь оставался без уже готового кода — даже если 3 из 4 шагов были
# полностью корректны.
#
# Начиная с v44: если сырой ответ ПОХОЖ на action=plan (см.
# parser_base.parse_plan_lenient), мы разбираем каждый шаг из "steps": [...]
# ПО ОТДЕЛЬНОСТИ (с учётом починки несогласованных кавычек — см.
# parser_base._repair_unescaped_inner_quotes). Все шаги, которые распознались
# нормально, сразу принимаются (lenient_good). По каждому ОСТАВШЕМУСЯ битому
# шагу (lenient_bad) отправляется ТОЧЕЧНЫЙ fix-prompt: модели называют уже
# принятые пути (чтобы не путать её и не заставлять присылать план заново
# целиком), номер/путь именно ПРОБЛЕМНОГО шага и точную причину разбора —
# и просят переписать ТОЛЬКО этот один шаг одним корректным JSON-объектом
# (без обёртки action=plan). Каждая такая попытка расходует ОДНУ попытку из
# общего бюджета MAX_ACTION_FIX_RETRIES (общего с обычным самоисцелением
# create_file/patch_file). Если шаг починился — он переходит в lenient_good;
# если нет — на него записывается причина отказа, и обрабатывается следующий
# битый шаг по кругу, пока бюджет не закончится.
#
# Если после этого lenient_bad опустел — план собирается заново из
# lenient_good, и обработка продолжается как обычный action=plan (дальше
# план валидируется/подтверждается пользователем как всегда).
#
# Если бюджет попыток исчерпан, а lenient_bad всё ещё не пуст, но
# lenient_good не пуст — план всё равно собирается из того, что удалось
# распознать (лучше отдать пользователю частичный результат, чем ничего), а
# в text дописывается явное предупреждение: сколько шагов принято, сколько и
# какие (номер + путь, если удалось угадать) отброшены и почему, с советом
# попросить модель прислать отброшенные шаги отдельным сообщением.
#
# Если сырой ответ вообще не похож на план, или из него не удалось вытащить
# ни одного шага (ни good, ни bad) — ведём себя как раньше: обычный общий
# fix-prompt с просьбой переслать ВСЁ действие заново.
# ---------------------------------------------------------------------------

def _lenient_resend_note(action, msg):
    """v86.22 (автодосыл после терпимого разбора): если тело этого действия
    было восстановлено терпимым разбором v86.18 (без ===END_МЕТКА=== —
    возможно, оборвано при передаче) и файл не прошёл проверку — не просим
    модель «чинить код» (она будет латать обрезанный кусок), а прямо
    говорим прислать содержимое ЦЕЛИКОМ заново. Для обычных действий
    (без пометки от parser_base) сообщение не меняется."""
    if not isinstance(action, dict) or msg is None:
        return msg
    fields = action.get("lenient_transfer_fields")
    if not fields:
        return msg
    return msg + (
        "\n[Система]: ВАЖНО: поле(я) %s этого действия были восстановлены из "
        "ОБОРВАННОЙ передачи (закрывающий ===END_МЕТКА=== не был получен), "
        "поэтому содержимое могло оборваться на середине. НЕ пытайся точечно "
        "чинить присланный кусок — пришли это действие заново ЦЕЛИКОМ, с полным "
        "содержимым файла, и обязательно заверши тело строкой ===END_МЕТКА=== "
        "и весь ответ — маркером ===DONE===."
    ) % ", ".join(str(f) for f in fields)


def _reply_with_self_heal(prompt, project_root):
    # Cancellation ends the entire repair chain, not just one backend call.
    try:
        return _reply_with_self_heal_impl(prompt, project_root)
    except parser_base.ParserCancelled:
        return "[Остановлено] Запрос прерван кнопкой «Стоп».", None


def _reply_with_self_heal_impl(prompt, project_root):
    text, action = _reply(prompt)
    retries = 0
    while retries < MAX_ACTION_FIX_RETRIES:
        if action and action.get("action") == "parse_error":
            raw = action.get("raw")
            lenient = parser_base.parse_plan_lenient(raw)
            has_any_step = bool(lenient and (lenient.get("good_steps") or lenient.get("bad_steps")))
            if not has_any_step:
                retries += 1
                print(f"--> [self-heal] Битый JSON action, попытка {retries}/{MAX_ACTION_FIX_RETRIES}")
                fix_prompt = (
                    "[Система]: Твой предыдущий блок agent_action содержал невалидный JSON "
                    "и не был обработан. Пришли ТО ЖЕ действие заново одним корректным JSON-блоком "
                    "agent_action, строго экранируя переносы строк (\\n) и кавычки (\\\") внутри "
                    "строковых значений. Никакого текста вне JSON-блока."
                )
                text, action = _reply(fix_prompt)
                continue
            lenient_good = list(lenient["good_steps"])
            lenient_bad = list(lenient["bad_steps"])
            print(f"--> [self-heal] план распознан частично: {len(lenient_good)} шаг(ов) ок, "
                  f"{len(lenient_bad)} шаг(ов) битых — пробую точечно починить.")
            accepted_paths = [s["step"].get("path", "") for s in lenient_good]
            dropped = []
            while lenient_bad and retries < MAX_ACTION_FIX_RETRIES:
                bad = lenient_bad.pop(0)
                retries += 1
                bad_path = _guess_step_path(bad["raw"]) or "?"
                print(f"--> [self-heal] точечная починка шага (индекс {bad['index']}, "
                      f"путь {bad_path}), попытка {retries}/{MAX_ACTION_FIX_RETRIES}: {bad['error']}")
                accepted_note = (
                    ("Уже принятые шаги (НЕ присылай их повторно): " + ", ".join(p for p in accepted_paths if p))
                    if accepted_paths else "Других шагов пока не принято."
                )
                fix_prompt = (
                    "[Система]: В твоём последнем плане (action=plan) шаг №%d содержит НЕвалидный "
                    "JSON и не был обработан (остальные корректные шаги уже приняты ОТДЕЛЬНО). "
                    "Путь этого шага: %s. Точная причина ошибки разбора: %s. %s "
                    "Пришли ТОЛЬКО этот ОДИН шаг заново одним корректным JSON-ОБЪЕКТОМ действия "
                    "(create_file/patch_file/move_file — без обёртки action=plan и без остальных "
                    "шагов), строго экранируя переносы строк (\\n) и кавычки (\\\") внутри строковых "
                    "значений."
                ) % (bad["index"] + 1, bad_path, bad["error"], accepted_note)
                fix_text, fix_action = _reply(fix_prompt)
                if isinstance(fix_action, dict) and fix_action.get("action") in PLAN_ALLOWED_ACTIONS:
                    lenient_good.append({"index": bad["index"], "step": fix_action})
                    accepted_paths.append(fix_action.get("path", ""))
                    print(f"--> [self-heal] шаг {bad['index'] + 1} успешно починен точечно.")
                else:
                    reason = (
                        (fix_action or {}).get("error") if isinstance(fix_action, dict) else None
                    ) or bad["error"] or "не удалось распознать корректное действие"
                    dropped.append({"index": bad["index"], "path": bad_path, "error": reason})
                    print(f"--> [self-heal] шаг {bad['index'] + 1} НЕ починен точечно: {reason}")
            for bad in lenient_bad:
                dropped.append({
                    "index": bad["index"],
                    "path": _guess_step_path(bad["raw"]) or "?",
                    "error": bad["error"] + " (бюджет попыток самоисцеления исчерпан)",
                })
            if not lenient_good:
                retries += 1
                print(f"--> [self-heal] ни один шаг плана не удалось восстановить — откат на общий fix-prompt, попытка {retries}/{MAX_ACTION_FIX_RETRIES}")
                fix_prompt = (
                    "[Система]: Твой предыдущий блок agent_action (план) содержал невалидный JSON "
                    "и не был обработан целиком. Пришли ТО ЖЕ действие заново одним корректным "
                    "JSON-блоком agent_action, строго экранируя переносы строк (\\n) и кавычки (\\\") "
                    "внутри строковых значений. Никакого текста вне JSON-блока."
                )
                text, action = _reply(fix_prompt)
                continue
            ordered_steps = [s["step"] for s in sorted(lenient_good, key=lambda s: s["index"])]
            action = {
                "action": "plan",
                "description": lenient.get("description", ""),
                "steps": ordered_steps,
                "total": len(ordered_steps),
            }
            if dropped:
                listing = "\n".join(
                    "- шаг %d (%s): %s" % (d["index"] + 1, d["path"], d["error"]) for d in dropped
                )
                warning = (
                    "[Система]: \u26a0 Восстановлено частично: %d шаг(ов) плана принято, %d шаг(ов) "
                    "отброшено из-за повреждённого JSON, который не удалось починить даже точечно:\n%s\n"
                    "Попроси модель прислать отброшенные шаги отдельным сообщением, если они нужны."
                    % (len(ordered_steps), len(dropped), listing)
                )
                text = (text + "\n\n" + warning).strip() if text else warning
            else:
                print(f"--> [self-heal] план полностью восстановлен точечными починками: "
                      f"{len(ordered_steps)} шаг(ов).")
            continue
        if action and action.get("action") == "patch_file":
            ok, real_content, err = _validate_patch_against_disk(action, project_root)
            if ok:
                lint_msg = _lint_action_code(action, project_root)
                if lint_msg is None:
                    break
                retries += 1
                print(f"--> [self-heal] Код в patch_file не прошёл проверку, попытка {retries}/{MAX_ACTION_FIX_RETRIES}")
                text, action = _reply(_lenient_resend_note(action, lint_msg))
                continue
            retries += 1
            path = action.get("path", "")
            print(f"--> [self-heal] patch_file не совпал с диском ({err}), попытка {retries}/{MAX_ACTION_FIX_RETRIES}")
            fence = "`" * 3
            if real_content is None:
                fix_prompt = (
                    f"[Система]: Не удалось применить patch_file к {path}: {err}. "
                    f"Проверь путь к файлу и предложи корректное действие заново."
                )
            else:
                fix_prompt = (
                    f"[Система]: Блок 'search' в твоём patch_file не совпадает с реальным "
                    f"содержимым файла {path} прямо сейчас (причина: {err}). "
                    f"Вот АКТУАЛЬНОЕ содержимое файла на диске:\n{fence}\n{real_content}\n{fence}\n"
                    f"Пришли новый agent_action patch_file, где 'search' дословно совпадает "
                    f"с текстом файла выше."
                )
                # Модель только что увидела АКТУАЛЬНОЕ содержимое файла с диска.
                _touch_file_read(path)
            text, action = _reply(fix_prompt)
            continue
        if action and action.get("action") == "create_file":
            stale_msg = _create_overwrite_is_stale(action, project_root)
            if stale_msg is None:
                lint_msg = _lint_action_code(action, project_root)
                if lint_msg is None:
                    break
                retries += 1
                print(f"--> [self-heal] Код в create_file не прошёл проверку, попытка {retries}/{MAX_ACTION_FIX_RETRIES}")
                text, action = _reply(_lenient_resend_note(action, lint_msg))
                continue
            retries += 1
            print(f"--> [self-heal] create_file поверх файла, изменённого другим чатом, попытка {retries}/{MAX_ACTION_FIX_RETRIES}")
            text, action = _reply(stale_msg)
            continue
        # Любое другое действие или его отсутствие — проверять нечего.
        break
    # v46: бюджет самоисцеления мог закончиться на ВСЁ ЕЩЁ битом write-действии
    # (последний ответ модели после выхода из цикла не перепроверялся). Раньше
    # такое действие уходило дальше как pending_action: пользователь подтверждал
    # заведомо сломанный файл, а модель (и пользователь по её тексту) считали
    # правку применённой, хотя файл мог остаться прежним. Теперь действие
    # снимается, а пользователь и модель получают явное «файл НЕ изменён».
    if action and action.get("action") in ("create_file", "patch_file"):
        try:
            final_lint = _lint_action_code(action, project_root)
        except Exception:
            final_lint = None
        if final_lint is not None:
            kind = action.get("action")
            path = action.get("path", "")
            warn = (
                "[Система]: ⚠ Действие %s для %s ОТБРОШЕНО: файл НЕ был изменён. "
                "Модель за %d попыт(ок) так и не прислала версию, проходящую автоматическую "
                "проверку. Повторите запрос (можно попросить модель прислать файл целиком заново)."
                % (kind, path, MAX_ACTION_FIX_RETRIES)
            )
            server_state.queue_action_note(
                "[Система: твоё последнее действие %s для %s было ОТБРОШЕНО, файл НЕ изменён — "
                "присланная версия так и не прошла автоматическую проверку. Не считай эти правки "
                "применёнными: файл на диске остался прежним.]" % (kind, path)
            )
            text = (text + "\n\n" + warn).strip() if text else warn
            action = None
    return text, action


def _validate_patch_against_disk(action, project_root):
    """Проверяет, что action['search'] реально присутствует (и уникален)
    в файле на диске ПРЯМО СЕЙЧАС — до показа pending_action пользователю.
    Возвращает (ok, real_file_content_or_None, error_or_None)."""
    path = action.get("path", "")
    search = action.get("search", "") or ""
    try:
        abs_path = _resolve_safe_path(project_root, path)
    except Exception as e:
        return False, None, str(e)
    if not os.path.isfile(abs_path):
        return False, None, f"Файл не найден: {path}"
    with open(abs_path, "r", encoding="utf-8-sig", errors="replace") as f:
        content = f.read()
    norm_content = content.replace("\r\n", "\n")
    norm_search = search.replace("\r\n", "\n")
    if not norm_search.strip():
        return False, content, "search пустой"
    occurrences = norm_content.count(norm_search)
    if occurrences == 1:
        return True, content, None
    if occurrences > 1:
        return False, content, "search встречается больше одного раза (не уникален)"
    return False, content, "search не найден в текущем содержимом файла"


def _format_search_results(query, results, truncated):
    """Собирает ОДНО сообщение для модели с результатами поиска по проекту."""
    fence = "`" * 3
    if not results:
        return ("[Система]: Поиск по проекту «%s» — совпадений НЕ найдено ни в одном файле проекта." % query)
    head = "[Система]: Поиск по проекту «%s» — совпадений: %d" % (query, len(results))
    if truncated:
        head += " (показаны первые, список обрезан — уточни запрос)"
    parts = [head + "."]
    for r in results:
        parts.append("%s (строка %d):\n%s\n%s\n%s" % (r["path"], r["line"], fence, r["snippet"], fence))
    parts.append("Номера строк — только для ориентира. Для patch_file бери блок кода дословно через read_file: сниппеты выше ОБРЕЗАНЫ и начинаются с номеров строк.")
    return "\n\n".join(parts)


def _refresh_fs_snapshot(project_root):
    """Пересъёмка отпечатка файлов проекта. Вызывается после КАЖДОЙ записи
    самого агента, чтобы его собственные правки не считались «внешними»."""
    if not project_root:
        return
    try:
        # v88.5: prev — чтобы не перехэшировать файлы, чьи mtime+size не менялись
        STATE["fs_snapshot"] = snapshot_files(project_root, prev=STATE.get("fs_snapshot"))
        STATE["fs_snapshot_root"] = project_root
    except Exception:
        pass


FILE_CACHE_MAX_BYTES = 300000  # файлы больше этого в кэш точечных diff не попадают


def _rel_from_godot_path(godot_path):
    return str(godot_path or "").replace("res://", "").strip("/").replace(chr(92), "/")


def _remember_file(project_root, godot_path):
    """Кэширует содержимое файла, которое видела модель (после чтения или
    своей записи): при ручной правке пользователя модель получит ТОЧЕЧНЫЙ
    diff, а не команду перечитать весь файл (экономия токенов)."""
    try:
        abs_path = _resolve_safe_path(project_root, godot_path)
        if not os.path.isfile(abs_path) or os.path.getsize(abs_path) > FILE_CACHE_MAX_BYTES:
            return
        with open(abs_path, "r", encoding="utf-8-sig", errors="replace") as fh:
            content = fh.read()
    except Exception:
        return
    cache = STATE.get("file_cache")
    if cache is None:
        cache = {}
        STATE["file_cache"] = cache
    cache[_rel_from_godot_path(godot_path)] = content


def _forget_file(godot_path):
    cache = STATE.get("file_cache")
    if cache:
        cache.pop(_rel_from_godot_path(godot_path), None)


def _external_changes_note(project_root):
    """Сообщение модели о файлах, изменённых ВНЕ агента с прошлого обмена
    (пользователь удалил сцену, поменял скрипт руками, что-то добавил), или "".
    Заодно обновляет снапшот, чтобы одно изменение не сообщалось дважды."""
    if not project_root:
        return ""
    old = STATE.get("fs_snapshot")
    if old is None or STATE.get("fs_snapshot_root") != project_root:
        _refresh_fs_snapshot(project_root)
        return ""
    try:
        new = snapshot_files(project_root, prev=old)
    except Exception:
        return ""
    STATE["fs_snapshot"] = new
    STATE["fs_snapshot_root"] = project_root
    added, changed, deleted = diff_snapshots(old, new)
    cache = STATE.get("file_cache") or {}
    diffs = {}
    for rel in changed:
        old_content = cache.get(rel)
        if old_content is None:
            continue
        try:
            with open(os.path.join(project_root, rel), "r", encoding="utf-8", errors="replace") as fh:
                new_content = fh.read()
        except Exception:
            continue
        d, n_lines = unified_diff_text(old_content, new_content, rel)
        if d is not None:
            diffs[rel] = (d, n_lines)
            cache[rel] = new_content   # модель узнаёт новое содержимое из diff
        else:
            cache.pop(rel, None)       # правка слишком большая — модель перечитает файл
    for rel in deleted:
        cache.pop(rel, None)
    try:
        # v105: внешние правки тоже попадают в индекс Библиотекаря точечно
        librarian.note_files_changed(project_root, list(added) + list(changed), deleted=list(deleted))
    except Exception:
        pass
    return format_fs_changes(added, changed, deleted, diffs=diffs)


def _short_godot_version(raw):
    """v87.9: «4.4.1.stable.official.49a5bc7b6» -> «4.4.1» — в мега-промпт идёт
    только числовая часть версии движка (major.minor[.patch])."""
    parts = []
    for p in str(raw or "").split("."):
        if p.isdigit():
            parts.append(p)
        else:
            break
    return ".".join(parts)


def _build_priming_context(project_root):
    """Мега-промпт: умное дерево (полное для маленького проекта, сводка по
    папкам для большого) + описание архитектуры проекта. Если проект пустой —
    агент сам создаёт стандартную архитектуру для игр."""
    try:
        created = ensure_standard_architecture(project_root)
    except Exception:
        created = []
    if created:
        print("--> Проект пуст: создана стандартная архитектура (%d папок)" % len(created))
    try:
        arch = describe_architecture(project_root)
    except Exception:
        arch = ""
    if created:
        arch = ("Проект был пуст — агент УЖЕ создал стандартную структуру папок для игры:\n"
                + "\n".join("- " + d for d in created)
                + "\nКлади скрипты в res://src/scripts/, сцены в res://src/scenes/, "
                  "автозагрузки в res://src/autoload/, ассеты в res://assets/."
                + (("\n" + arch) if arch.strip() else ""))
    if not arch.strip():
        arch = "(явной архитектуры не обнаружено — ориентируйся на структуру ниже и не разводи хаос в корне)"
    tree, compact = build_project_overview(project_root, only_exts=CODE_EXTS,
                                           max_entries=PRIME_TREE_MAX_ENTRIES,
                                           compact_threshold=PRIME_COMPACT_THRESHOLD)
    if compact:
        print("--> Проект большой: в мега-промпт идёт компактная сводка по папкам вместо полного дерева")
    _refresh_fs_snapshot(project_root)  # созданные папки — не «внешние» изменения
    # v87.9: в промпт подставляется ТОЧНАЯ версия Godot проекта (правила и API
    # между версиями меняются): сперва версия из /init (плагин шлёт
    # Engine.get_version_info()), затем версия из кеша API (плагин обновляет его
    # при старте), и только если ничего нет — «4», как раньше.
    godot_version = _short_godot_version(STATE.get("godot_version"))
    if not godot_version:
        try:
            godot_version = _short_godot_version(
                gd_api_cache.get_cached_version(project_root, STATE.get("addon_dir")))
        except Exception:
            godot_version = ""
    if not godot_version:
        godot_version = "4"
    return (PRIMING_TEMPLATE.replace("{tree}", tree)
            .replace("{architecture}", arch)
            .replace("{godot_version}", godot_version))


# ---------------------------------------------------------------------------
# HTTP-эндпоинты
# ---------------------------------------------------------------------------

@app.route('/init', methods=['POST'])
def init_session():
    if not server_state.try_begin_navigation():
        return jsonify({"error": "Агент обрабатывает запрос; синхронизация отложена.",
                        "code": "busy"}), 409
    # Editor writes execute between HTTP requests. Admission alone does not
    # protect their reserved history and capability tokens from a reset.
    if any(STATE.get(key) is not None for key in (
            "pending_scene_action", "pending_project_settings_action",
            "pending_resource_action", "pending_transaction",
            "pending_runtime_request", "pending_runtime_check")):
        return jsonify({"error": "Сначала завершите или отклоните ожидающую операцию.",
                        "code": "pending_operation"}), 409
    data = request.json or {}
    STATE["project_root"] = data.get('project_root')
    # v87.9: точная версия движка для мега-промпта (плагин шлёт её в /init).
    _gv = str(data.get("godot_version") or "").strip()
    if _gv:
        STATE["godot_version"] = _gv
    _apply_session_context(data)
    STATE["pending_action"] = None
    STATE["pending_refactor"] = None
    STATE["pending_scene_action"] = None
    STATE["pending_project_settings_action"] = None
    STATE["pending_resource_action"] = None
    STATE["pending_validation"] = None
    STATE["pending_transaction"] = None
    STATE["pending_batch"] = None
    STATE["action_notes"] = {}  # v45: словарь chat_id -> заметка, а не одна общая строка
    STATE["pending_log_report"] = None
    STATE["editor_context"] = None
    reset_runtime_turn(runtime_debug.normalize_status(data.get("runtime_status")))
    if STATE.get("fs_snapshot") is None or STATE.get("fs_snapshot_root") != STATE["project_root"]:
        _refresh_fs_snapshot(STATE["project_root"])
    reinit = bool(data.get("reinit", False))
    if reinit:
        _save_primed(STATE["project_root"], False)
        STATE["is_primed"] = False
        print(f"\n---> РЕИНИЦИАЛИЗАЦИЯ: {STATE['project_root']} (дерево будет отправлено заново)")
    else:
        STATE["is_primed"] = _load_primed(STATE["project_root"])
        print(f"\n---> Проект синхронизирован: {STATE['project_root']} (primed={STATE['is_primed']})")
    _ensure_current_chat("")
    _sync_chat_after_reply()
    return jsonify({"success": True, "message": "Локальная синхронизация успешна.", "primed": STATE["is_primed"]})


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    prompt = data.get('prompt', '')
    project_root = data.get('project_root')
    old_fs_snapshot = STATE.get("fs_snapshot")
    old_fs_snapshot_root = STATE.get("fs_snapshot_root")

    if not server_state.try_begin_turn_exchange():
        return jsonify({"error": "Агент уже обрабатывает запрос или переключает чат.",
                        "code": "busy"}), 409

    requested_chat_id = str(data.get("chat_id") or "").strip()
    current_chat_id = str(STATE.get("current_chat_id") or "")
    if requested_chat_id and requested_chat_id != current_chat_id:
        return jsonify({"error": "Открытый чат изменился до отправки сообщения.",
                        "code": "chat_changed"}), 409
    turn_chat_id = requested_chat_id or current_chat_id
    if turn_chat_id:
        server_state.bind_turn_chat(turn_chat_id)

    if STATE["pending_action"] is not None:
        return jsonify({"error": "Есть неподтверждённое действие агента."}), 409
    if STATE["pending_batch"] is not None:
        return jsonify({"error": "Есть неподтверждённые запросы файлов агента."}), 409

    _apply_session_context(data)
    if requested_chat_id:
        base = server_state._chats_dir()
        if not base or chat_store.find_chat(base, requested_chat_id) is None:
            return jsonify({"error": "Чат для отправки сообщения не найден.",
                            "code": "chat_not_found"}), 404
    STATE["editor_context"] = editor_context.normalize_snapshot(
        data.get("editor_context"))
    reset_runtime_turn(runtime_debug.normalize_status(data.get("runtime_status")), increment=True)
    STATE["pending_log_report"] = None  # новое сообщение отменяет неотправленный отчёт
    STATE["battle_choice_summary"] = None
    STATE["plan_parts"] = None  # незавершённые части плана от прошлого обмена сбрасываются
    # Системный блок для API-режима пересобирается один раз на сообщение
    # пользователя: внутри хода он обязан быть НЕИЗМЕННЫМ (иначе не работает
    # кэш промпта у провайдера), а между ходами — свежим (дерево проекта могло
    # измениться после create_file/move_file).
    _drop_api_system_cache()
    # Бюджет повторов тоже принадлежит ходу, а не запросу: внутри хода их
    # будет несколько (самоисцеление, дочитывание файлов, шаги плана), и без
    # общего потолка флапающий провайдер запирал бы редактор на часы.
    _reset_retry_budget()
    # Каждое НОВОЕ сообщение пользователя заново решает, разрешены ли в этом ходе действия над
    # аддонами (res://addons/...) — только когда он сам упомянул аддон/addon в тексте. Сбрасывается и
    # задаётся заново на каждое такое сообщение, а не один раз, чтобы доступ к аддонам не застревал навсегда.
    STATE["addon_intent"] = bool(_ADDON_INTENT_RE.search(prompt or ""))
    current_root = STATE.get("project_root")
    ensured_chat = _ensure_current_chat(prompt)
    if not turn_chat_id and ensured_chat is not None:
        turn_chat_id = str(ensured_chat.get("id") or "")
        if turn_chat_id:
            server_state.bind_turn_chat(turn_chat_id)
    server_state.begin_turn_transcript(turn_chat_id)
    # Страховка: если история ТЕКУЩЕГО чата пуста — это первое сообщение,
    # и мега-промпт нужен ВСЕГДА: глобальный флаг мог остаться от старого чата
    # или подгрузиться с диска при /init уже ПОСЛЕ создания нового чата.
    _cur_chat = server_state.get_current_chat()
    if (_cur_chat is not None and not _cur_chat.get("transcript")
            and not _cur_chat.get("primed")):
        # v104.2: страховка теперь учитывает и флаг primed самой записи чата:
        # раньше пустой ПАНЕЛЬНЫЙ транскрипт (например, запись чата
        # пересоздана после перезапуска сервера) заново слал мега-промпт
        # в чат, где на САЙТЕ он уже есть (репорт 23.07: «мегапромпт
        # прислался ещё раз, хотя не менялся»).
        STATE["is_primed"] = False
    if not data.get("ignore_site_mismatch"):
        mm = server_state.site_mismatch_for_current()
        if mm:
            return jsonify({"site_mismatch": True,
                            "expected_url": mm["expected_url"],
                            "site": mm["site"],
                            "prompt": prompt})
    _remember("user", prompt)

    try:
        # v45: заметка отдаётся только тому же чату, где произошло действие/откат —
        # другие чаты (в т.ч. только созданные) её НЕ видят.
        note = server_state.peek_action_note_for_current()
        if note:
            prompt = f"{note}\n\n{prompt}"

        # Сводка «что изменилось, пока чат был неактивен» (готовится при
        # открытии чата, отправляется ОДИН раз с первым сообщением).
        stale = server_state.peek_stale_note_for_current()
        if stale:
            prompt = f"{stale}\n\n{prompt}"

        # Файлы, изменённые ВНЕ агента (пользователь удалил сцену, поменял
        # скрипт руками...) — модель узнаёт об этом вместе с этим сообщением.
        ext_note = _external_changes_note(current_root)
        if ext_note:
            print("--> Обнаружены внешние изменения файлов проекта, сообщаем модели")
            prompt = f"{ext_note}\n\n{prompt}"

        prompt, context_sizes = editor_context.attach_to_prompt(
            prompt, STATE.get("editor_context"))
        prompt = runtime_debug.attach_status(prompt, STATE.get("runtime_status"))
        if context_sizes.get("total"):
            sizes = ", ".join("%s=%d" % (key, context_sizes[key])
                              for key in sorted(context_sizes))
            print("--> Editor context v1: " + sizes)

        # v104.2: источник истины про мега-промпт — запись САМОГО чата, а не
        # глобальный флаг проекта (тот перетирается при создании/открытии
        # других чатов и перезапусках сервера) — репорт 23.07: мега-промпт
        # улетал повторно в чат, где он уже есть.
        from agent_prompts import PROMPT_HASH as _ph
        if (not STATE.get("is_primed", False)
                and server_state.chat_already_primed(_ph)):
            STATE["is_primed"] = True
            _save_primed(current_root, True)
            print("--> Чат уже обучен мега-промптом этой версии — повторная отправка не нужна (v104.2).")

        if server_state.current_chat_is_api():
            # По API мега-промпт уходит ОТДЕЛЬНЫМ системным сообщением в
            # КАЖДОМ запросе — это делает ApiBackend через _api_system_text().
            # Значит в текст запроса его подмешивать нельзя, иначе он уедет
            # дважды и удвоит расход токенов. Флаг is_primed («дерево уже
            # отправлено») здесь смысла не имеет: по API нет переписки на
            # сайте, где что-то могло бы «остаться» с прошлого раза.
            print(f"\n---> Отправка по API ({len(prompt)} симв.)")
            text, action = _reply_with_self_heal(prompt, current_root)
            server_state.mark_chat_prompt_version()
        elif not STATE.get("is_primed", False):
            print("\n---> Авто-инициализация сессии и отправка мега-промпта...")
            system_context = _build_priming_context(current_root)
            # v104.6: маркер без синтаксиса «[метка]: адрес» — старый вид Markdown считал
            # link reference definition (если задание — одно слово) и СКРЫВАЛ его при отображении
            # отправленного сообщения на AI Studio/Qwen и др. (модель текст получала, но в чате он был невидим).
            final_prompt = f"{system_context}\n\n=== ЗАДАНИЕ ОТ ПОЛЬЗОВАТЕЛЯ ===\n{prompt}"
            text, action = _reply_with_self_heal(final_prompt, current_root)
            STATE["is_primed"] = True
            _save_primed(current_root, True)
            server_state.mark_chat_prompt_version()  # v48: запомнить версию промпта у чата
        else:
            print(f"\n---> Отправка сообщения ({len(prompt)} симв.)")
            text, action = _reply_with_self_heal(prompt, current_root)

        packaged = _attach_battle_choice(
            _package_model_reply(text, action, current_root))
        packaged_status = (int(packaged[1]) if isinstance(packaged, tuple)
                           and len(packaged) > 1 else
                           int(getattr(packaged, "status_code", 200) or 200))
        if packaged_status >= 400:
            server_state.discard_turn_transcript()
            STATE["fs_snapshot"] = old_fs_snapshot
            STATE["fs_snapshot_root"] = old_fs_snapshot_root
            return packaged
        try:
            visible_payload = (packaged[0].get_json(silent=True)
                               if isinstance(packaged, tuple)
                               else packaged.get_json(silent=True))
        except Exception:
            visible_payload = None
        if isinstance(visible_payload, dict):
            server_state.ensure_turn_agent_response(visible_payload.get("answer"))
        try:
            server_state.commit_turn_transcript()
        except Exception as persist_error:
            # Модель уже приняла запрос и pending action мог быть подготовлен.
            # Ошибка HTTP восстановила бы draft и продублировала его на сайте/API.
            # Возвращаем принятый результат, но явно сообщаем, что локальная
            # история не сохранена: скрытая потеря хуже видимого предупреждения.
            server_state.discard_turn_transcript()
            print("❌ Не удалось сохранить transcript принятого хода: %s" % persist_error)
            if isinstance(visible_payload, dict):
                visible_payload["transcript_persisted"] = False
                visible_payload["transcript_warning"] = (
                    "Ответ получен, но локальную историю чата сохранить не удалось. "
                    "Не закрывайте этот чат до исправления доступа к диску.")
                return jsonify(visible_payload)
            return packaged
        server_state.consume_action_note_for_current(note)
        server_state.consume_stale_note_for_current(stale)
        if not server_state.turn_chat_is_current():
            server_state.clear_pending_confirmations()
            return jsonify({"error": "Чат изменился во время обработки; ответ сохранён в исходном чате.",
                            "code": "chat_changed"}), 409
        return packaged
    except Exception as e:
        STATE["fs_snapshot"] = old_fs_snapshot
        STATE["fs_snapshot_root"] = old_fs_snapshot_root
        print(f"❌ ОШИБКА: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/chat/confirm_action', methods=['POST'])
def confirm_action():
    data = request.json or {}
    approved = data.get('approved', False)
    project_root = STATE.get("project_root")

    # --- Ветка 0: план (целая цепочка действий) ---
    if STATE.get("pending_plan") is not None:
        plan = STATE["pending_plan"]
        if not approved:
            print(f"--> План из {plan['total']} шаг(ов) ОТКЛОНён пользователем.")
            STATE["pending_plan"] = None
            STATE["pending_action"] = None
            server_state.queue_action_note("[Система: Пользователь ОТКЛОНИЛ ваш план. Ни один шаг не был применен. Скорректируй подход.]")
            return jsonify({"answer": "[Система]: План отклонён пользователем.", "pending_action": None})
        # План одобрен: переводим в режим выполнения. Сами шаги вызывает клиент (Godot-панель)
        # через /chat/plan/step — здесь мы только снимаем pending_action, чтобы освободить UI подтверждения.
        print(f"--> План из {plan['total']} шаг(ов) подтверждён. Выполнение будет идти пошагово через /chat/plan/step.")
        STATE["pending_action"] = None
        return jsonify({"answer": "[Система]: План подтверждён, начинается выполнение шагов.", "pending_action": None,
                        "plan_started": True, "plan_total": plan["total"]})

    # --- Ветка 1: пачка файлов на чтение ---
    if STATE.get("pending_batch") is not None:
        try:
            conf = _next_batch_confirmation()
            if conf is None:
                STATE["pending_batch"] = None
                return jsonify({"error": "Нет ожидающего файла."}), 400
            for f in STATE["pending_batch"]["files"]:
                if f["path"] == conf["path"] and f["status"] == "pending":
                    f["status"] = "approved" if approved else "rejected"
                    print(f"--> Файл {f['path']}: {'ОДОБРЕН' if approved else 'ОТКЛОНЁН'}")
                    break
            nxt = _next_batch_confirmation()
            if nxt is not None:
                # Браузер НЕ трогаем — просто спрашиваем про следующий файл.
                return jsonify({"next_confirmation": nxt})
            # Все решения приняты — ОДИН запрос в браузер со всем сразу.
            followup = _finish_read_batch(project_root)
            print(f"--> Пачка файлов собрана, отправляем одним сообщением ({len(followup)} симв.)")
            text, new_action = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text, new_action, project_root)
        except Exception as e:
            STATE["pending_batch"] = None
            print(f"❌ ОШИБКА confirm_action (batch): {e}")
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    # --- Ветка 2: WRITE-действие ---
    action = STATE.get("pending_action")
    if action is None:
        return jsonify({"error": "Нет ожидающего подтверждения действия."}), 400

    act_type = action.get("action")
    path = action.get("path", "")
    try:
        if not approved:
            print(f"--> Действие '{act_type}' ОТКЛОНЕНО пользователем.")
            server_state.queue_action_note(f"[Система: Пользователь ОТКЛОНИЛ ваше действие {act_type} для {path}. Изменение НЕ было применено! Скорректируй подход.]")
            STATE["pending_action"] = None
            STATE["pending_refactor"] = None
            STATE["pending_scene_action"] = None
            STATE["pending_project_settings_action"] = None
            STATE["pending_resource_action"] = None
            STATE["pending_validation"] = None
            STATE["pending_transaction"] = None
            STATE["pending_runtime_request"] = None
            STATE["pending_runtime_check"] = None
            return jsonify({"answer": "[Система]: Действие отклонено пользователем.", "pending_action": None})

        if act_type == "inspect_runtime":
            if int(STATE.get("runtime_inspections_this_turn") or 0) >= 1:
                STATE["pending_action"] = None
                return jsonify({"error": "Runtime snapshot уже запрашивался в этом ходе."}), 409
            try:
                pending = runtime_debug.create_request(
                    action, STATE.get("runtime_status"), STATE.get("current_chat_id"),
                    STATE.get("runtime_turn_id"))
                pending["project_root"] = STATE.get("project_root")
            except runtime_debug.RuntimeDebugError as exc:
                STATE["pending_action"] = None
                return jsonify({"error": str(exc)}), 409
            STATE["pending_runtime_request"] = pending
            STATE["runtime_inspections_this_turn"] = 1
            STATE["pending_action"] = None
            return jsonify({"answer": "[Система]: Runtime inspection подтверждён.",
                            "pending_action": None,
                            "runtime_request": runtime_debug.public_request(pending)})

        if act_type == "run_check":
            if int(STATE.get("runtime_inspections_this_turn") or 0) >= 1:
                STATE["pending_action"] = None
                return jsonify({"error": "Runtime action уже выполнялся в этом ходе."}), 409
            pending = runtime_checks.create_request(
                action, STATE.get("current_chat_id"), STATE.get("runtime_turn_id"), project_root,
                STATE.get("user_data_dir"))
            STATE["pending_runtime_check"] = pending
            STATE["runtime_inspections_this_turn"] = 1
            STATE["pending_action"] = None
            return jsonify({"answer": "[Система]: Локальная игровая проверка подтверждена.",
                            "pending_action": None,
                            "runtime_check_request": runtime_checks.public_request(pending)})

        if act_type == "rename_symbol":
            prepared = STATE.get("pending_refactor")
            if not isinstance(prepared, dict):
                STATE["pending_action"] = None
                return jsonify({"error": "Подготовленная транзакция переименования утрачена."}), 409
            print("--> rename_symbol %s -> %s. Применяем %d файл(ов)..." % (
                prepared.get("old_name"), prepared.get("new_name"),
                len(prepared.get("files") or [])))
            try:
                validation = prepared.get("validation") or {}
                godot_headless_validation.verify_receipt(
                    project_root, validation.get("batch"), validation.get("receipt"))
                result = symbol_refactor.apply_prepared_rename(
                    project_root, prepared, *_current_chat_info())
            except symbol_refactor.StaleRenameError as exc:
                STATE["pending_action"] = None
                STATE["pending_refactor"] = None
                return jsonify({"error": str(exc)}), 409
            except godot_headless_validation.StaleValidationError as exc:
                STATE["pending_action"] = None
                STATE["pending_refactor"] = None
                STATE["pending_validation"] = None
                return jsonify({"error": str(exc)}), 409
            STATE["pending_action"] = None
            STATE["pending_refactor"] = None
            STATE["pending_validation"] = None
            changed_paths = result["changed_paths"]
            for changed_path in changed_paths:
                _remember_file(project_root, changed_path)
                _touch_file_read(changed_path)
            _refresh_fs_snapshot(project_root)
            return jsonify({
                "answer": "[Система]: Символ %s безопасно переименован в %s (%d файл(ов), %d ссылок)." % (
                    prepared["old_name"], prepared["new_name"], result["file_count"],
                    result["reference_count"]),
                "pending_action": None, "changed_paths": changed_paths,
                "history_entry_id": result["entry_id"],
            })

        if act_type == "rename_file":
            prepared = STATE.get("pending_file_refactor")
            if not isinstance(prepared, dict):
                STATE["pending_action"] = None
                return jsonify({"error": "Подготовленная транзакция переименования файла утрачена."}), 409
            print("--> rename_file %s -> %s. Применяем %d файл(ов)..." % (
                prepared.get("old_path"), prepared.get("new_path"),
                len(prepared.get("files") or [])))
            try:
                result = file_refactor.apply_prepared_file_rename(
                    project_root, prepared, *_current_chat_info())
            except file_refactor.StaleFileRefactorError as exc:
                STATE["pending_action"] = None
                STATE["pending_file_refactor"] = None
                return jsonify({"error": str(exc)}), 409
            except Exception as exc:
                STATE["pending_action"] = None
                STATE["pending_file_refactor"] = None
                return jsonify({"error": "Ошибка применения rename_file: %s" % exc}), 500
            STATE["pending_action"] = None
            STATE["pending_file_refactor"] = None
            changed_paths = result["changed_paths"]
            try:
                librarian.note_files_changed(project_root, changed_paths, deleted=[result["old_path"]])
            except Exception:
                pass
            for changed_path in changed_paths:
                _remember_file(project_root, changed_path)
                _touch_file_read(changed_path)
            _forget_file(result["old_path"])
            _refresh_fs_snapshot(project_root)
            return jsonify({
                "answer": "[Система]: Файл %s успешно переименован в %s (обновлено ссылок: %d в %d файлах)." % (
                    result["old_path"], result["new_path"],
                    result["reference_count"], result["file_count"]),
                "pending_action": None, "changed_paths": changed_paths,
                "history_entry_id": result["entry_id"],
            })

        if act_type in ("rename_node", "reparent_node", "delete_node"):
            prepared = STATE.get("pending_node_refactor")
            if not isinstance(prepared, dict):
                STATE["pending_action"] = None
                return jsonify({"error": "Подготовленная транзакция рефакторинга узла утрачена."}), 409
            print("--> %s %s в %s. Применяем %d файл(ов)..." % (
                act_type, prepared.get("target_node_path"),
                prepared.get("scene_res"), len(prepared.get("files") or [])))
            try:
                result = node_refactor.apply_prepared_node_refactor(
                    project_root, prepared, *_current_chat_info())
            except node_refactor.StaleNodeRefactorError as exc:
                STATE["pending_action"] = None
                STATE["pending_node_refactor"] = None
                return jsonify({"error": str(exc)}), 409
            except Exception as exc:
                STATE["pending_action"] = None
                STATE["pending_node_refactor"] = None
                return jsonify({"error": "Ошибка применения %s: %s" % (act_type, exc)}), 500
            STATE["pending_action"] = None
            STATE["pending_node_refactor"] = None
            changed_paths = result["changed_paths"]
            try:
                librarian.note_files_changed(project_root, changed_paths)
            except Exception:
                pass
            for changed_path in changed_paths:
                _remember_file(project_root, changed_path)
                _touch_file_read(changed_path)
            _refresh_fs_snapshot(project_root)
            if act_type == "reparent_node":
                msg = "[Система]: Узел %s успешно перемещён в %s в сцене %s (обновлено ссылок: %d в %d файлах)." % (
                    result["target_node_path"], result.get("new_parent"), result["scene_res"],
                    result["reference_count"], result["file_count"])
            elif act_type == "delete_node":
                msg = "[Система]: Узел %s успешно удалён из сцены %s (%d обновлений в .tscn)." % (
                    result["target_node_path"], result["scene_res"],
                    result["reference_count"])
                warnings = prepared.get("warnings") or []
                if warnings:
                    msg += "\n\nВнимание! В прикреплённых скриптах найдены ссылки на удалённый узел (скрипты не изменялись, чтобы не нарушить отступы и логику):\n"
                    msg += "\n".join("- %s:%d: %s" % (w["file"], w["line"], w["code"]) for w in warnings[:5])
                    if len(warnings) > 5:
                        msg += "\n- ... и ещё %d мест(а)" % (len(warnings) - 5)
            else:
                msg = "[Система]: Узел %s успешно переименован в %s в сцене %s (обновлено ссылок: %d в %d файлах)." % (
                    result["target_node_path"], result["new_name"], result["scene_res"],
                    result["reference_count"], result["file_count"])
            return jsonify({
                "answer": msg,
                "pending_action": None, "changed_paths": changed_paths,
                "history_entry_id": result["entry_id"],
            })

        if act_type == "transaction":
            prepared = STATE.get("pending_transaction")
            if not isinstance(prepared, dict):
                STATE["pending_action"] = None
                return jsonify({"error": "Подготовленная пакетная транзакция утрачена."}), 409
            try:
                result = transaction_actions.apply_prepared(
                    project_root, prepared, *_current_chat_info())
            except (transaction_actions.StaleTransactionError,
                    godot_headless_validation.StaleValidationError) as exc:
                STATE["pending_action"] = None
                STATE["pending_transaction"] = None
                return jsonify({"error": str(exc)}), 409
            STATE["pending_action"] = None
            STATE["pending_transaction"] = None
            changed_paths = result["changed_paths"]
            librarian.note_files_changed(project_root, changed_paths)
            for changed_path in changed_paths:
                _remember_file(project_root, changed_path)
                _touch_file_read(changed_path)
            _refresh_fs_snapshot(project_root)
            return jsonify({
                "answer": "[Система]: Пакетная транзакция применена атомарно (%d файл(ов))." % result["file_count"],
                "pending_action": None, "changed_paths": changed_paths,
                "history_entry_id": result["entry_id"],
            })

        if act_type in ("edit_scene", "create_scene"):
            prepared = STATE.get("pending_scene_action")
            if not isinstance(prepared, dict):
                STATE["pending_action"] = None
                return jsonify({"error": "Подготовленная транзакция сцены утрачена."}), 409
            _normalized, absolute = scene_actions.normalize_action(
                project_root, prepared["action"], bool(STATE.get("addon_intent")))
            if act_type == "edit_scene" and scene_actions.file_sha256(absolute) != prepared["before_hash"]:
                STATE["pending_action"] = None
                STATE["pending_scene_action"] = None
                return jsonify({"error": "Сцена изменилась после предпросмотра."}), 409
            editor_semantic_hash = str(data.get("editor_semantic_hash") or "")
            if len(editor_semantic_hash) != 64:
                STATE["pending_action"] = None
                STATE["pending_scene_action"] = None
                return jsonify({"error": "Godot не подтвердил структурный предпросмотр сцены."}), 409
            prepared["editor_semantic_hash"] = editor_semantic_hash
            states = None
            if act_type == "create_scene":
                if os.path.lexists(absolute):
                    STATE["pending_action"] = None
                    STATE["pending_scene_action"] = None
                    return jsonify({"error": "Сцена появилась после предпросмотра; создание отменено."}), 409
                states = [{"path": prepared["scene"], "before_bytes": None, "after_bytes": b"pending"}]
            entry_id = history.record_batch_change(
                project_root, act_type, [prepared["scene"]], *_current_chat_info(), states=states)
            prepared["entry_id"] = entry_id
            prepared["execution_token"] = os.urandom(24).hex()
            prepared["state"] = "executing"
            STATE["pending_action"] = None
            return jsonify({
                "answer": "[Система]: Действие подтверждено; Godot применяет структурные операции.",
                "pending_action": None,
                "execute_in_editor": True,
                "editor_action": prepared["action"],
                "action_id": prepared["action_id"],
                "action_digest": prepared["action_digest"],
                "expected_scene_hash": prepared["before_hash"] or "",
                "execution_token": prepared["execution_token"],
            })

        if act_type == "edit_project_settings":
            prepared = STATE.get("pending_project_settings_action")
            if not isinstance(prepared, dict):
                STATE["pending_action"] = None
                return jsonify({"error": "Подготовленная транзакция настроек проекта утрачена."}), 409
            _normalized, absolute = project_settings_actions.normalize_action(
                project_root, prepared["action"], bool(STATE.get("addon_intent")))
            if project_settings_actions.file_sha256(absolute) != prepared["before_hash"]:
                STATE["pending_action"] = None
                STATE["pending_project_settings_action"] = None
                return jsonify({"error": "project.godot изменился после предпросмотра."}), 409
            editor_semantic_hash = str(data.get("editor_semantic_hash") or "")
            if len(editor_semantic_hash) != 64:
                STATE["pending_action"] = None
                STATE["pending_project_settings_action"] = None
                return jsonify({"error": "Godot не подтвердил предпросмотр настроек проекта."}), 409
            prepared["editor_semantic_hash"] = editor_semantic_hash
            entry_id = history.record_batch_change(
                project_root, "edit_project_settings", ["res://project.godot"], *_current_chat_info())
            prepared["entry_id"] = entry_id
            prepared["execution_token"] = os.urandom(24).hex()
            prepared["state"] = "executing"
            STATE["pending_action"] = None
            return jsonify({
                "answer": "[Система]: Изменение подтверждено; Godot применяет настройки проекта.",
                "pending_action": None, "execute_in_editor": True,
                "editor_action_kind": "project_settings", "editor_action": prepared["action"],
                "action_id": prepared["action_id"], "action_digest": prepared["action_digest"],
                "expected_project_hash": prepared["before_hash"],
                "execution_token": prepared["execution_token"],
            })

        if act_type == "edit_resource":
            prepared = STATE.get("pending_resource_action")
            if not isinstance(prepared, dict):
                STATE["pending_action"] = None
                return jsonify({"error": "Подготовленная транзакция ресурса утрачена."}), 409
            _normalized, absolute = resource_actions.normalize_action(
                project_root, prepared["action"], bool(STATE.get("addon_intent")))
            if resource_actions.file_sha256(absolute) != prepared["before_hash"]:
                STATE["pending_action"] = None
                STATE["pending_resource_action"] = None
                return jsonify({"error": "Ресурс изменился после предпросмотра."}), 409
            editor_semantic_hash = str(data.get("editor_semantic_hash") or "")
            dependency_fingerprint = str(data.get("dependency_fingerprint") or "")
            if len(editor_semantic_hash) != 64 or len(dependency_fingerprint) != 64:
                STATE["pending_action"] = None
                STATE["pending_resource_action"] = None
                return jsonify({"error": "Godot не подтвердил структурный предпросмотр ресурса."}), 409
            prepared["editor_semantic_hash"] = editor_semantic_hash
            prepared["dependency_fingerprint"] = dependency_fingerprint
            entry_id = history.record_batch_change(
                project_root, "edit_resource", [prepared["resource"]], *_current_chat_info())
            prepared["entry_id"] = entry_id
            prepared["execution_token"] = os.urandom(24).hex()
            prepared["state"] = "executing"
            STATE["pending_action"] = None
            return jsonify({
                "answer": "[Система]: Изменение подтверждено; Godot применяет операции ресурса.",
                "pending_action": None, "execute_in_editor": True,
                "editor_action_kind": "resource", "editor_action": prepared["action"],
                "action_id": prepared["action_id"], "action_digest": prepared["action_digest"],
                "expected_resource_hash": prepared["before_hash"],
                "expected_dependency_fingerprint": dependency_fingerprint,
                "execution_token": prepared["execution_token"],
            })

        if act_type in ("create_file", "patch_file", "move_file"):
            print(f"--> {act_type} {path}. Выполняем локально...")
            result = _apply_write_step(
                action, project_root, validation=STATE.get("pending_validation"))
            STATE["pending_action"] = None
            STATE["pending_validation"] = None
            if not result["ok"]:
                raise RuntimeError(result["message"])
            # changed_path/changed_block — панель откроет файл в редакторе и
            # подсветит строки, которые написал агент.
            resp = {"answer": "[Система]: " + result["message"], "pending_action": None}
            if result.get("changed_path"):
                resp["changed_path"] = result["changed_path"]
                resp["changed_block"] = result.get("changed_block", "")
            # Адрес записи журнала для кнопки отката на ЭТОЙ карточке
            # сообщения. Без него панель могла просить только «откатить
            # последнее» и отменяла не то изменение, на которое нажали.
            if result.get("entry_id"):
                resp["history_entry_id"] = result["entry_id"]
            return jsonify(resp)

        elif act_type == "search_project":
            query = str(action.get("query", ""))
            STATE["pending_action"] = None
            if not query.strip():
                followup = "[Система]: search_project пришёл с ПУСТЫМ 'query' — поиск не выполнен. Пришли действие заново с непустым query."
            else:
                print(f"--> Поиск по проекту: {query!r}")
                results, truncated = search_project_text(project_root, query)
                followup = _format_search_results(query, results, truncated)
            text, new_action = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text, new_action, project_root)

        elif act_type == "gather_context":
            STATE["pending_action"] = None
            print("--> Составной сбор контекста проекта...")
            result = gather_context.gather(
                project_root, action,
                editor_snapshot=STATE.get("editor_context"),
                addon_dir=STATE.get("addon_dir"),
                allow_addons=bool(STATE.get("addon_intent")))
            followup = gather_context.format_result(result)
            print("--> Контекст собран, отправляем одним сообщением (%d симв.)" % len(followup))
            text, new_action = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text, new_action, project_root)

        elif act_type == "list_files":
            STATE["pending_action"] = None
            sub = str(action.get("dir") or "").strip()
            if sub.rstrip("/") in ("", "res:"):
                sub = ""  # res:// — это корень проекта: отдаём полную структуру, а не ошибку
            fence = "`" * 3
            if sub:
                print(f"--> Отправка дерева папки {sub}...")
                try:
                    tree = build_project_tree(project_root, subdir=sub)
                    followup = "[Система]: АКТУАЛЬНОЕ дерево папки %s:\n%s\n%s\n%s" % (sub, fence, tree, fence)
                except Exception as e:
                    followup = "[Система]: list_files не выполнен: %s Проверь \"dir\" — это должна быть существующая папка res://." % e
            else:
                print("--> Отправка свежей структуры проекта...")
                tree, compact = build_project_overview(project_root, compact_threshold=PRIME_COMPACT_THRESHOLD)
                head = ("АКТУАЛЬНАЯ структура проекта (проект большой — это СВОДКА по папкам; дерево конкретной папки: list_files с \"dir\")"
                        if compact else "АКТУАЛЬНОЕ дерево файлов проекта")
                followup = "[Система]: %s:\n%s\n%s\n%s" % (head, fence, tree, fence)
            text, new_action = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text, new_action, project_root)

        elif act_type == "list_scene":
            STATE["pending_action"] = None
            print(f"--> Структура сцены {path}...")
            fence = "`" * 3
            try:
                summary = describe_scene(project_root, path)
                followup = ("[Система]: Структура сцены %s:\n%s\n%s\n%s\n"
                            "Это СВОДКА, а не содержимое файла: для patch_file по этой сцене сначала прочитай файл через read_file.") % (path, fence, summary, fence)
            except Exception as e:
                followup = "[Система]: list_scene не выполнен: %s" % e
            text, new_action = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text, new_action, project_root)

        else:
            STATE["pending_action"] = None
            return jsonify({"error": f"Неизвестный тип действия: {act_type}"}), 400

    except Exception as e:
        server_state.discard_turn_transcript()
        if not (act_type == "transaction" and isinstance(STATE.get("pending_transaction"), dict)
                and STATE["pending_transaction"].get("state") == "recovery_required"):
            STATE["pending_transaction"] = None
        STATE["pending_action"] = None
        STATE["pending_refactor"] = None
        STATE["pending_scene_action"] = None
        STATE["pending_project_settings_action"] = None
        STATE["pending_resource_action"] = None
        STATE["pending_runtime_request"] = None
        STATE["pending_validation"] = None
        print(f"❌ ОШИБКА confirm_action: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/chat/editor_action/result', methods=['POST'])
def editor_action_result():
    """Finalize one Godot-executed scene, settings, or resource transaction."""
    data = request.json or {}
    identity = (str(data.get("action_id") or ""), str(data.get("execution_token") or ""))
    cached = _EDITOR_ACTION_RESULTS.get(identity)
    if cached is not None:
        body, status = cached
        return jsonify(body), status
    action_kind = str(data.get("editor_action_kind") or "scene")
    pending_keys = {"scene": "pending_scene_action",
                    "project_settings": "pending_project_settings_action",
                    "resource": "pending_resource_action"}
    pending_key = pending_keys.get(action_kind)
    if pending_key is None:
        return jsonify({"error": "Неизвестный тип editor-транзакции."}), 400
    prepared = STATE.get(pending_key)
    if not isinstance(prepared, dict) or prepared.get("state") != "executing":
        return jsonify({"error": "Нет выполняемой editor-транзакции."}), 409
    expected = (prepared.get("action_id"), prepared.get("execution_token"))
    if identity != expected:
        return jsonify({"error": "Токен editor-транзакции не совпадает."}), 403
    project_root = STATE.get("project_root")
    entry_id = prepared.get("entry_id")
    changed_path = prepared.get("scene") or prepared.get("resource") or prepared.get("target")
    success = bool(data.get("success"))
    is_settings = pending_key == "pending_project_settings_action"
    is_resource = pending_key == "pending_resource_action"
    is_create_scene = prepared.get("action", {}).get("action") == "create_scene"
    target_written = bool(data.get("target_written")) if is_create_scene else False
    staged_hash = str(data.get("staged_hash") or "") if is_create_scene else ""
    hash_field = "project_hash" if is_settings else ("resource_hash" if is_resource else "scene_hash")
    reported_hash = str(data.get(hash_field) or "")
    try:
        actions_module = (project_settings_actions if is_settings else
                          (resource_actions if is_resource else scene_actions))
        if is_resource:
            _normalized, absolute = actions_module.normalize_action(
                project_root, prepared["action"], bool(STATE.get("addon_intent")),
                require_exists=False)
        elif pending_key == "pending_scene_action":
            _normalized, absolute = actions_module.normalize_action(
                project_root, prepared["action"], bool(STATE.get("addon_intent")),
                require_target_state=False)
        else:
            _normalized, absolute = actions_module.normalize_action(
                project_root, prepared["action"], bool(STATE.get("addon_intent")))
        try:
            actual_hash = actions_module.file_sha256(absolute)
        except (OSError, FileNotFoundError):
            actual_hash = ""
        if is_create_scene and success:
            if target_written:
                history.abort_change(project_root, entry_id)
                STATE[pending_key] = None
                return jsonify({"error": "Godot не должен напрямую записывать новую сцену."}), 409
            try:
                actual_hash = scene_actions.materialize_staged_scene(
                    absolute, str(prepared.get("action_id") or ""), staged_hash)
                target_written = True
                reported_hash = actual_hash
            except scene_actions.SceneActionError as exc:
                scene_actions.discard_staged_scene(
                    absolute, str(prepared.get("action_id") or ""))
                history.abort_change(project_root, entry_id)
                STATE[pending_key] = None
                body = {"success": False, "restored": True,
                        "answer": "[Система]: Новая сцена не опубликована: %s" % exc,
                        "changed_paths": []}
                _EDITOR_ACTION_RESULTS[identity] = (body, 409)
                return jsonify(body), 409
        if success and not is_create_scene and not reported_hash:
            return jsonify({"error": "Godot не передал хэш записанного файла; резерв истории сохранён."}), 409
        if reported_hash and reported_hash != actual_hash:
            restored, message, paths = history.restore_reserved_change(
                project_root, entry_id, current_hash=reported_hash,
                remove_created=False)
            if restored:
                STATE[pending_key] = None
                _refresh_fs_snapshot(project_root)
            body = {"success": False, "restored": restored,
                    "answer": "[Система]: Хэш отчёта Godot не совпал с диском. " + message,
                    "changed_paths": paths}
            status = 200 if restored else 409
            if restored:
                _EDITOR_ACTION_RESULTS[identity] = (body, status)
            return jsonify(body), status
        if not success:
            if is_create_scene:
                scene_actions.discard_staged_scene(
                    absolute, str(prepared.get("action_id") or ""))
            restored, message, paths = history.restore_reserved_change(
                project_root, entry_id, current_hash=reported_hash or None,
                remove_created=is_create_scene and target_written)
            if restored:
                STATE[pending_key] = None
                _refresh_fs_snapshot(project_root)
            body = {"success": False, "restored": restored,
                    "answer": "[Система]: " + message, "changed_paths": paths}
            status = 200 if restored else 409
            if restored:
                _EDITOR_ACTION_RESULTS[identity] = (body, status)
            return jsonify(body), status
        already_satisfied = bool(data.get("already_satisfied")) if is_settings else False
        if is_create_scene and not target_written:
            history.abort_change(project_root, entry_id)
            STATE[pending_key] = None
            return jsonify({"error": "Godot не подтвердил запись новой сцены."}), 409
        if is_create_scene and not actual_hash:
            history.abort_change(project_root, entry_id)
            STATE[pending_key] = None
            return jsonify({"error": "Godot сообщил создание сцены, но целевой файл отсутствует."}), 409
        if actual_hash == prepared.get("before_hash") and not already_satisfied and not is_create_scene:
            history.abort_change(project_root, entry_id)
            STATE[pending_key] = None
            return jsonify({"error": "Godot сообщил успех, но целевой файл не изменился."}), 409
        if already_satisfied and actual_hash != prepared.get("before_hash"):
            return jsonify({"error": "Godot сообщил already_satisfied, но project.godot изменился."}), 409
        if already_satisfied:
            history.abort_change(project_root, entry_id)
            body = {
                "success": True,
                "already_satisfied": True,
                "answer": "[Система]: Запрошенные настройки проекта уже были применены; запись не потребовалась.",
                "history_entry_id": None,
                "changed_paths": [],
                "requires_editor_restart": False,
            }
            _EDITOR_ACTION_RESULTS[identity] = (body, 200)
            STATE[pending_key] = None
            return jsonify(body)
        history.commit_change(project_root, entry_id)
        body = {
            "success": True,
            "answer": ("[Система]: Настройки проекта применены; требуется перезапуск редактора."
                       if is_settings else ("[Система]: Структурные изменения ресурса применены и сохранены."
                       if is_resource else ("[Система]: Сцена создана и сохранена."
                       if is_create_scene else "[Система]: Структурные изменения сцены применены и сохранены."))),
            "history_entry_id": entry_id,
            "changed_paths": [changed_path], "requires_editor_restart": is_settings,
        }
        _EDITOR_ACTION_RESULTS[identity] = (body, 200)
        STATE[pending_key] = None
        if len(_EDITOR_ACTION_RESULTS) > 32:
            _EDITOR_ACTION_RESULTS.pop(next(iter(_EDITOR_ACTION_RESULTS)))
        try:
            librarian.note_files_changed(project_root, [changed_path])
            _remember_file(project_root, changed_path)
            _touch_file_read(changed_path)
            _refresh_fs_snapshot(project_root)
        except Exception as exc:
            print("⚠️ Editor-транзакция зафиксирована, но обновление кэшей не выполнено: %s" % exc)
        return jsonify(body)
    except Exception as exc:
        print("❌ ОШИБКА editor_action_result: %s" % exc)
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route('/chat/runtime_inspect/result', methods=['POST'])
def runtime_inspect_result():
    if request.content_length is not None and request.content_length > runtime_debug.MAX_HTTP_BODY_BYTES:
        return jsonify({"error": "Runtime result превышает допустимый размер."}), 413
    data = request.json or {}
    identity, error = _runtime_result_identity(data)
    if error:
        return error
    cached = _RUNTIME_RESULTS.get(identity)
    if cached is not None:
        return jsonify(cached[0]), cached[1]
    status = str(data.get("status") or "protocol_error")
    if status not in runtime_debug.RESULT_STATUSES:
        return jsonify({"error": "Неизвестный runtime status."}), 400
    pending, claim_error = claim_runtime_request(data)
    if claim_error == "token":
        return jsonify({"error": "Неверный runtime result token."}), 403
    if claim_error == "expired":
        return jsonify({"error": "Runtime inspection истёк."}), 410
    if claim_error in ("session", "turn", "request"):
        return jsonify({"error": "Runtime inspection устарел или относится к другой сессии."}), 409
    if claim_error:
        return jsonify({"error": "Нет ожидающего runtime inspection."}), 409
    try:
        if status != "ok":
            messages = {
                "runtime_not_running": "Игра больше не запущена.",
                "ambiguous_session": "Нужно явно выбрать runtime session.",
                "bridge_unavailable": "AgentRuntimeBridge не подключён как debug Autoload.",
                "session_stopped": "Runtime session остановлена.",
                "stale_runtime_session": "Игра была перезапущена во время inspection.",
                "timeout": "Runtime inspection превысил лимит времени.",
                "response_too_large": "Runtime snapshot превысил допустимый размер.",
            }
            return _cache_runtime_result(identity, {
                "answer": "[Система]: " + messages.get(status, "Runtime inspection не выполнен."),
                "pending_action": None, "runtime_status": status})
        snapshot = runtime_debug.normalize_snapshot(data.get("snapshot"))
        runtime_debug.validate_snapshot_request(snapshot, pending)
        followup = runtime_debug.format_snapshot(snapshot)
        text, new_action = _reply_once(followup)
        response = app.make_response(_package_model_reply(
            text, new_action, pending.get("project_root"), allow_followup=False))
        return _cache_runtime_result(identity, response.get_json(), response.status_code)
    except runtime_debug.RuntimeDebugError as exc:
        return _cache_runtime_result(identity, {"error": str(exc)}, 413 if "96 KiB" in str(exc) else 400)


@app.route('/chat/runtime_check/bind', methods=['POST'])
def runtime_check_bind():
    data = request.json or {}
    pending, error = bind_runtime_check(data)
    if error == "token":
        return jsonify({"error": "Неверный runtime check token."}), 403
    if error == "expired":
        return jsonify({"error": "Локальная проверка истекла."}), 410
    if error:
        return jsonify({"error": "Проверка не может быть привязана к этой runtime session."}), 409
    return jsonify({"success": True, "game_request": runtime_checks.game_request(pending)})


@app.route('/chat/runtime_check/result', methods=['POST'])
def runtime_check_result():
    if request.content_length is not None and request.content_length > runtime_checks.MAX_HTTP_BODY_BYTES:
        return jsonify({"error": "Runtime check result превышает допустимый размер."}), 413
    data = request.json or {}
    identity, error = _runtime_result_identity(data)
    if error:
        return error
    cached = _RUNTIME_RESULTS.get(identity)
    if cached is not None:
        return jsonify(cached[0]), cached[1]
    status = str(data.get("status") or "protocol_error")
    if status not in runtime_checks.RESULT_STATUSES:
        return jsonify({"error": "Неизвестный runtime check status."}), 400
    prebind_statuses = {"runtime_already_running", "launch_failed", "launch_timeout",
                        "bridge_unavailable", "session_stopped", "cancelled"}
    pending, error = claim_runtime_check(data, allow_unbound=status in prebind_statuses)
    if error == "token":
        return jsonify({"error": "Неверный runtime check token."}), 403
    if error == "expired":
        return jsonify({"error": "Локальная проверка истекла."}), 410
    if error:
        return jsonify({"error": "Локальная проверка устарела или уже завершена."}), 409
    try:
        if status != "ok":
            body = {"success": False, "passed": False,
                    "answer": "[Система]: Локальная игровая проверка не выполнена: %s." % status,
                    "runtime_status": status}
            return _cache_runtime_result(identity, body)
        log_errors = runtime_checks.collect_log_errors(pending.get("log_cursor"))
        report = runtime_checks.finalize_result(
            pending, data.get("result"), log_errors=log_errors,
            log_available=runtime_checks.log_source_available(pending.get("log_cursor")))
        body = {"success": True, "passed": report["passed"], "check_report": report,
                "answer": ("[Система]: Локальная игровая проверка пройдена."
                           if report["passed"] else
                           "[Система]: Локальная игровая проверка обнаружила несоответствия.")}
        if not report["passed"]:
            followup = runtime_checks.format_report(report)
            text, next_action = _reply_once(followup)
            packaged = _package_model_reply(text, next_action, pending.get("project_root"), allow_followup=False)
            response = packaged[0] if isinstance(packaged, tuple) else packaged
            response_json = response.get_json()
            response_json.update({"success": True, "passed": False, "check_report": report})
            return _cache_runtime_result(identity, response_json)
        return _cache_runtime_result(identity, body)
    except runtime_checks.RuntimeCheckError as exc:
        return _cache_runtime_result(identity, {"error": str(exc)}, 400)


def _runtime_result_identity(data):
    # HTTP admission owns the exchange through cache publication. Never bypass
    # it for a replay: navigation or a new turn may be changing this binding.
    if (not isinstance(data, dict)
            or not isinstance(data.get("request_id"), str) or not data["request_id"]
            or not isinstance(data.get("result_token"), str) or not data["result_token"]
            or not data["result_token"].isascii()
            or type(data.get("session_id", -1)) is not int
            or not isinstance(data.get("run_id", ""), str)
            or not isinstance(data.get("status", "protocol_error"), str)):
        return None, (jsonify({"error": "Invalid runtime result metadata."}), 400)
    scope = (STATE.get("current_chat_id"), STATE.get("runtime_turn_id"),
             STATE.get("project_root"), STATE.get("user_data_dir"),
             STATE.get("runtime_result_generation"))
    for field, expected in zip(("chat_id", "turn_id", "project_root"), scope):
        if field in data and (type(data[field]) is not type(expected) or data[field] != expected):
            return None, (jsonify({"error": "Runtime result belongs to another context."}), 409)
    now = time.monotonic()
    for key, cached in list(_RUNTIME_RESULTS.items()):
        if cached[2] <= now or key[1:6] != scope:
            del _RUNTIME_RESULTS[key]
    return (request.path, *scope, data["request_id"], data["result_token"],
            data.get("session_id", -1), data.get("run_id", "")), None


def _cache_runtime_result(identity, body, status=200):
    _RUNTIME_RESULTS[identity] = (body, status, time.monotonic() + _RUNTIME_RESULT_TTL)
    if len(_RUNTIME_RESULTS) > _RUNTIME_RESULT_LIMIT:
        _RUNTIME_RESULTS.pop(next(iter(_RUNTIME_RESULTS)))
    return jsonify(body), status


@app.route('/chat/rollback/preview', methods=['POST'])
def rollback_preview():
    """Что именно отменит откат — панель показывает это в диалоге
    подтверждения, чтобы не откатить вслепую действие другого чата.

    entry_id (необязателен) — адрес КОНКРЕТНОЙ записи журнала. Панель
    присылает его, когда пользователь нажал откат на карточке сообщения:
    иначе откатилось бы просто самое свежее изменение проекта, каким бы оно
    ни было и из какого чата ни пришло. Без entry_id остаётся прежнее
    поведение («последнее действие») — это путь для старой панели и для
    кнопки отката в дополнительных настройках."""
    data = request.json or {}
    entry_id = str(data.get("entry_id") or "").strip()
    if not STATE.get("project_root"):
        return jsonify({"error": "Проект не синхронизирован."}), 400
    if entry_id:
        info = history.entry_info(STATE["project_root"], entry_id)
    else:
        info = history.last_committed_info(STATE["project_root"])
    if not info:
        return jsonify({"found": False,
                        "gone": bool(entry_id)})
    kind_ru = {"create_file": "перезапись файла" if info.get("overwrote") else "создание файла",
               "patch_file": "правка файла", "move_file": "перемещение файла",
               "rename_symbol": "переименование символа",
               "edit_scene": "структурное изменение сцены", "create_scene": "создание сцены",
               "edit_project_settings": "изменение настроек проекта",
               "edit_resource": "структурное изменение ресурса",
               "transaction": "пакетная транзакция"}
    paths = [str(path) for path in (info.get("paths") or []) if path]
    target = ", ".join(paths[:3]) if len(paths) > 1 else info["path"]
    if len(paths) > 3:
        target += " и ещё %d" % (len(paths) - 3)
    desc = "%s %s" % (kind_ru.get(info["type"], info["type"]), target)
    when = time.strftime("%H:%M", time.localtime(info.get("ts", 0)))
    title = info.get("chat_title") or ""
    if title:
        src = "чат «%s», %s" % (title, when)
    else:
        src = "%s, чат неизвестен (изменение сделано до обновления)" % when
    resp = {"found": True, "description": "%s (%s)" % (desc, src)}
    if entry_id:
        resp["entry_id"] = entry_id
        # Более свежие правки агента по тому же файлу делают адресный откат
        # невозможным: он потерял бы их работу. Сообщаем это ДО подтверждения,
        # а не после неудачной попытки.
        blockers = info.get("newer_same_file") or []
        if blockers:
            resp["blocked"] = True
            resp["description"] += (
                ". ВНИМАНИЕ: этот файл агент правил ещё %d раз(а) позже. "
                "Сначала откатите более свежие изменения — откат идёт от новых "
                "к старым." % len(blockers))
        # Шаг плана: честно предупреждаем, что остальные шаги останутся.
        if info.get("chain_id") and info.get("chain_total", 0) > 1:
            resp["description"] += (
                ". Это один шаг плана из %d — остальные шаги останутся "
                "применёнными." % info["chain_total"])
    elif info.get("chain_id") and info.get("chain_total", 0) > 1:
        # Прежнее поведение БЕЗ адреса: предложить откат всей цепочки. Для
        # адресного отката такое расширение запрещено — пользователь нажал
        # откат на конкретном сообщении и ждёт отката именно его.
        resp["chain_id"] = info["chain_id"]
        resp["chain_total"] = info["chain_total"]
    return jsonify(resp)


@app.route('/chat/rollback', methods=['POST'])
def rollback():
    data = request.json or {}
    force = bool(data.get('force', False))
    entry_id = str(data.get('entry_id') or "").strip()
    if not STATE.get("project_root"):
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        if entry_id:
            # Адресный откат: отменяем ИМЕННО то изменение, на карточке
            # которого нажали. Без адреса откатывалось самое свежее изменение
            # проекта — из-за этого кнопка на старом облачке отменяла чужую
            # работу, а на сообщении без действий вообще откатывала последнее.
            ok, msg, needs_force, paths, diff = history.rollback_entry(
                STATE["project_root"], entry_id, force=force)
        else:
            ok, msg, needs_force, paths, diff = history.rollback_last(
                STATE["project_root"], force=force)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    if ok:
        _refresh_fs_snapshot(STATE.get("project_root"))
        STATE["file_cache"] = None  # содержимое откатилось — кэш diff устарел
        # Багфикс v105.8: откат меняет файлы на диске, а снапшот уже обновлён —
        # детектор «внешних правок» их не увидит. Обновляем индекс Библиотекаря
        # сами: update_entries сам разберётся, что восстановлено, а что удалено.
        try:
            librarian.note_files_changed(STATE.get("project_root"), paths or [])
        except Exception:
            pass  # худший случай — индекс достроится лениво по STALE_SEC
        note = f"[Система: Пользователь ОТМЕНИЛ (откатил) ваше последнее действие! {msg}."
        if diff:
            # Точный обратный дифф — модели НЕ нужно перечитывать файл целиком.
            fence = "`" * 3
            note += (
                f"\nФайл {diff['path']} вернулся к состоянию ДО твоего патча. Блок:\n"
                f"{fence}\n{diff['was']}\n{fence}\n"
                f"снова выглядит так:\n"
                f"{fence}\n{diff['now']}\n{fence}\n"
                "Остальное содержимое файла НЕ менялось. Повторный read_file НЕ нужен — "
                "можешь сразу предлагать patch_file на основе этого диффа."
            )
        resp = {"success": True, "message": msg, "paths": list(paths or [])}
        if "res://project.godot" in resp["paths"]:
            resp["requires_editor_restart"] = True
        if diff:
            # Панель подсветит в редакторе восстановленный после отката блок.
            resp["changed_path"] = diff["path"]
            resp["changed_block"] = diff["now"]
        # Откат мог вернуть create_file к состоянию "файла ещё нет", а автозагрузка на него
        # в project.godot могла остаться от другого (неоткатанного) шага плана — вычищаем её.
        removed_autoloads = clean_dangling_autoloads(STATE["project_root"])
        if removed_autoloads:
            resp["autoload_removed"] = removed_autoloads
            resp["project_godot_changed"] = True
            if "res://project.godot" not in resp["paths"]:
                resp["paths"].append("res://project.godot")
            note += (" В project.godot также убраны висячие записи автозагрузки (%s), "
                     "так как их файлы больше не существуют." % ", ".join(removed_autoloads))
        note += " Учтите это!]"
        server_state.queue_action_note(note)
        return jsonify(resp)
    return jsonify({"error": msg, "needs_force": needs_force}), 409


# ---------------------------------------------------------------------------
# Plan-режим (цепочка действий): после подтверждения всего плана в confirm_action
# клиент (Godot-панель) сам вызывает /chat/plan/step в цикле, пока не закончатся
# шаги, не придёт ошибка линта/привинения, или пользователь не нажмёт "Стоп".
#
# v40: раньше любая ошибка линта/аплайна на шаге плана тут сразу останавливала весь план
# и требовала ручного отката от пользователя, в отличие от одиночных действий (см. _reply_with_self_heal),
# где модель сама получает точное описание ошибки и шанс исправиться. теферь шаг
# плана точно так же пытается самоисцелиться до MAX_ACTION_FIX_RETRIES раз, и только после этого
# останавливает весь план и зовёт кнопку ручного отката.
# ---------------------------------------------------------------------------

def _self_heal_plan_step_action(step, error_msg, idx, total):
    """Просит модель прислать исправленную версию одного шага плана, который
    не прошёл линт или не применился на диске. Возвращает исправленное действие
    (dict) или None, если модель не прислала пригодное для плана действие."""
    path = step.get("path", "")
    act = step.get("action", "")
    fix_prompt = (
        "[Система]: шаг %d из %d твоего плана (%s, файл: %s) НЕ прошёл проверку и не был применён. "
        "Ошибка: %s\n"
        "Пришли исправленную версию ТОЛьКО этого шага одним agent_action (действие %s для файла %s), "
        "учитывая эту ошибку. Не присылай остальные шаги плана — после того как этот шаг пройдёт "
        "проверку, выполнение плана автоматически продолжится со следующего."
    ) % (idx + 1, total, act, path, error_msg, act, path)
    _, fixed = _reply(fix_prompt)
    if not fixed or fixed.get("action") not in PLAN_ALLOWED_ACTIONS or not fixed.get("path"):
        return None
    return fixed


@app.route('/chat/plan/step', methods=['POST'])
def plan_step():
    plan = STATE.get("pending_plan")
    if plan is None:
        return jsonify({"error": "Нет активного плана."}), 400
    project_root = STATE.get("project_root")
    idx = plan["index"]
    if idx >= plan["total"]:
        STATE["pending_plan"] = None
        return jsonify({"done": True, "index": idx, "total": plan["total"], "message": "План уже завершён."})
    step = plan["steps"][idx]
    heal_attempts = 0
    try:
        result = None
        step_diff = None
        while True:
            engine_fixable = None
            _plan_paths = set(s.get("path") or "" for s in plan["steps"] if s.get("action") == "create_file")
            lint_msg = _lint_action_code(step, project_root, planned_paths=_plan_paths) if step.get("action") != "move_file" else None
            if lint_msg is None:
                batch = godot_headless_validation.batch_from_action(project_root, step)
                receipt = godot_headless_validation.validate_batch(
                    project_root, batch, executable=STATE.get("godot_executable"))
                lint_msg = godot_headless_validation.blocking_message(receipt)
                validation = {"batch": batch, "receipt": receipt}
                engine_fixable = bool((receipt.get("report") or {}).get("new_diagnostics"))
            if lint_msg is None:
                # Дифф считаем ДО записи на диск: после неё «старого» текста уже
                # нет, и показать в панели, что именно изменилось, стало бы нечем.
                # Шаг мог прийти сюда исправленным self-heal — берём его текущую версию.
                step_diff = action_diff_preview(project_root, step)
                result = _apply_write_step(
                    step, project_root, chain_id=plan["chain_id"], validation=validation)
                if result["ok"]:
                    break
                fail_reason = result["message"]
            else:
                fail_reason = _lenient_resend_note(step, lint_msg)
                if engine_fixable is False:
                    STATE["pending_plan"] = None
                    server_state.queue_action_note(
                        "[Система: выполнение плана остановлено: инфраструктурная проверка Godot не прошла. Уже выполненные шаги остались на диске.]")
                    return jsonify({"ok": False, "stopped": True, "index": idx,
                                    "total": plan["total"], "chain_id": plan["chain_id"],
                                    "error": fail_reason, "message": fail_reason})
            # шаг не прошёл проверку/применение — прежде чем останавливать весь план
            # и звать ручной откат, пытаемся самоисцелиться через зачинку обратно модели.
            if heal_attempts >= MAX_ACTION_FIX_RETRIES:
                STATE["pending_plan"] = None
                server_state.queue_action_note((
                    "[Система: выполнение плана остановлено на шаге %d из %d (%s): автоматическое исправление не помогло за %d "
                    "попыт(ки). Последняя ошибка: %s. Уже выполненные шаги (%d) остались на диске.]"
                ) % (idx + 1, plan["total"], step.get("path", ""), MAX_ACTION_FIX_RETRIES, fail_reason, idx))
                return jsonify({
                    "ok": False, "stopped": True, "index": idx, "total": plan["total"],
                    "chain_id": plan["chain_id"], "error": fail_reason,
                    "message": ("шаг %d из %d (%s) не прошёл проверку, автоисправление не помогло (%d попыт.), выполнение остановлено"
                                % (idx + 1, plan["total"], step.get("path", ""), heal_attempts)),
                })
            print("--> [plan self-heal] шаг %d/%d не прошёл проверку, попытка %d/%d: %s"
                  % (idx + 1, plan["total"], heal_attempts + 1, MAX_ACTION_FIX_RETRIES, fail_reason))
            fixed = _self_heal_plan_step_action(step, fail_reason, idx, plan["total"])
            heal_attempts += 1
            if fixed is None:
                STATE["pending_plan"] = None
                server_state.queue_action_note((
                    "[Система: выполнение плана остановлено на шаге %d из %d (%s): %s. Модель не прислала "
                    "пригодное исправление. Уже выполненные шаги (%d) остались на диске.]"
                ) % (idx + 1, plan["total"], step.get("path", ""), fail_reason, idx))
                return jsonify({
                    "ok": False, "stopped": True, "index": idx, "total": plan["total"],
                    "chain_id": plan["chain_id"], "error": fail_reason,
                    "message": "шаг %d из %d (%s) не прошёл проверку, выполнение остановлено" % (idx + 1, plan["total"], step.get("path", "")),
                })
            step = fixed
            plan["steps"][idx] = fixed  # сохраняем исправленный шаг в плане (на случай повторной попытки)
            continue
        plan["applied_paths"].append(result.get("changed_path") or step.get("path", ""))
        plan["index"] = idx + 1
        done = plan["index"] >= plan["total"]
        step_msg = result["message"]
        if heal_attempts:
            step_msg += " (автоисправлено с учётом ошибки, попыток: %d)" % heal_attempts
        resp = {
            "ok": True, "done": done, "index": plan["index"], "total": plan["total"],
            "chain_id": plan["chain_id"],
            "message": "Шаг %d/%d: %s" % (plan["index"], plan["total"], step_msg),
        }
        # Адрес записи журнала этого шага. Панель сейчас показывает шаги плана
        # простыми строками (без карточек с кнопкой отката) и откатывает план
        # целиком через chain_id — поле задел на будущее, если появится откат
        # отдельного шага.
        if result.get("entry_id"):
            resp["history_entry_id"] = result["entry_id"]
        if result.get("changed_path"):
            resp["changed_path"] = result["changed_path"]
            resp["changed_block"] = result.get("changed_block", "")
        if step_diff:
            # Разобранный дифф шага — панель покажет его такой же свёрнутой
            # карточкой, как у одиночных действий: «файл +N -M».
            resp["step_diff"] = step_diff
        if done:
            STATE["pending_plan"] = None
            server_state.queue_action_note((
                "[Система: весь план из %d шаг(ов) успешно выполнен. Файлы: %s]"
            ) % (plan["total"], ", ".join(plan["applied_paths"])))
        return jsonify(resp)
    except Exception as e:
        traceback.print_exc()
        STATE["pending_plan"] = None
        return jsonify({"error": str(e)}), 500


@app.route('/chat/plan/stop', methods=['POST'])
def plan_stop():
    plan = STATE.get("pending_plan")
    if plan is None:
        return jsonify({"error": "Нет активного плана."}), 400
    idx, total = plan["index"], plan["total"]
    STATE["pending_plan"] = None
    server_state.queue_action_note((
        "[Система: Пользователь остановил выполнение плана вручную на шаге %d из %d. "
        "Сделанные шаги (%d) остались на диске, остальные отменены. При необходимости пользователь "
        "может откатить всю цепочку целиком.]"
    ) % (idx, total, idx))
    return jsonify({"stopped": True, "index": idx, "total": total, "chain_id": plan["chain_id"], "applied_paths": plan["applied_paths"]})


@app.route('/chat/plan/rollback_chain', methods=['POST'])
def plan_rollback_chain():
    data = request.json or {}
    chain_id = data.get('chain_id')
    force = bool(data.get('force', False))
    if not STATE.get("project_root"):
        return jsonify({"error": "Проект не синхронизирован."}), 400
    if not chain_id:
        return jsonify({"error": "Не указан chain_id."}), 400
    try:
        ok, msg, needs_force, paths, reverted_count, total_count = history.rollback_chain(
            STATE["project_root"], chain_id, force=force)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    if ok:
        _refresh_fs_snapshot(STATE.get("project_root"))
        STATE["file_cache"] = None  # содержимое откатилось — кэш diff устарел
        # Багфикс v105.8: как и в rollback_last — сообщаем индексу Библиотекаря
        # о файлах, затронутых откатом цепочки.
        try:
            librarian.note_files_changed(STATE.get("project_root"), paths or [])
        except Exception:
            pass  # худший случай — индекс достроится лениво по STALE_SEC
        note = (
            "[Система: Пользователь откатил всю цепочку вашего плана! %s. Скорректируйте подход, если эти файлы всё ещё нужны."
        ) % msg
        resp = {"success": True, "message": msg, "paths": list(paths or []),
                "reverted_count": reverted_count, "total_count": total_count}
        if "res://project.godot" in resp["paths"]:
            resp["requires_editor_restart"] = True
        # После отката всей цепочки файлы, добавленные планом в [autoload], больше не существуют — вычищаем их.
        removed_autoloads = clean_dangling_autoloads(STATE["project_root"])
        if removed_autoloads:
            resp["autoload_removed"] = removed_autoloads
            resp["project_godot_changed"] = True
            if "res://project.godot" not in resp["paths"]:
                resp["paths"].append("res://project.godot")
            note += (" В project.godot также убраны висячие записи автозагрузки (%s), "
                     "так как их файлы больше не существуют." % ", ".join(removed_autoloads))
        note += "]"
        server_state.queue_action_note(note)
        return jsonify(resp)
    return jsonify({"error": msg, "needs_force": needs_force,
                    "reverted_count": reverted_count, "total_count": total_count}), 409


# ---------------------------------------------------------------------------
# Ошибки последнего запуска игры: панель сперва получает сводку (в браузер
# НИЧЕГО не уходит), пользователь подтверждает — и только тогда модели
# отправляется ОДИН отчёт. Повторная отправка того же лога блокируется
# по отпечатку (mtime + размер), который переживает перезапуск сервера.
# ---------------------------------------------------------------------------

@app.route('/minilich/status', methods=['POST'])
def minilich_status():
    data = request.json or {}
    _apply_session_context(data)
    root = STATE.get("project_root")
    if not root:
        print("[minilich] /status:", "проект не синхронизирован, отвечаю enabled=False")
        return jsonify({"enabled": False, "examples": 0, "train_step": 0, "last_loss": None, "training_active": False, "params": 0, "disk_bytes": 0})
    try:
        _st = minilich.status(root, STATE.get("addon_dir"))
        if _st.get("storage"):
            print(u"[minilich] мозг (датасет+веса): %s" % _st.get("storage"))
        print("[minilich] /status: root=%s enabled=%s training_active=%s" % (root, _st.get("enabled"), _st.get("training_active")))
        if _st.get("start_error"):
            print("[minilich] /status: реальная ошибка запуска обучения: %s" % _st.get("start_error"))
        return jsonify(_st)
    except Exception as e:
        print("[minilich] /status: ошибка:", e)
        return jsonify({"error": str(e)}), 500


@app.route('/minilich/set', methods=['POST'])
def minilich_set():
    data = request.json or {}
    _apply_session_context(data)
    root = STATE.get("project_root")
    if not root:
        print("[minilich] /set:", "проект не синхронизирован — отказываю (400)")
        return jsonify({"error": "Проект не синхронизирован."}), 400
    has_enabled = "enabled" in data
    enabled = bool(data.get("enabled")) if has_enabled else bool(minilich.is_enabled(root))
    print(u"[minilich] /set: root=%s enabled=%s%s" % (root, enabled, u"" if has_enabled else u" (галочка mini-lich не менялась)"))
    try:
        if has_enabled:
            minilich.set_enabled(root, enabled)
        if "training_mode" in data:
            minilich.set_training_mode(root, bool(data.get("training_mode")))
            print("[minilich] /set: training_mode=%s" % bool(data.get("training_mode")))
        if "train_pause_sec" in data:
            minilich.set_train_pause(root, data.get("train_pause_sec"))
            print("[minilich] /set: train_pause_sec=%s" % data.get("train_pause_sec"))
        if enabled and has_enabled:
            _started = minilich.start_training(root, STATE.get("addon_dir"))
            if _started:
                print("[minilich] /set: start_training -> True (фоновый поток запущен)")
            else:
                _err = getattr(minilich, "_last_start_error", "")
                if _err:
                    print("[minilich] /set: start_training -> False, РЕАЛЬНАЯ ОШИБКА запуска: %s" % _err)
                else:
                    print("[minilich] /set: start_training -> False (уже работает с предыдущего раза — второй фон не нужен, это не ошибка)")
        elif has_enabled:
            minilich.stop_training()
        _st = minilich.status(root, STATE.get("addon_dir"))
        if _st.get("storage"):
            print(u"[minilich] мозг (датасет+веса): %s" % _st.get("storage"))
        print("[minilich] /set: сохранено, enabled=%s training_active=%s (перечитано с диска)" % (_st.get("enabled"), _st.get("training_active")))
        if _st.get("start_error"):
            print("[minilich] /set: реальная ошибка запуска обучения: %s" % _st.get("start_error"))
        return jsonify(_st)
    except Exception as e:
        print("[minilich] /set: ошибка:", e)
        return jsonify({"error": str(e)}), 500


@app.route('/minilich/github_fetch', methods=['POST'])
def minilich_github_fetch():
    """v81: сбор обучающих пар со сцен GitHub по кнопке из панели (в фоне)."""
    data = request.json or {}
    _apply_session_context(data)
    root = STATE.get("project_root")
    if not root:
        return jsonify({"error": "Проект не синхронизирован."}), 400
    repos_text = (data.get("repos") or "").strip()
    if not repos_text:
        return jsonify({"error": "Укажи ссылки на репозитории GitHub (через запятую или пробел)."}), 400
    started = minilich.github_fetch_async(root, STATE.get("addon_dir"), repos_text)
    if not started:
        return jsonify({"error": "Сбор с GitHub уже идёт — прогресс в журнале обучения."}), 409
    print("[minilich] /github_fetch: запущен сбор, repos=%s" % repos_text)
    return jsonify({"started": True})


@app.route('/librarian/query', methods=['POST'])
def librarian_query():
    """v105: та же справка Библиотекаря, но для панели Godot и отладки:
    можно посмотреть, что именно увидит модель по данному запросу."""
    data = request.json or {}
    root = data.get("project_root") or STATE.get("project_root")
    if not root:
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        answer_text = librarian.answer(root, str(data.get("query") or ""),
                                       addon_dir=STATE.get("addon_dir"))
        return jsonify({"success": True, "answer": answer_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/project/api_cache_status', methods=['POST'])
def api_cache_status():
    data = request.json or {}
    _apply_session_context(data)
    root = STATE.get("project_root")
    addon_dir = STATE.get("addon_dir")
    if not root:
        return jsonify({"cached_version": "", "has_cache": False})
    version = gd_api_cache.get_cached_version(root, addon_dir)
    return jsonify({"cached_version": version, "has_cache": bool(version) or gd_api_cache.has_cache(root, addon_dir)})


@app.route('/project/update_api_cache', methods=['POST'])
def update_api_cache():
    data = request.json or {}
    _apply_session_context(data)
    if not STATE.get("project_root"):
        return jsonify({"error": "\u041f\u0440\u043e\u0435\u043a\u0442 \u043d\u0435 \u0441\u0438\u043d\u0445\u0440\u043e\u043d\u0438\u0437\u0438\u0440\u043e\u0432\u0430\u043d."}), 400
    classes = data.get("classes")
    if not isinstance(classes, dict) or not classes:
        return jsonify({"error": "\u041f\u0443\u0441\u0442\u043e\u0439 \u0438\u043b\u0438 \u043d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0439 \u0441\u043f\u0438\u0441\u043e\u043a \u043a\u043b\u0430\u0441\u0441\u043e\u0432."}), 400
    godot_version = str(data.get("godot_version", ""))
    try:
        count = gd_api_cache.save_cache(STATE["project_root"], classes, godot_version, STATE.get("addon_dir"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    print("--> API cache updated: %d classes (Godot %s)" % (count, godot_version))
    return jsonify({"classes_count": count, "godot_version": godot_version})


@app.route('/project/refactor/file/preview', methods=['POST'])
def refactor_file_preview():
    data = request.json or {}
    _apply_session_context(data)
    old_path = data.get("old_path")
    new_path = data.get("new_path") or data.get("dest")
    update_refs = bool(data.get("update_references", True))
    project_root = STATE.get("project_root")
    if not project_root:
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        prepared = file_refactor.prepare_file_rename(
            project_root, old_path, new_path,
            update_references=update_refs,
            allow_addons=bool(STATE.get("addon_intent"))
        )
        diffs = [item["diff"] for item in prepared["files"]]
        return jsonify({
            "ok": True,
            "prepared": {
                "old_path": prepared["old_path"],
                "new_path": prepared["new_path"],
                "is_directory": prepared.get("is_directory", False),
                "moved_files": prepared.get("moved_files", {}),
                "reference_count": prepared["reference_count"],
                "file_count": len(prepared["files"]),
                "affected_paths": prepared["affected_paths"],
                "diffs": diffs,
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/project/refactor/file/apply', methods=['POST'])
def refactor_file_apply():
    data = request.json or {}
    _apply_session_context(data)
    old_path = data.get("old_path")
    new_path = data.get("new_path") or data.get("dest")
    update_refs = bool(data.get("update_references", True))
    project_root = STATE.get("project_root")
    if not project_root:
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        prepared = file_refactor.prepare_file_rename(
            project_root, old_path, new_path,
            update_references=update_refs,
            allow_addons=bool(STATE.get("addon_intent"))
        )
        result = file_refactor.apply_prepared_file_rename(
            project_root, prepared, *_current_chat_info()
        )
        changed_paths = result["changed_paths"]
        try:
            librarian.note_files_changed(project_root, changed_paths, deleted=[result["old_path"]])
        except Exception:
            pass
        for changed_path in changed_paths:
            _remember_file(project_root, changed_path)
            _touch_file_read(changed_path)
        _forget_file(result["old_path"])
        _refresh_fs_snapshot(project_root)
        return jsonify({
            "ok": True,
            "entry_id": result["entry_id"],
            "old_path": result["old_path"],
            "new_path": result["new_path"],
            "changed_paths": result["changed_paths"],
            "reference_count": result["reference_count"],
            "file_count": result["file_count"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/scene/refactor/node/preview', methods=['POST'])
def refactor_node_preview():
    data = request.json or {}
    _apply_session_context(data)
    scene = data.get("scene")
    node_path = data.get("node_path") or data.get("node")
    new_name = data.get("new_name") or data.get("name")
    project_root = STATE.get("project_root")
    if not project_root:
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        prepared = node_refactor.prepare_node_rename(
            project_root, scene, node_path, new_name,
            allow_addons=bool(STATE.get("addon_intent"))
        )
        diffs = [item["diff"] for item in prepared["files"]]
        return jsonify({
            "ok": True,
            "prepared": {
                "scene": prepared["scene_res"],
                "node_path": prepared["target_node_path"],
                "new_name": prepared["new_name"],
                "reference_count": prepared["reference_count"],
                "file_count": len(prepared["files"]),
                "affected_paths": prepared["affected_paths"],
                "diffs": diffs,
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/scene/refactor/node/apply', methods=['POST'])
def refactor_node_apply():
    data = request.json or {}
    _apply_session_context(data)
    scene = data.get("scene")
    node_path = data.get("node_path") or data.get("node")
    new_name = data.get("new_name") or data.get("name")
    project_root = STATE.get("project_root")
    if not project_root:
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        prepared = node_refactor.prepare_node_rename(
            project_root, scene, node_path, new_name,
            allow_addons=bool(STATE.get("addon_intent"))
        )
        result = node_refactor.apply_prepared_node_rename(
            project_root, prepared, *_current_chat_info()
        )
        changed_paths = result["changed_paths"]
        try:
            librarian.note_files_changed(project_root, changed_paths)
        except Exception:
            pass
        for changed_path in changed_paths:
            _remember_file(project_root, changed_path)
            _touch_file_read(changed_path)
        _refresh_fs_snapshot(project_root)
        return jsonify({
            "ok": True,
            "entry_id": result["entry_id"],
            "scene": result["scene_res"],
            "node_path": result["target_node_path"],
            "new_name": result["new_name"],
            "changed_paths": result["changed_paths"],
            "reference_count": result["reference_count"],
            "file_count": result["file_count"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/scene/refactor/node/reparent/preview', methods=['POST'])
def refactor_node_reparent_preview():
    data = request.json or {}
    _apply_session_context(data)
    scene = data.get("scene")
    node_path = data.get("node_path") or data.get("node")
    new_parent = data.get("new_parent") or data.get("parent")
    project_root = STATE.get("project_root")
    if not project_root:
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        prepared = node_refactor.prepare_node_reparent(
            project_root, scene, node_path, new_parent,
            allow_addons=bool(STATE.get("addon_intent"))
        )
        diffs = [item["diff"] for item in prepared["files"]]
        return jsonify({
            "ok": True,
            "prepared": {
                "scene": prepared["scene_res"],
                "node_path": prepared["target_node_path"],
                "new_parent": prepared["new_parent"],
                "new_path": prepared["new_path"],
                "reference_count": prepared["reference_count"],
                "file_count": len(prepared["files"]),
                "affected_paths": prepared["affected_paths"],
                "diffs": diffs,
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/scene/refactor/node/reparent/apply', methods=['POST'])
def refactor_node_reparent_apply():
    data = request.json or {}
    _apply_session_context(data)
    scene = data.get("scene")
    node_path = data.get("node_path") or data.get("node")
    new_parent = data.get("new_parent") or data.get("parent")
    project_root = STATE.get("project_root")
    if not project_root:
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        prepared = node_refactor.prepare_node_reparent(
            project_root, scene, node_path, new_parent,
            allow_addons=bool(STATE.get("addon_intent"))
        )
        result = node_refactor.apply_prepared_node_refactor(
            project_root, prepared, *_current_chat_info()
        )
        changed_paths = result["changed_paths"]
        try:
            librarian.note_files_changed(project_root, changed_paths)
        except Exception:
            pass
        for changed_path in changed_paths:
            _remember_file(project_root, changed_path)
            _touch_file_read(changed_path)
        _refresh_fs_snapshot(project_root)
        return jsonify({
            "ok": True,
            "entry_id": result["entry_id"],
            "scene": result["scene_res"],
            "node_path": result["target_node_path"],
            "new_parent": result["new_parent"],
            "new_path": result["new_path"],
            "changed_paths": result["changed_paths"],
            "reference_count": result["reference_count"],
            "file_count": result["file_count"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/scene/refactor/node/delete/preview', methods=['POST'])
def refactor_node_delete_preview():
    data = request.json or {}
    _apply_session_context(data)
    scene = data.get("scene")
    node_path = data.get("node_path") or data.get("node")
    cleanup_code = bool(data.get("cleanup_code", True))
    project_root = STATE.get("project_root")
    if not project_root:
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        prepared = node_refactor.prepare_node_deletion(
            project_root, scene, node_path,
            cleanup_code=cleanup_code,
            allow_addons=bool(STATE.get("addon_intent"))
        )
        diffs = [item["diff"] for item in prepared["files"]]
        return jsonify({
            "ok": True,
            "prepared": {
                "scene": prepared["scene_res"],
                "node_path": prepared["target_node_path"],
                "deleted_nodes": prepared["deleted_nodes"],
                "reference_count": prepared["reference_count"],
                "file_count": len(prepared["files"]),
                "affected_paths": prepared["affected_paths"],
                "diffs": diffs,
                "warnings": prepared.get("warnings", []),
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/scene/refactor/node/delete/apply', methods=['POST'])
def refactor_node_delete_apply():
    data = request.json or {}
    _apply_session_context(data)
    scene = data.get("scene")
    node_path = data.get("node_path") or data.get("node")
    cleanup_code = bool(data.get("cleanup_code", True))
    project_root = STATE.get("project_root")
    if not project_root:
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        prepared = node_refactor.prepare_node_deletion(
            project_root, scene, node_path,
            cleanup_code=cleanup_code,
            allow_addons=bool(STATE.get("addon_intent"))
        )
        result = node_refactor.apply_prepared_node_refactor(
            project_root, prepared, *_current_chat_info()
        )
        changed_paths = result["changed_paths"]
        try:
            librarian.note_files_changed(project_root, changed_paths)
        except Exception:
            pass
        for changed_path in changed_paths:
            _remember_file(project_root, changed_path)
            _touch_file_read(changed_path)
        _refresh_fs_snapshot(project_root)
        return jsonify({
            "ok": True,
            "entry_id": result["entry_id"],
            "scene": result["scene_res"],
            "node_path": result["target_node_path"],
            "deleted_nodes": result["deleted_nodes"],
            "changed_paths": result["changed_paths"],
            "reference_count": result["reference_count"],
            "file_count": result["file_count"],
            "warnings": prepared.get("warnings", []),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/project/check_log', methods=['POST'])
def check_log():
    data = request.json or {}
    _apply_session_context(data)
    if not STATE.get("project_root"):
        return jsonify({"error": "Проект не синхронизирован."}), 400
    if not STATE.get("user_data_dir"):
        return jsonify({"error": "Панель не передала путь user:// (обновите agent_panel.gd)."}), 400
    if STATE["pending_action"] is not None or STATE["pending_batch"] is not None:
        return jsonify({"error": "Сначала завершите текущее подтверждение действия."}), 409
    ok, report = log_reader.collect_errors(
        STATE["user_data_dir"], STATE["project_root"],
        history.get_storage_dir(STATE["project_root"]))
    if not ok:
        return jsonify({"error": report}), 404
    log_info = f"{report['log_time']} ({report['age_minutes']} мин назад)"
    if not report["errors"]:
        return jsonify({"found": 0, "log_time": log_info})
    if report["already_sent"]:
        return jsonify({"error": "Этот лог (" + log_info + ") уже отправлялся модели — "
                        "новых запусков игры с тех пор не было. Запустите игру ещё раз."}), 409
    STATE["pending_log_report"] = report
    print(f"--> Лог запуска: найдено {len(report['errors'])} уникальных ошибок (лог от {report['log_time']})")
    return jsonify({
        "found": len(report["errors"]),
        "log_time": log_info,
        "summary": log_reader.build_summary(report),
    })


@app.route('/project/send_log_errors', methods=['POST'])
def send_log_errors():
    report = STATE.get("pending_log_report")
    if not report:
        return jsonify({"error": "Нет подготовленного отчёта. Нажмите «Ошибки запуска» заново."}), 400
    project_root = STATE.get("project_root")
    try:
        message = log_reader.format_report(report)
        note = server_state.peek_action_note_for_current()
        if note:
            message = f"{note}\n\n{message}"
        # v104.2: сверка с записью чата — как в /chat (не шлём мега-промпт
        # повторно в уже обученный чат).
        from agent_prompts import PROMPT_HASH as _ph
        if (not STATE.get("is_primed", False)
                and server_state.chat_already_primed(_ph)):
            STATE["is_primed"] = True
            _save_primed(project_root, True)
        _need_prime = not STATE.get("is_primed", False)
        if _need_prime:
            print("\n---> Авто-инициализация сессии и отправка мега-промпта...")
            system_context = _build_priming_context(project_root)
            message = f"{system_context}\n\n{message}"
        print(f"--> Отправка отчёта об ошибках запуска ({len(message)} симв.)")
        text, action = _reply_with_self_heal(message, project_root)
        packaged = _package_model_reply(text, action, project_root)
        status = (int(packaged[1]) if isinstance(packaged, tuple)
                  and len(packaged) > 1 else
                  int(getattr(packaged, "status_code", 200) or 200))
        if status >= 400:
            return packaged
        # Одноразовое состояние потребляем только после принятого ответа.
        STATE["pending_log_report"] = None
        log_reader.save_sent_fingerprint(
            history.get_storage_dir(project_root), report["fingerprint"])
        server_state.consume_action_note_for_current(note)
        if _need_prime:
            # v104.2: флаг — только ПОСЛЕ успешной отправки, и теперь он ещё и
            # сохраняется (раньше здесь не было ни _save_primed, ни
            # mark_chat_prompt_version — после перезапуска мега-промпт уходил заново).
            STATE["is_primed"] = True
            _save_primed(project_root, True)
            server_state.mark_chat_prompt_version()
        return packaged
    except Exception as e:
        print(f"❌ ОШИБКА send_log_errors: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# --- v88.11: живой ввод — зеркалирование текста панели в поле сайта ---

def _live_prefer_url():
    """Адрес вкладки ТЕКУЩЕГО чата — печатаем в неё, а не в первую попавшуюся."""
    rec = server_state.get_current_chat() or {}
    return rec.get("url") or None


def _live_parser():
    return getattr(_current_parser(), "PARSER", None)


_live_mirror = live_input.LiveInputMirror(
    get_driver=server_state.get_driver,   # БЕЗ wait_driver: нет браузера — просто пропуск
    get_parser=_live_parser,
    busy_fn=server_state.exchange_active,
    prefer_url_fn=_live_prefer_url)


@app.route('/chat/live_input', methods=['POST'])
def chat_live_input():
    """v88.11: живой ввод — панель шлёт текст по мере набора, сервер вставляет
    его в поле ввода сайта (без отправки). Best effort: любые проблемы ->
    {"applied": false, "reason": ...}, ошибок наружу не бросаем."""
    data = request.json or {}
    # Hold the existing browser-mutation reservation until request teardown.
    if not server_state.try_begin_navigation():
        return jsonify({"ok": True, "applied": False, "reason": "busy"})
    return jsonify(_live_mirror.apply(data.get("seq"), data.get("text", "")))


@app.route('/chat/stop', methods=['POST'])
def chat_stop():
    """Остановить текущую обработку запроса (кнопка «Стоп» в панели)."""
    busy = bool((STATE.get("progress") or {}).get("active"))
    server_state.request_cancel()
    print("--> Запрошена остановка обработки (шла обработка: %s)." % busy)
    return jsonify({"ok": True, "was_busy": busy})


@app.route('/dashboard', methods=['GET'])
def dashboard_page():
    """v80: страница-дашборд: секторы со статистикой + копируемый журнал."""
    return app.response_class(dashboard.DASHBOARD_HTML, mimetype="text/html")


@app.route('/dashboard/data', methods=['GET'])
def dashboard_data():
    root = STATE.get("project_root")
    ml = {}
    if root:
        try:
            ml = minilich.status(root, STATE.get("addon_dir"))
        except Exception as e:
            ml = {"error": str(e)}
    plan = STATE.get("pending_plan") or {}
    return jsonify({
        "uptime": dashboard.uptime_text(),
        "project_root": root or "",
        "pending_action": bool(STATE.get("pending_action")),
        "plan": {"active": bool(plan), "index": int(plan.get("index", 0) or 0), "total": int(plan.get("total", 0) or 0)},
        "minilich": ml,
        "log": dashboard.get_lines(),
    })


@app.route('/chat/progress', methods=['GET'])
def chat_progress():
    # Живая трансляция для панели: что сейчас происходит в браузере.
    # ВАЖНО: эндпоинт НЕ трогает Selenium (браузером занят поток /chat),
    # он только читает последний снимок состояния — поэтому безопасен
    # при одновременном длинном запросе.
    return jsonify(STATE.get("progress") or {"active": False})


def _boot_browser_background():
    """Запуск Chrome В ФОНЕ и ТОЛЬКО ПО ТРЕБОВАНИЮ: HTTP-сервер поднимается
    сразу, а браузер запускается при первом обращении к wait_driver() (то
    есть при первом браузерном чате). В режиме работы по ключу API браузер
    не нужен вообще — не открываем лишнее окно и не тратим память."""
    try:
        set_driver(setup_browser())
        print("\u2705 Браузер готов.")
    except Exception as e:
        traceback.print_exc()
        set_driver_error(e)


def _disable_quickedit():
    """v86.5: консоль Windows в режиме QuickEdit «замирает» от одного случайного
    клика мышью: выделение текста блокирует print() у ВСЕХ потоков, и сервер
    (включая обучение mini-lich) стоит, пока не нажата клавиша. Выключаем
    QuickEdit у своей консоли; выделять текст по-прежнему можно через меню окна
    (правый клик по заголовку -> Изменить -> Пометить)."""
    try:
        import ctypes
        import os as _os
        if _os.name != "nt":
            return
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k32.GetConsoleMode(h, ctypes.byref(mode)):
            return  # своей консоли нет (запуск без окна) — нечего чинить
        ENABLE_QUICK_EDIT = 0x0040
        ENABLE_EXTENDED_FLAGS = 0x0080
        k32.SetConsoleMode(h, (mode.value & ~ENABLE_QUICK_EDIT) | ENABLE_EXTENDED_FLAGS)
        print("--> Защита консоли: QuickEdit выключен — случайный клик мышью больше не замораживает сервер.")
    except Exception:
        pass


if __name__ == '__main__':
    try:
        _disable_quickedit()
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        # Браузер больше не стартует безусловно: регистрируем функцию запуска,
        # а поднимет его первое же обращение к wait_driver() — то есть первый
        # браузерный чат. Чату по ключу API браузер не нужен.
        server_state.set_browser_booter(_boot_browser_background)
        # Настройки DoH могли быть заданы в прошлой сессии — применяем их до
        # первого запроса, иначе первый обмен ушёл бы через системный DNS.
        try:
            _dns = api_keys.apply_dns_settings()
            if _dns.get("enabled"):
                print("--> DNS over HTTPS: %s" % _dns.get("url"))
        except Exception as e:
            print("--> Не удалось применить настройки DNS: %s" % e)
        # ВАЖНО: только 127.0.0.1! На 0.0.0.0 любой в локальной сети
        # мог бы писать файлы в ваш проект простым POST-запросом.
        print("Dashbord servera: http://127.0.0.1:5000/dashboard")
        app.run(port=5000, host='127.0.0.1', threaded=True)
    except Exception as e:
        traceback.print_exc()
        input()
