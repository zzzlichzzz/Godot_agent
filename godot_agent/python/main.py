import os
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
    _resolve_safe_path,
)
import history_manager as history

app = Flask(__name__)
driver = None

MAX_ACTION_FIX_RETRIES = 3

# Лимиты пакетного чтения файлов
MAX_BATCH_FILES = 5
PER_FILE_CHAR_LIMIT = 30000
TOTAL_CHAR_BUDGET = 80000

# Глобальное состояние сессии
STATE = {
    "project_root": None,
    "pending_action": None,   # ожидающее подтверждения WRITE-действие
    "pending_batch": None,    # ожидающая подтверждений пачка файлов на чтение
    "is_primed": False,
    "action_note": "",
}

PRIMING_TEMPLATE = """Ты — специализированный ИИ-разработчик, интегрированный в движок Godot 4 через плагин.
Стиль общения: кратко, технически точно, без приветствий и лишней вежливости.

Доступные действия:
1. read_file — прочитать один или НЕСКОЛЬКО файлов (до 5 за раз). ВСЕГДА запрашивай сразу все файлы, которые понадобятся для задачи, одним блоком.
2. create_file — создать новый файл (и папки на пути к нему).
3. patch_file — заменить уникальный блок кода (патч функции).
4. move_file — переместить или переименовать существующий файл.

Форматы блоков agent_action (ЗАКОНЧИ ответ ровно одним таким блоком при необходимости действия):
```agent_action
{"action": "read_file", "paths": ["res://scripts/a.gd", "res://scripts/b.gd"], "reason": "причина"}
```
Каждый запрошенный файл показывается пользователю на подтверждение отдельно; если пользователь откажет по какому-то файлу, ты получишь об этом пометку — НЕ запрашивай его повторно.
или
```agent_action
{"action": "create_file", "path": "res://scripts/ui/menu.gd", "content": "код"}
```
или
```agent_action
{
  "action": "patch_file",
  "path": "res://scripts/player.gd",
  "search": "СТАРЫЙ_КОД",
  "replace": "НОВЫЙ_КОД",
  "summary": "описание"
}
```
или
```agent_action
{"action": "move_file", "path": "res://old_path.gd", "dest": "res://new_path.gd"}
```

КРИТИЧЕСКИЕ ПРАВИЛА:
1. Пиши строго на GDScript для Godot 4! Никакого Python или Bash в действиях.
2. СОБЛЮДАЙ СТРУКТУРУ ПРОЕКТА! Не создавай новые папки в корне проекта (res://), если не просили. Клади новые скрипты в существующую папку для скриптов (res://scripts/ или аналогичную).
3. ЗАПРЕЩЕНО использовать patch_file для файла, если ты не прочитал его АКТУАЛЬНОЕ содержимое в ЭТОМ ЖЕ диалоге через read_file. Если ты не читал файл только что (даже если помнишь его из более раннего сообщения) — сначала отправь read_file (сразу со ВСЕМИ нужными файлами в paths), дождись содержимого, и только следующим ответом отправляй patch_file. Файл мог измениться с последнего просмотра.

Структура проекта Godot:
```
{tree}
```
"""


def _reply(prompt):
    """Один запрос-ответ к модели, без какой-либо логики восстановления."""
    result = send_message_and_get_response(driver, prompt)
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
    if not text and action is None:
        # Пустой ответ из браузера: парсер мог не дождаться конца генерации
        # длинного ответа. Не молчим — пользователь должен это увидеть.
        text = ("[Система]: ⚠ Из браузера пришёл ПУСТОЙ ответ. Скорее всего, модель "
                "ещё генерировала текст, а парсер не дождался конца. Ответ, вероятно, "
                "виден во вкладке AI Studio. Можно написать модели: 'повтори последний ответ'.")
    STATE["pending_action"] = action
    return jsonify({
        "answer": text,
        "pending_action": action,
        "pending_action_description": _describe_action(action),
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


# ---------------------------------------------------------------------------
# HTTP-эндпоинты
# ---------------------------------------------------------------------------

@app.route('/init', methods=['POST'])
def init_session():
    data = request.json or {}
    STATE["project_root"] = data.get('project_root')
    STATE["pending_action"] = None
    STATE["pending_batch"] = None
    STATE["is_primed"] = False
    STATE["action_note"] = ""
    print(f"\n---> Проект синхронизирован: {STATE['project_root']}")
    return jsonify({"success": True, "message": "Локальная синхронизация успешна."})


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    prompt = data.get('prompt', '')
    project_root = data.get('project_root')

    if STATE["pending_action"] is not None:
        return jsonify({"error": "Есть неподтверждённое действие агента."}), 409
    if STATE["pending_batch"] is not None:
        return jsonify({"error": "Есть неподтверждённые запросы файлов агента."}), 409

    if project_root:
        STATE["project_root"] = project_root
    current_root = STATE.get("project_root")

    try:
        note = STATE.get("action_note", "")
        if note:
            prompt = f"{note}\n\n{prompt}"
            STATE["action_note"] = ""

        if not STATE.get("is_primed", False):
            print("\n---> Авто-инициализация сессии и отправка мега-промпта...")
            tree = build_project_tree(current_root)
            system_context = PRIMING_TEMPLATE.replace("{tree}", tree)
            final_prompt = f"{system_context}\n\n[ЗАДАНИЕ ОТ ПОЛЬЗОВАТЕЛЯ]:\n{prompt}"
            text, action = _reply_with_self_heal(final_prompt, current_root)
            STATE["is_primed"] = True
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
                create_project_file(project_root, path, action.get("content", ""))
            except Exception:
                history.abort_change(project_root, entry_id)
                raise
            history.commit_change(project_root, entry_id)
            STATE["pending_action"] = None
            return jsonify({"answer": f"[Система]: Файл успешно создан: {path}", "pending_action": None})

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
            return jsonify({"answer": f"[Система]: Изменения успешно внесены в файл: {path}", "pending_action": None})

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
        ok, msg, needs_force, paths = history.rollback_last(STATE["project_root"], force=force)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    if ok:
        STATE["action_note"] = f"[Система: Пользователь ОТМЕНИЛ (откатил) ваше последнее действие! {msg}. Учтите это!]"
        return jsonify({"success": True, "message": msg, "paths": paths})
    return jsonify({"error": msg, "needs_force": needs_force}), 409


if __name__ == '__main__':
    try:
        driver = setup_browser()
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        # ВАЖНО: только 127.0.0.1! На 0.0.0.0 любой в локальной сети
        # мог бы писать файлы в ваш проект простым POST-запросом.
        app.run(port=5000, host='127.0.0.1')
    except Exception as e:
        traceback.print_exc()
        input()
