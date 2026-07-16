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
    _resolve_safe_path
)

app = Flask(__name__)
driver = None

# Глобальное состояние сессии
STATE = {
    "project_root": None,
    "pending_action": None,         # dict с текущим ожидающим подтверждения действием
    "last_applied_action": None,    # dict с последним успешно примененным действием (для отката)
    "is_primed": False,             # флаг того, отправлен ли уже системный промпт в Chrome
}

PRIMING_TEMPLATE = """Ты — специализированный ИИ-разработчик, интегрированный непосредственно в игровой движок Godot 4 через плагин редактора. Твоя задача — помогать пользователю писать GDScript код, настраивать сцены и автоматизировать рутину разработки.

Стиль общения: отвечай кратко, технически точно и строго по существу. Без лишней вежливости и вступительных приветствий.

Пользователь работает над проектом в Godot. Структура его папок и файлов прислана ниже. Запомни её.

Доступные действия:
1. read_file — прочитать содержимое конкретного файла.
2. create_file — создать новый файл в проекте с нуля (включая создание любых подпапок на пути).
3. patch_file — заменить конкретный старый уникальный блок кода на новый (точечный патч функции).

Чтобы выполнить действие, ты ОБЯЗАН ЗАКОНЧИТЬ свой ответ ровно ОДНИМ блоком кода с языком agent_action (сырой JSON):

```agent_action
{"action": "read_file", "path": "res://путь/до/файла.gd", "reason": "зачем нужен файл"}
```

или

```agent_action
{"action": "create_file", "path": "res://hello_world/hello.gd", "content": "extends Node\\n\\nfunc _ready():\\n\\tprint(\\"Привет\\")\\n"}
```

или

```agent_action
{
  "action": "patch_file",
  "path": "res://путь/до/файла.gd",
  "search": "ТОЧНЫЙ_СТАРЫЙ_УНИКАЛЬНЫЙ_БЛОК_КОДА_КОТОРЫЙ_НУЖНО_ЗАМЕНИТЬ",
  "replace": "НОВЫЙ_БЛОК_КОДА",
  "summary": "описание изменения"
}
```

Правила:
- Мы разрабатываем строго в движке Godot 4! Все скрипты пиши исключительно на GDScript. Никакого Python или Bash в действиях, если тебя об этом прямо не попросят.
- Для изменения существующего кода всегда используй patch_file (передавай всю функцию целиком в search).
- Не более ОДНОГО блока agent_action за один ответ.

Структура проекта Godot:
```
{tree}
```
"""


def _reply(prompt):
    """Отправляет prompt в чат и возвращает (текст_для_показа, действие_или_None)."""
    result = send_message_and_get_response(driver, prompt)
    if isinstance(result, dict):
        return result.get("text") or "", result.get("action")
    return result or "", None


def _describe_action(action):
    if not action:
        return None
    act = action.get("action")
    path = action.get("path", "")
    if act == "read_file":
        return f"Агент хочет прочитать файл: {path}"
    if act == "create_file":
        return f"Агент хочет создать файл: {path}"
    if act == "patch_file":
        return f"Агент хочет изменить код в: {path}"
    return f"Агент запросил неизвестное действие: {act}"


@app.route('/init', methods=['POST'])
def init_session():
    data = request.json or {}
    project_root = data.get('project_root')
    if not project_root:
        return jsonify({"error": "project_root не передан"}), 400

    STATE["project_root"] = project_root
    STATE["pending_action"] = None
    STATE["last_applied_action"] = None
    STATE["is_primed"] = False  # Сбрасываем флаг, чтобы принудительно пересобрать дерево при следующем сообщении

    print(f"\n---> Запрошена переинициализация структуры: {project_root}")
    return jsonify({
        "success": True,
        "message": "Структура проекта будет обновлена и переслана при следующей отправке сообщения."
    })


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    prompt = data.get('prompt', '')
    project_root = data.get('project_root')

    if STATE["pending_action"] is not None:
        return jsonify({
            "error": "Есть неподтверждённое действие агента — сначала подтвердите или отклоните его."
        }), 409

    # Если Godot передал корень проекта, фиксируем его
    if project_root:
        STATE["project_root"] = project_root

    current_root = STATE.get("project_root")
    if not current_root:
        return jsonify({"error": "Путь к проекту не указан. Перезапустите плагин или нажмите синхронизацию."}), 400

    try:
        # Автоматический ленивый прайминг сессии
        if not STATE.get("is_primed", False):
            print("\n---> Авто-инициализация сессии: собираем дерево файлов и склеиваем с промптом...")
            tree = build_project_tree(current_root)
            system_context = PRIMING_TEMPLATE.replace("{tree}", tree)
            
            # Соединяем системную инструкцию и реальный первый вопрос в один пак
            final_prompt = f"{system_context}\n\n[ЗАДАНИЕ ОТ ПОЛЬЗОВАТЕЛЯ РЕДАКТОРА GODOT]:\n{prompt}"
            
            text, action = _reply(final_prompt)
            STATE["is_primed"] = True
        else:
            print(f"\n---> Отправка сообщения в текущую сессию ({len(prompt)} симв.)")
            text, action = _reply(prompt)

        STATE["pending_action"] = action
        print("<--- Ответ успешно отправлен в Godot!")
        return jsonify({
            "answer": text,
            "pending_action": action,
            "pending_action_description": _describe_action(action),
        })
    except Exception as e:
        print(f"❌ ОШИБКА в роуте /chat: {e}")
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

    print(f"\n---> Подтверждение действия '{act_type}' ({path}): {'ДА' if approved else 'НЕТ'}")

    try:
        if not approved:
            followup = (
                f"Пользователь ОТКЛОНИЛ действие ({act_type}, {path}). "
                f"Файл остаётся без изменений. Учти это в дальнейшей работе."
            )
            STATE["last_applied_action"] = None
        elif act_type == "read_file":
            content, truncated = read_project_file(project_root, path)
            note = " (файл обрезан)" if truncated else ""
            followup = f"Содержимое файла {path}{note}:\n```\n{content}\n```"
            STATE["last_applied_action"] = None
        elif act_type == "create_file":
            create_project_file(project_root, path, action.get("content", ""))
            followup = f"Новый файл {path} успешно создан на диске."
            STATE["last_applied_action"] = action
        elif act_type == "patch_file":
            patch_project_file(project_root, path, action.get("search", ""), action.get("replace", ""))
            followup = f"Патч успешно применен к файлу {path}."
            STATE["last_applied_action"] = action
        else:
            followup = f"Неизвестное действие '{act_type}' — пропускаю, уточни задачу."
            STATE["last_applied_action"] = None

        STATE["pending_action"] = None
        text, new_action = _reply(followup)
        STATE["pending_action"] = new_action

        return jsonify({
            "answer": text,
            "pending_action": new_action,
            "pending_action_description": _describe_action(new_action),
        })
    except Exception as e:
        STATE["pending_action"] = None
        print(f"❌ ОШИБКА confirm_action: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/chat/rollback', methods=['POST'])
def rollback():
    action = STATE.get("last_applied_action")
    if not action:
        return jsonify({"error": "Нет примененных действий для отката."}), 400

    project_root = STATE["project_root"]
    path = action.get("path", "")
    act_type = action.get("action")

    try:
        abs_path = _resolve_safe_path(project_root, path)

        if act_type == "create_file":
            if os.path.exists(abs_path):
                os.remove(abs_path)
                STATE["last_applied_action"] = None
                print(f"--> Успешный откат: удален созданный файл {path}")
                return jsonify({"success": True, "message": f"Файл {path} успешно удален."})
            return jsonify({"error": "Файл не найден на диске для удаления."}), 404

        elif act_type == "patch_file":
            backup_path = abs_path + ".bak"
            if not os.path.exists(backup_path):
                return jsonify({"error": f"Файл резервной копии (.bak) для {path} не найден."}), 404
            
            os.replace(backup_path, abs_path)
            STATE["last_applied_action"] = None
            print(f"--> Успешный откат: восстановлена резервная копия для {path}")
            return jsonify({"success": True, "message": f"Изменения в файле {path} отменены."})

        return jsonify({"error": f"Тип действия '{act_type}' не поддерживает откат."}), 400
    except Exception as e:
        print(f"❌ ОШИБКА rollback: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("=====================================================")
    print("🤖 ИИ-МОСТ ДЛЯ GODOT: СЕРВЕР ЗАПУСКАЕТСЯ")
    print("=====================================================")

    try:
        driver = setup_browser()
        print("\n✅ СЕРВЕР ГОТОВ К РАБОТЕ!\n")

        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        app.run(port=5000, host='0.0.0.0')

    except Exception as e:
        print("\n❌ КРИТИЧЕСКАЯ ОШИБКА:")
        traceback.print_exc()
        input("\nНажмите ENTER для выхода...")
