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
    read_project_file,
    create_project_file,
    patch_project_file,
    move_project_file,
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
import log_reader
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
    p = str(path).replace("\\", "/")
    if p.startswith("res://"):
        p = p[len("res://"):]
    p = p.lstrip("/")
    return p.startswith("addons/")


def _addon_blocked_message(path):
    return (
        "Путь %s находится в папке аддона (res://addons/...). Правки аддонов разрешены ТОЛЬКО "
        "когда пользователь явно попросил об этом в своём сообщении (словами \u00abаддон\u00bb/\u00abaddon\u00bb). "
        "Если это действительно нужно — спроси пользователя напрямую, прежде чем предлагать действие "
        "над файлами аддона; не запрашивай и не изменяй файлы аддона по своей инициативе." % path
    )
import server_state
from server_state import (
    STATE, get_driver, set_driver, wait_driver, set_driver_error,
    _prime_flag_path, _load_primed, _save_primed,
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

from chat_routes import chats_bp

app = Flask(__name__)
app.register_blueprint(chats_bp)


def _current_parser():
    """Модуль-парсер по сайту ТЕКУЩЕГО чата (aistudio -> ai_parser,
    deepseek -> deepseek_parser, ...). Если чат не помнит сайт (старые чаты) —
    определяем по адресу открытой страницы браузера."""
    site_id = None
    try:
        base = server_state._chats_dir()
        cid = STATE.get("current_chat_id")
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


def _reply(prompt):
    """Один запрос-ответ к модели, без какой-либо логики восстановления."""
    server_state.clear_cancel()
    _set_progress({"phase": "отправляю запрос в браузер"})
    try:
        # v54: адрес текущего чата — чтобы печатать в ЕГО вкладку, а не в первую
        # попавшуюся вкладку сайта (у пользователя могла быть открыта вкладка старого чата).
        _chat_rec = server_state.get_current_chat() or {}
        result = _current_parser().send_message_and_get_response(
            wait_driver(), prompt, progress_cb=_set_progress,
            cancel_cb=server_state.cancel_requested,
            prefer_url=_chat_rec.get("url") or None)
    except parser_base.ParserCancelled:
        print("<-- Запрос остановлен пользователем.")
        return "[Остановлено] Запрос прерван кнопкой «Стоп».", None
    finally:
        _clear_progress()
    if isinstance(result, dict):
        text, action = result.get("text") or "", result.get("action")
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
        if (not STATE.get("addon_intent")) and (_is_addon_path(step.get("path")) or _is_addon_path(step.get("dest"))):
            return False, (
                "шаг %d трогает файл аддона (res://addons/...), а пользователь это явно не запрашивал. "
                "Не включай аддоны в план, если пользователь явно не попросил изменить аддон." % (i + 1)
            )
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
    \"continues\": true, поля content_part/content_parts_total). Во����вращает
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


def _apply_write_step(action, project_root, chain_id=None):
    """Применяет ОДНО write-действие (create_file/patch_file/move_file) на диске,
    с записью в журнал изменений. Общий путь для одиночных действий
    и для шагов плана (chain_id задаётся только во втором случае).
    Возвращает dict: {"ok", "message", "changed_path", "changed_block"}."""
    act_type = action.get("action")
    path = action.get("path", "")
    dest = action.get("dest", "")
    if (not STATE.get("addon_intent")) and (_is_addon_path(path) or _is_addon_path(dest)):
        return {"ok": False, "message": _addon_blocked_message(path if _is_addon_path(path) else dest),
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
    if act_type != "move_file":
        _touch_file_read(path)
    if act_type == "create_file":
        message = ("Файл полностью перезаписан: %s" % path) if overwrote else ("Файл успешно создан: %s" % path)
        return {"ok": True, "message": message, "changed_path": path, "changed_block": action.get("content", "")}
    if act_type == "patch_file":
        return {"ok": True, "message": "Изменения успешно внесены в файл: %s" % path, "changed_path": path, "changed_block": action.get("replace", "")}
    return {"ok": True, "message": "Файл успешно перемещён в: %s" % action.get("dest", ""), "changed_path": None, "changed_block": None}


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
            parts.append("[Система]: Пользователь ��ТКАЗАЛСЯ показывать файл %s. НЕ запрашивай его повторно; работай без него или объясни пользователю, зачем он нужен." % f["path"])
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
                "Файл %s запроси ц��ликом через read_file." % path)
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


def _package_model_reply(text, action, project_root, depth=0):
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
        if depth >= MAX_CONTENT_PARTS + 3 or (not ok_part and depth >= 2):
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
    if action and action.get("action") in ("read_file", "read_files", "read_function"):
        STATE["pending_action"] = None
        STATE["pending_batch"] = _start_read_batch(action, project_root)
        nxt = _next_batch_confirmation()
        if nxt is None:
            # Все запрошенные файлы missing — сообщаем модели сразу (1 запрос),
            # но не глубже 2 раз — защита от зацикливания на несуществующих путях.
            followup = _finish_read_batch(project_root)
            if depth >= 2:
                return jsonify({"answer": text + "\n\n" + followup, "pending_action": None})
            text2, act2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, act2, project_root, depth + 1)
        return jsonify({"answer": text, "next_confirmation": nxt})
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
        if pairs:
            _refresh_fs_snapshot(project_root)
        if not pairs:
            followup = ("[Система]: copy_file пришёл без пар src/dest. Пришли заново: "
                        '{"action":"copy_file","copies":[{"src":"res://...","dest":"res://..."}]}.')
        else:
            followup = ("[Система]: Результат копирования (файлы ско��ированы БЕЗ изменений; "
                        "адаптацию под проект делай через patch_file, он ��отребует подтверждения):\n"
                        + "\n".join(results))
        if depth >= 3:
            return jsonify({"answer": (text + "\n\n" + followup).strip(), "pending_action": None})
        text2, act2 = _reply_with_self_heal(followup, project_root)
        return _package_model_reply(text2, act2, project_root, depth + 1)
    if action and action.get("action") == "plan":
        STATE["pending_action"] = None
        # Многочастный план: модель присылает шаги нескольким�� сообщениями
        # ("continues": true), если все шаги не помещаются в один ответ
        # (не хватает выходного лимита токенов). Пользователь увидит и
        # подтвердит склеенный план ОДИН раз — целиком, за один проход.
        if action.get("continues"):
            ok_part, followup = _plan_part_add(action)
            if depth >= MAX_PLAN_PARTS + 4 or (not ok_part and depth >= 2):
                STATE["plan_parts"] = None
                return jsonify({"answer": (text + "\n\n" + followup).strip(), "pending_action": None})
            text2, act2 = _reply_with_self_heal(followup, project_root)
            return _package_model_reply(text2, act2, project_root, depth + 1)
        steps, plan_description = _plan_collect_final(action)
        ok, err = _validate_plan_steps(steps, max_steps=MAX_PLAN_TOTAL_STEPS)
        if not ok:
            followup = "[Система]: план отклонён автоматически: %s Исправь и пришли agent_action заново (action=plan; если все шаги не помещаются в один ответ — частями через \"continues\": true)." % err
            if depth >= 2:
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
    if not text and action is None:
        # Пустой ответ из браузера: парсер мог не дождаться конца генерации
        # длинного ответа. Не молчим — пользователь должен это увидеть.
        text = ("[Система]: ⚠ Из браузера пришёл ПУСТОЙ ответ. Скорее всего, м��дель "
                "ещ�� генерировала текст, а парсер не дождался конца. Ответ, вероятно, "
                "виден во вклад��е AI Studio. Можно написать модели: 'повтори последний ответ'.")
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
    })


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
    ПОСЛ�� того, как текущий чат в последний раз видел его содержим��е, —
    оп������сен: модель молча сотрёт чужую работу. Возвращает текст системного
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
        "но он изменялся из ДРУГОГО чата после того, как ты в последн��й раз видел его содержимое. "
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


def _lint_action_code(action, project_root, planned_paths=None):
    """Самопроверка кода ДО показа действия пользователю: гоняем лёгкий
    линтер по ИТОГОВОМУ тексту .gd-файла (каким он станет после create/patch).
    Возвращает текст системного сообщения для модели или None, если код чист."""
    kind = action.get("action")
    path = action.get("path", "") or ""
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
    listing = "\n".join("- %s" % p for p in problems[:8])
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
    возвращаются модели на самоисправлени��."""
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
# если нет — на него записывается причина отказа, и обраба��ывается следующий
# битый шаг по кругу, пока бюджет не закончится.
#
# Если после этого lenient_bad опустел — план собирается заново из
# lenient_good, и обработка продолжается как обычный action=plan (дальше
# план валидируется/подтверждается пользователем как всегда).
#
# Если бюджет попыток исчерпан, а lenient_bad всё ещё не пуст, но
# lenient_good не пуст — план всё равно собирается из того, что удалось
# распознать (лучше отдать пользователю частичный результат, чем ничего), а
# в text дописывается явное пр��дупреждение: сколько шагов принято, сколько и
# какие (номер + путь, если удалось угадать) отброшены и почему, с советом
# попросить модель прислать отброшенные шаги отдельным сообщением.
#
# Если сырой ответ вообще не похож на план, или из него не удалось вытащить
# ни одног�� шага (ни good, ни bad) — ведём себя как раньше: обычный общий
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
                    "стро��овых значений. Никакого текста вне JSON-блока."
                )
                text, action = _reply(fix_prompt)
                continue
            lenient_good = list(lenient["good_steps"])
            lenient_bad = list(lenient["bad_steps"])
            print(f"--> [self-heal] план р��спознан частично: {len(lenient_good)} шаг(ов) ок, "
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
                    ("Уже принятые шаги (НЕ присылай ��х повторно): " + ", ".join(p for p in accepted_paths if p))
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
                    "��опроси модель прислать отброшенные шаги отдельным сообщением, если они нужны."
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
                # Модель только что увидела АКТУАЛЬНОЕ содержим��е файла с диска.
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
    (пользователь удалил сцену, поменял ск��ипт руками, что-то добавил), или "".
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
    """Мега-промпт: умное д��рево (полное для маленького проекта, сводка по
    папкам для большого) + описание архитектуры проекта. Если проект пустой —
    агент сам создаёт стандартную архитектуру для игр."""
    try:
        created = ensure_standard_architecture(project_root)
    except Exception:
        created = []
    if created:
        print("--> Проект ��уст: создана стандартная архитектура (%d папок)" % len(created))
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
    _refresh_fs_snapshot(project_root)  # созданные ��апки — не «внешние» изменения
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
    data = request.json or {}
    STATE["project_root"] = data.get('project_root')
    # v87.9: точная версия движка для мега-промпта (плагин шлёт её в /init).
    _gv = str(data.get("godot_version") or "").strip()
    if _gv:
        STATE["godot_version"] = _gv
    _apply_session_context(data)
    STATE["pending_action"] = None
    STATE["pending_batch"] = None
    STATE["action_notes"] = {}  # v45: словарь chat_id -> заметка, а не одна общая строка
    STATE["pending_log_report"] = None
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

    if STATE["pending_action"] is not None:
        return jsonify({"error": "Есть неподтверждённое действие агента."}), 409
    if STATE["pending_batch"] is not None:
        return jsonify({"error": "Есть неподтверждённые запросы файлов агента."}), 409

    _apply_session_context(data)
    STATE["pending_log_report"] = None  # новое сообщение отменяет неотправленный отчёт
    STATE["plan_parts"] = None  # незавершённые части плана от прошлого обмена сбрасываются
    # Каждое НОВОе сообщение пользователя занова решает, ��азрешены ли в этом ходе действия над
    # аддонами (res://addons/...) — только когда он сам упомянул аддон/addon в тексте. Сбрасывается и
    # задаётся заново на каждое такое сообщение, а не один раз, чтобы досту�� к аддонам не застревал нав��егда.
    STATE["addon_intent"] = bool(_ADDON_INTENT_RE.search(prompt or ""))
    current_root = STATE.get("project_root")
    _ensure_current_chat(prompt)
    # Страховка: если история ТЕКУЩЕГО чата пуста — это первое сообщен��е,
    # и мега-промпт нужен ВСЕГДА: глобальный флаг мог остаться от старого чата
    # или подгрузиться с диска при /init уже П��СЛЕ создания нового чата.
    _cur_chat = server_state.get_current_chat()
    if _cur_chat is not None and not _cur_chat.get("transcript"):
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
        note = server_state.pop_action_note_for_current()
        if note:
            prompt = f"{note}\n\n{prompt}"

        # Сводка «что изменилось, пока чат был неа��тивен» (готовится при
        # открытии чата, отправляется ОДИН раз с первым сообщением).
        stale = STATE.get("stale_note", "")
        if stale:
            prompt = f"{stale}\n\n{prompt}"
            STATE["stale_note"] = ""

        # Файлы, изменённые ВНЕ агента (пользоват��ль удалил сцену, поменял
        # скрипт руками...) — модель узнаёт об этом вместе с этим сообщением.
        ext_note = _external_changes_note(current_root)
        if ext_note:
            print("--> Обнаружены внешние изменения файлов проекта, сообщаем модели")
            prompt = f"{ext_note}\n\n{prompt}"

        if not STATE.get("is_primed", False):
            print("\n---> Авто-инициализация сессии и отправка мега-промпта...")
            system_context = _build_priming_context(current_root)
            final_prompt = f"{system_context}\n\n[ЗАДАНИЕ ОТ ПОЛЬЗОВАТЕЛЯ]:\n{prompt}"
            text, action = _reply_with_self_heal(final_prompt, current_root)
            STATE["is_primed"] = True
            _save_primed(current_root, True)
            server_state.mark_chat_prompt_version()  # v48: запомнить версию промпта у чата
        else:
            print(f"\n---> Отправка сообщения ({len(prompt)} симв.)")
            text, action = _reply_with_self_heal(prompt, current_root)

        return _package_model_reply(text, action, current_root)
    except Exception as e:
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
        return jsonify({"error": "Нет ожидающего подтвер��дения действия."}), 400

    act_type = action.get("action")
    path = action.get("path", "")
    try:
        if not approved:
            print(f"--> Действие '{act_type}' ОТКЛОНЕНО пользователем.")
            server_state.queue_action_note(f"[Система: Пользователь ОТКЛОНИЛ ваше действие {act_type} для {path}. Изменение НЕ было применено! Скорректируй подход.]")
            STATE["pending_action"] = None
            return jsonify({"answer": "[Система]: Действие отклонено пользователем.", "pending_action": None})

        if act_type in ("create_file", "patch_file", "move_file"):
            print(f"--> {act_type} {path}. Выполняем локально...")
            result = _apply_write_step(action, project_root)
            STATE["pending_action"] = None
            if not result["ok"]:
                raise RuntimeError(result["message"])
            # changed_path/changed_block — панель откроет файл в редакторе и
            # подсветит строки, которые написал агент.
            resp = {"answer": "[Система]: " + result["message"], "pending_action": None}
            if result.get("changed_path"):
                resp["changed_path"] = result["changed_path"]
                resp["changed_block"] = result.get("changed_block", "")
            return jsonify(resp)

        elif act_type == "search_project":
            query = str(action.get("query", ""))
            STATE["pending_action"] = None
            if not query.strip():
                followup = "[Система]: search_project пришёл с ПУСТЫМ 'query' — поиск н�� выполнен. Пришли действие заново с непустым query."
            else:
                print(f"--> Поиск по проекту: {query!r}")
                results, truncated = search_project_text(project_root, query)
                followup = _format_search_results(query, results, truncated)
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
        STATE["pending_action"] = None
        print(f"❌ ОШИБКА confirm_action: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/chat/rollback/preview', methods=['POST'])
def rollback_preview():
    """Что именно отменит откат — панель показывает это в диалоге
    подтверждения, чтобы не откатить вслепую действие другого чата."""
    if not STATE.get("project_root"):
        return jsonify({"error": "Проект не синхронизирован."}), 400
    info = history.last_committed_info(STATE["project_root"])
    if not info:
        return jsonify({"found": False})
    kind_ru = {"create_file": "перезапись файла" if info.get("overwrote") else "создание фай��а",
               "patch_file": "правка файла", "move_file": "перемещение файла"}
    desc = "%s %s" % (kind_ru.get(info["type"], info["type"]), info["path"])
    when = time.strftime("%H:%M", time.localtime(info.get("ts", 0)))
    title = info.get("chat_title") or ""
    if title:
        src = "чат «%s», %s" % (title, when)
    else:
        src = "%s, чат неизвестен (изменение сделано до обновления)" % when
    resp = {"found": True, "description": "%s (%s)" % (desc, src)}
    # если последнее действие — шаг неоткатанной цепочки плана из >1 шага — панель должна
    # предложить откатить всю цепочку, а не по одному действию.
    if info.get("chain_id") and info.get("chain_total", 0) > 1:
        resp["chain_id"] = info["chain_id"]
        resp["chain_total"] = info["chain_total"]
    return jsonify(resp)


@app.route('/chat/rollback', methods=['POST'])
def rollback():
    data = request.json or {}
    force = bool(data.get('force', False))
    if not STATE.get("project_root"):
        return jsonify({"error": "Проект не синхронизирован."}), 400
    try:
        ok, msg, needs_force, paths, diff = history.rollback_last(STATE["project_root"], force=force)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    if ok:
        _refresh_fs_snapshot(STATE.get("project_root"))
        STATE["file_cache"] = None  # содержимое откатилось — кэш diff устарел
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
# Plan-режим (ц��почка действий): после подтверж��ения всего плана в confirm_action
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
        while True:
            _plan_paths = set(s.get("path") or "" for s in plan["steps"] if s.get("action") == "create_file")
            lint_msg = _lint_action_code(step, project_root, planned_paths=_plan_paths) if step.get("action") != "move_file" else None
            if lint_msg is None:
                result = _apply_write_step(step, project_root, chain_id=plan["chain_id"])
                if result["ok"]:
                    break
                fail_reason = result["message"]
            else:
                fail_reason = _lenient_resend_note(step, lint_msg)
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
        if result.get("changed_path"):
            resp["changed_path"] = result["changed_path"]
            resp["changed_block"] = result.get("changed_block", "")
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
        note = (
            "[Система: Пользователь откатил всю цепочку вашего плана! %s. Скорректируйте подход, если эти файлы всё ещё нужны."
        ) % msg
        resp = {"success": True, "message": msg, "paths": list(paths or []),
                "reverted_count": reverted_count, "total_count": total_count}
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
# отпр��вляется ОДИН отчёт. Повторная отправка того же лога блокируется
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
        return jsonify({"error": "Нет подготовленного отчёт��. Нажмите «Ошибки запуска» заново."}), 400
    STATE["pending_log_report"] = None
    project_root = STATE.get("project_root")
    try:
        # Фиксируем отпечаток ДО отправки: этот ж�� лог больше не отправить.
        log_reader.save_sent_fingerprint(history.get_storage_dir(project_root), report["fingerprint"])
        message = log_reader.format_report(report)
        note = server_state.pop_action_note_for_current()  # v45: только заметка своего чата
        if note:
            message = f"{note}\n\n{message}"
        if not STATE.get("is_primed", False):
            print("\n---> Авто-инициализация сессии и отправка мега-промпта...")
            system_context = _build_priming_context(project_root)
            message = f"{system_context}\n\n{message}"
            STATE["is_primed"] = True
        print(f"--> Отправка отчёта об ошибках запуска ({len(message)} симв.)")
        text, action = _reply_with_self_heal(message, project_root)
        return _package_model_reply(text, action, project_root)
    except Exception as e:
        print(f"❌ ОШИБКА send_log_errors: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


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
    """Запуск Chrome В ФОНЕ: HTTP-сервер поднимается сразу (панель видит его
    через 1-2 секунды), а браузер догоняет параллельно. Кому нужен
    браузер — дождётся его через wait_driver()."""
    try:
        set_driver(setup_browser())
        print("\u2705 Браузер готов.")
    except Exception as e:
        traceback.print_exc()
        set_driver_error(e)


def _disable_quickedit():
    """v86.5: консол�� Windows в режиме QuickEdit «замирает» от одного случайного
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
        import threading
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        threading.Thread(target=_boot_browser_background, daemon=True).start()
        # ВАЖНО: только 127.0.0.1! На 0.0.0.0 любой в локальной сети
        # мог бы писать файлы в ваш проект простым POST-запросом.
        print("Dashbord servera: http://127.0.0.1:5000/dashboard")
        app.run(port=5000, host='127.0.0.1', threaded=True)
    except Exception as e:
        traceback.print_exc()
        input()
