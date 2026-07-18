import os
import time
import traceback
from flask import Flask, request, jsonify

from browser_manager import setup_browser
from ai_parser import send_message_and_get_response
from project_tools import (
    build_project_tree,
    read_project_file,
    create_project_file,
    patch_project_file,
    move_project_file,
    copy_project_file,
    search_project_text,
    describe_scene,
    _resolve_safe_path,
)
import history_manager as history
import log_reader
import chat_store
import json as _json
from agent_prompts import (
    PRIMING_TEMPLATE,
    CODE_EXTS,
    PRIME_TREE_MAX_ENTRIES,
    MAX_BATCH_FILES,
    PER_FILE_CHAR_LIMIT,
    TOTAL_CHAR_BUDGET,
    MAX_ACTION_FIX_RETRIES,
)
import server_state
from server_state import (
    STATE, get_driver, set_driver,
    _prime_flag_path, _load_primed, _save_primed,
    _apply_session_context, _ensure_current_chat, _remember,
    _sync_chat_after_reply, _set_progress, _clear_progress,
)
import sites
from chat_routes import chats_bp

app = Flask(__name__)
app.register_blueprint(chats_bp)


def _reply(prompt):
    """Один запрос-ответ к модели, без какой-либо логики восстановления."""
    _set_progress({"phase": "отправляю запрос в браузер"})
    try:
        result = send_message_and_get_response(get_driver(), prompt, progress_cb=_set_progress)
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
    if act == "list_files": return "Агент хочет получить свежее дерево файлов проекта"
    if act == "list_scene": return f"Агент хочет посмотреть структуру сцены: {path}"
    if act == "parse_error": return "⚠ Агент прислал повреждённый JSON действия — действие пропущено."
    return f"Агент запросил неизвестное действие: {act}"


# ---------------------------------------------------------------------------
# Пакетное чтение файлов: модель запрашивает несколько файлов ОДНИМ
# действием, пользователь подтверждает каждый по очереди (без обращений
# к браузеру!), и только после последнего решения в браузер уходит ОДИН
# запрос со всеми одобренными файлами и пометками об отказах.
# ---------------------------------------------------------------------------

def _start_read_batch(action, project_root):
    paths = action.get("paths") or ([action.get("path")] if action.get("path") else [])
    seen, files = set(), []
    for p in paths[:MAX_BATCH_FILES]:
        if not p or p in seen:
            continue
        seen.add(p)
        status = "pending"
        try:
            if not os.path.isfile(_resolve_safe_path(project_root, p)):
                status = "missing"
        except Exception:
            status = "missing"
        files.append({"path": p, "status": status})
    return {"files": files, "reason": action.get("reason", "")}


def _next_batch_confirmation():
    batch = STATE.get("pending_batch")
    if not batch:
        return None
    files = batch["files"]
    for i, f in enumerate(files):
        if f["status"] == "pending":
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
        elif f["status"] == "rejected":
            parts.append("[Система]: Пользователь ОТКАЗАЛСЯ показывать файл %s. НЕ запрашивай его повторно; работай без него или объясни пользователю, зачем он нужен." % f["path"])
        elif f["status"] == "missing":
            parts.append("[Система]: Файл %s не найден в проекте. Сверься со структурой проекта." % f["path"])
    return "\n\n".join(parts) or "[Система]: Ни один файл не был предоставлен."


def _package_model_reply(text, action, project_root, depth=0):
    """Единая упаковка ответа модели в HTTP-ответ для Godot:
    parse_error / запрос чтения / write-действие / просто текст."""
    if action and action.get("action") == "parse_error":
        STATE["pending_action"] = None
        return jsonify({
            "answer": text + "\n\n[Система]: ⚠ Не удалось получить корректный JSON действия даже после повтора.",
            "pending_action": None,
        })
    if action and action.get("action") in ("read_file", "read_files"):
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
            synthetic = {"action": "create_file", "path": d}
            entry_id = history.record_change(project_root, synthetic)
            try:
                copy_project_file(project_root, s, d)
            except Exception as e:
                history.abort_change(project_root, entry_id)
                results.append("\u2717 %s -> %s: %s" % (s, d, e))
                continue
            history.commit_change(project_root, entry_id)
            results.append("\u2713 %s -> %s" % (s, d))
            print("--> copy_file %s -> %s" % (s, d))
        if not pairs:
            followup = ("[Система]: copy_file пришёл без пар src/dest. Пришли заново: "
                        '{"action":"copy_file","copies":[{"src":"res://...","dest":"res://..."}]}.')
        else:
            followup = ("[Система]: Результат копирования (файлы скопированы БЕЗ изменений; "
                        "адаптацию под проект делай через patch_file, он потребует подтверждения):\n"
                        + "\n".join(results))
        if depth >= 3:
            return jsonify({"answer": (text + "\n\n" + followup).strip(), "pending_action": None})
        text2, act2 = _reply_with_self_heal(followup, project_root)
        return _package_model_reply(text2, act2, project_root, depth + 1)
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
    })


# ---------------------------------------------------------------------------
# Self-heal: битый JSON или несовпадающий patch чиним без участия пользователя.
# ---------------------------------------------------------------------------

def _reply_with_self_heal(prompt, project_root):
    text, action = _reply(prompt)
    retries = 0
    while retries < MAX_ACTION_FIX_RETRIES:
        if action and action.get("action") == "parse_error":
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
        if action and action.get("action") == "patch_file":
            ok, real_content, err = _validate_patch_against_disk(action, project_root)
            if ok:
                break
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
            text, action = _reply(fix_prompt)
            continue
        # Любое другое действие или его отсутствие — проверять нечего.
        break
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
    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
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


# ---------------------------------------------------------------------------
# HTTP-эндпоинты
# ---------------------------------------------------------------------------

@app.route('/init', methods=['POST'])
def init_session():
    data = request.json or {}
    STATE["project_root"] = data.get('project_root')
    _apply_session_context(data)
    STATE["pending_action"] = None
    STATE["pending_batch"] = None
    STATE["action_note"] = ""
    STATE["pending_log_report"] = None
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
    current_root = STATE.get("project_root")
    _ensure_current_chat(prompt)
    # Страховка: если история ТЕКУЩЕГО чата пуста — это первое сообщение,
    # и мега-промпт нужен ВСЕГДА: глобальный флаг мог остаться от старого чата
    # или подгрузиться с диска при /init уже ПОСЛЕ создания нового чата.
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
        note = STATE.get("action_note", "")
        if note:
            prompt = f"{note}\n\n{prompt}"
            STATE["action_note"] = ""

        if not STATE.get("is_primed", False):
            print("\n---> Авто-инициализация сессии и отправка мега-промпта...")
            tree = build_project_tree(current_root, only_exts=CODE_EXTS, max_entries=PRIME_TREE_MAX_ENTRIES)
            system_context = PRIMING_TEMPLATE.replace("{tree}", tree)
            final_prompt = f"{system_context}\n\n[ЗАДАНИЕ ОТ ПОЛЬЗОВАТЕЛЯ]:\n{prompt}"
            text, action = _reply_with_self_heal(final_prompt, current_root)
            STATE["is_primed"] = True
            _save_primed(current_root, True)
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
            STATE["action_note"] = f"[Система: Пользователь ОТКЛОНИЛ ваше действие {act_type} для {path}. Изменение НЕ было применено! Скорректируй подход.]"
            STATE["pending_action"] = None
            return jsonify({"answer": "[Система]: Действие отклонено пользователем.", "pending_action": None})

        if act_type == "create_file":
            print(f"--> Создание файла {path}. Выполняем локально...")
            entry_id = history.record_change(project_root, action)
            try:
                overwrote = create_project_file(project_root, path, action.get("content", ""))
            except Exception:
                history.abort_change(project_root, entry_id)
                raise
            history.commit_change(project_root, entry_id)
            STATE["pending_action"] = None
            _create_msg = (f"[Система]: Файл полностью перезаписан: {path}" if overwrote
                           else f"[Система]: Файл успешно создан: {path}")
            # changed_path/changed_block — панель откроет файл в редакторе и
            # подсветит строки, которые написал агент.
            return jsonify({"answer": _create_msg, "pending_action": None,
                            "changed_path": path, "changed_block": action.get("content", "")})

        elif act_type == "patch_file":
            print(f"--> Точечный патч {path}. Выполняем локально...")
            entry_id = history.record_change(project_root, action)
            try:
                patch_project_file(project_root, path, action.get("search", ""), action.get("replace", ""))
            except Exception:
                history.abort_change(project_root, entry_id)
                raise
            history.commit_change(project_root, entry_id)
            STATE["pending_action"] = None
            return jsonify({"answer": f"[Система]: Изменения успешно внесены в файл: {path}", "pending_action": None,
                            "changed_path": path, "changed_block": action.get("replace", "")})

        elif act_type == "move_file":
            print(f"--> Перемещение файла в {action.get('dest')}. Выполняем локально...")
            entry_id = history.record_change(project_root, action)
            try:
                move_project_file(project_root, path, action.get("dest", ""))
            except Exception:
                history.abort_change(project_root, entry_id)
                raise
            history.commit_change(project_root, entry_id)
            STATE["pending_action"] = None
            return jsonify({"answer": f"[Система]: Файл успешно перемещен в: {action.get('dest')}", "pending_action": None})

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

        elif act_type == "list_files":
            print("--> Отправка свежего дерева файлов проекта...")
            STATE["pending_action"] = None
            tree = build_project_tree(project_root)
            fence = "`" * 3
            followup = "[Система]: АКТУАЛЬНОЕ дерево файлов проекта:\n%s\n%s\n%s" % (fence, tree, fence)
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
        note += " Учтите это!]"
        STATE["action_note"] = note
        resp = {"success": True, "message": msg, "paths": paths}
        if diff:
            # Панель подсветит в редакторе восстановленный после отката блок.
            resp["changed_path"] = diff["path"]
            resp["changed_block"] = diff["now"]
        return jsonify(resp)
    return jsonify({"error": msg, "needs_force": needs_force}), 409


# ---------------------------------------------------------------------------
# Ошибки последнего запуска игры: панель сперва получает сводку (в браузер
# НИЧЕГО не уходит), пользователь подтверждает — и только тогда модели
# отправляется ОДИН отчёт. Повторная отправка того же лога блокируется
# по отпечатку (mtime + размер), который переживает перезапуск сервера.
# ---------------------------------------------------------------------------

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
    STATE["pending_log_report"] = None
    project_root = STATE.get("project_root")
    try:
        # Фиксируем отпечаток ДО отправки: этот же лог больше не отправить.
        log_reader.save_sent_fingerprint(history.get_storage_dir(project_root), report["fingerprint"])
        message = log_reader.format_report(report)
        note = STATE.get("action_note", "")
        if note:
            message = f"{note}\n\n{message}"
            STATE["action_note"] = ""
        if not STATE.get("is_primed", False):
            print("\n---> Авто-инициализация сессии и отправка мега-промпта...")
            tree = build_project_tree(project_root)
            system_context = PRIMING_TEMPLATE.replace("{tree}", tree)
            message = f"{system_context}\n\n{message}"
            STATE["is_primed"] = True
        print(f"--> Отправка отчёта об ошибках запуска ({len(message)} симв.)")
        text, action = _reply_with_self_heal(message, project_root)
        return _package_model_reply(text, action, project_root)
    except Exception as e:
        print(f"❌ ОШИБКА send_log_errors: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/chat/progress', methods=['GET'])
def chat_progress():
    # Живая трансляция для панели: что сейчас происходит в браузере.
    # ВАЖНО: эндпоинт НЕ трогает Selenium (браузером занят поток /chat),
    # он только читает последний снимок состояния — поэтому безопасен
    # при одновременном длинном запросе.
    return jsonify(STATE.get("progress") or {"active": False})


if __name__ == '__main__':
    try:
        driver = setup_browser()
        set_driver(driver)
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        # ВАЖНО: только 127.0.0.1! На 0.0.0.0 любой в локальной сети
        # мог бы писать файлы в ваш проект простым POST-запросом.
        app.run(port=5000, host='127.0.0.1', threaded=True)
    except Exception as e:
        traceback.print_exc()
        input()
