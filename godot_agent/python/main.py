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
    _resolve_safe_path
)

app = Flask(__name__)
driver = None

MAX_ACTION_PARSE_RETRIES = 2
MAX_ACTION_FIX_RETRIES = 3

# Глобальное состояние сессии
STATE = {
    "project_root": None,
    "pending_action": None,
    "last_applied_action": None,
    "is_primed": False,
    "action_note": "",
}

PRIMING_TEMPLATE = """Ты — специализированный ИИ-разработчик, интегрированный в движок Godot 4 через плагин.
Стиль общения: кратко, технически точно, без приветствий и лишней вежливости.

Доступные действия:
1. read_file — прочитать файл.
2. create_file — создать новый файл (и папки на пути к нему).
3. patch_file — заменить уникальный блок кода (патч функции).
4. move_file — переместить или переименовать существующий файл.


Форматы блоков agent_action (ЗАКОНЧИ ответ ровно одним таким блоком при необходимости действия):

```agent_action
{"action": "read_file", "path": "res://scripts/mgr.gd", "reason": "причина"}
```

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
3. ЗАПРЕЩЕНО использовать patch_file для файла, если ты не прочитал его АКТУАЛЬНОЕ содержимое в ЭТОМ ЖЕ диалоге через read_file. Если ты не читал файл только что (даже если помнишь его из более раннего сообщения) — сначала отправь read_file, дождись содержимого, и только следующим ответом отправляй patch_file. Файл мог измениться с последнего просмотра.

Структура проекта Godot:
```
{tree}
```
"""


def _reply(prompt):
    """Один запрос-ответ к модели, без какой-либо логики восстановления."""
    result = send_message_and_get_response(driver, prompt)
    if isinstance(result, dict):
        return result.get("text") or "", result.get("action")
    return result or "", None


def _reply_with_action_retry(prompt):
    """Если agent_action пришёл битым JSON — просим модель прислать его же
    действие заново, вместо того чтобы сразу сдаваться."""
    text, action = _reply(prompt)
    retries = 0
    while action is not None and action.get("action") == "parse_error" and retries < MAX_ACTION_PARSE_RETRIES:
        retries += 1
        print(f"--> agent_action битый JSON (попытка исправления {retries})...")
        fix_prompt = (
            "[Система]: Твой предыдущий блок ```agent_action``` содержал невалидный JSON "
            "и не был обработан. Пришли ТО ЖЕ действие ещё раз одним корректным JSON-блоком "
            "agent_action, строго экранируя переносы строк (\\n), кавычки (\\\") и обратные "
            "слэши (\\\\) внутри строковых значений. Не добавляй никакого текста внутри JSON."
        )
        text, action = _reply(fix_prompt)
    return text, action


def _describe_action(action):
    if not action:
        return None
    act = action.get("action")
    path = action.get("path", "")
    if act == "read_file": return f"Агент хочет прочитать файл: {path}"
    if act == "create_file": return f"Агент хочет создать файл: {path}"
    if act == "patch_file": return f"Агент хочет изменить код в: {path}"
    if act == "move_file": return f"Агент хочет переместить {path} в {action.get('dest', '')}"
    if act == "parse_error": return "⚠ Агент прислал повреждённый JSON действия — действие пропущено."
    return f"Агент запросил неизвестное действие: {act}"


@app.route('/init', methods=['POST'])
def init_session():
    data = request.json or {}
    STATE["project_root"] = data.get('project_root')
    STATE["pending_action"] = None
    STATE["last_applied_action"] = None
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

    if project_root: STATE["project_root"] = project_root
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

        if action and action.get("action") == "parse_error":
            STATE["pending_action"] = None
            return jsonify({
                "answer": text + "\n\n[Система]: ⚠ Не удалось получить корректный JSON действия даже после повтора.",
                "pending_action": None,
            })

        STATE["pending_action"] = action
        return jsonify({
            "answer": text,
            "pending_action": action,
            "pending_action_description": _describe_action(action),
        })
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/chat/confirm_action', methods=['POST'])
def confirm_action():
    data = request.json or {}
    approved = data.get('approved', False)
    action = STATE.get("pending_action")

    if action is None:
        return jsonify({"error": "Нет ожидающего подтверждения действия."}), 400

    project_root = STATE["project_root"]
    act_type = action.get("action")
    path = action.get("path", "")

    try:
        if not approved:
            print(f"--> Действие '{act_type}' ОТКЛОНЕНО пользователем.")
            # Пишем нотификацию только при отказе, чтобы ИИ знал, что код не сохранился!
            STATE["action_note"] = f"[Система: Пользователь ОТКЛОНИЛ ваше действие {act_type} для {path}. Изменение НЕ было применено! Скорректируй подход.]"
            STATE["pending_action"] = None
            STATE["last_applied_action"] = None
            return jsonify({"answer": "[Система]: Действие отклонено пользователем.", "pending_action": None})

        # --- ЕСЛИ ДЕЙСТВИЕ ОДОБРЕНО ---
        if act_type == "read_file":
            print(f"--> Чтение файла {path}. Отправляем данные в браузер...")
            content, truncated = read_project_file(project_root, path)
            note = " (файл обрезан)" if truncated else ""
            followup = f"Содержимое файла {path}{note}:\n```\n{content}\n```"
            STATE["pending_action"] = None
            text, new_action = _reply_with_self_heal(followup, project_root)

            if new_action and new_action.get("action") == "parse_error":
                return jsonify({
                    "answer": text + "\n\n[Система]: ⚠ Не удалось получить корректный JSON действия даже после повтора.",
                    "pending_action": None,
                })

            STATE["pending_action"] = new_action
            return jsonify({
                "answer": text,
                "pending_action": new_action,
                "pending_action_description": _describe_action(new_action),
            })

        elif act_type == "create_file":
            print(f"--> Создание файла {path}. Выполняем локально...")
            create_project_file(project_root, path, action.get("content", ""))
            STATE["last_applied_action"] = action
            STATE["pending_action"] = None
            # Возвращаем мгновенный ответ в Godot БЕЗ отправки запроса в Chrome
            return jsonify({"answer": f"[Система]: Файл успешно создан: {path}", "pending_action": None})

        elif act_type == "patch_file":
            print(f"--> Точечный патч {path}. Выполняем локально...")
            patch_project_file(project_root, path, action.get("search", ""), action.get("replace", ""))
            STATE["last_applied_action"] = action
            STATE["pending_action"] = None
            return jsonify({"answer": f"[Система]: Изменения успешно внесены в файл: {path}", "pending_action": None})

        elif act_type == "move_file":
            print(f"--> Перемещение файла в {action.get('dest')}. Выполняем локально...")
            move_project_file(project_root, path, action.get("dest", ""))
            STATE["last_applied_action"] = action
            STATE["pending_action"] = None
            return jsonify({"answer": f"[Система]: Файл успешно перемещен в: {action.get('dest')}", "pending_action": None})

        else:
            STATE["pending_action"] = None
            return jsonify({"error": f"Неизвестный тип действия: {act_type}"}, 400)

    except Exception as e:
        STATE["pending_action"] = None
        print(f"❌ ОШИБКА confirm_action: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def _reply_with_self_heal(prompt, project_root):
    """
    Отправляет prompt модели. Если результат — битый JSON ИЛИ patch_file
    с search, не совпадающим с реальным файлом на диске — автоматически,
    без участия пользователя, просит модель прислать действие заново,
    подсовывая ей актуальное содержимое файла. Так пользователь не видит
    внутренних "уточняющих" сообщений и не тратит подтверждения впустую.
    """
    text, action = _reply(prompt)
    retries = 0

    while retries < MAX_ACTION_FIX_RETRIES:
        if action and action.get("action") == "parse_error":
            retries += 1
            print(f"--> [self-heal] Битый JSON action, попытка {retries}/{MAX_ACTION_FIX_RETRIES}")
            fix_prompt = (
                "[Система]: Твой предыдущий блок ```agent_action``` содержал невалидный JSON "
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

            if real_content is None:
                fix_prompt = (
                    f"[Система]: Не удалось применить patch_file к {path}: {err}. "
                    f"Проверь путь к файлу и предложи корректное действие заново."
                )
            else:
                fix_prompt = (
                    f"[Система]: Блок 'search' в твоём patch_file не совпадает с реальным "
                    f"содержимым файла {path} прямо сейчас (причина: {err}). "
                    f"Вот АКТУАЛЬНОЕ содержимое файла на диске:\n```\n{real_content}\n```\n"
                    f"Пришли новый agent_action patch_file, где 'search' дословно совпадает "
                    f"с текстом файла выше."
                )
            text, action = _reply(fix_prompt)
            continue

        # Любое другое действие (read_file, create_file, move_file) или его
        # отсутствие — донолнительно проверять нечего, выходим из цикла.
        break

    return text, action


def _validate_patch_against_disk(action, project_root):
    """
    Проверяет, что action['search'] реально присутствует (и уникален)
    в файле на диске ПРЯМО СЕЙЧАС — до того как показать pending_action
    пользователю. Возвращает (ok, real_file_content_or_None, error_or_None).
    """
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


@app.route('/chat/rollback', methods=['POST'])
def rollback():
    import shutil
    action = STATE.get("last_applied_action")
    if not action: return jsonify({"error": "Нет действий для отката."}), 400
    project_root = STATE["project_root"]
    path = action.get("path", "")
    act_type = action.get("action")
    try:
        abs_path = _resolve_safe_path(project_root, path)
        if act_type == "create_file":
            if os.path.exists(abs_path): os.remove(abs_path)
        elif act_type == "patch_file":
            backup_path = abs_path + ".bak"
            if os.path.exists(backup_path): os.replace(backup_path, abs_path)
        elif act_type == "move_file":
            dest_path = action.get("dest", "")
            abs_dest = _resolve_safe_path(project_root, dest_path)
            if os.path.exists(abs_dest): 
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                shutil.move(abs_dest, abs_path)
        STATE["last_applied_action"] = None
        STATE["action_note"] = "[Система: Пользователь только что ОТМЕНИЛ (откатил) ваше последнее действие! Учтите это!]"
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    try:
        driver = setup_browser()
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        app.run(port=5000, host='0.0.0.0')
    except Exception as e:
        traceback.print_exc()
        input()
