import traceback
from flask import Flask, request, jsonify

from browser_manager import setup_browser
from ai_parser import send_message_and_get_response
from project_tools import build_project_tree, read_project_file, write_project_file

app = Flask(__name__)
driver = None

# Общее состояние сессии. Простой глобальный словарь достаточен, т.к. у нас
# один пользователь и один браузер — конкурентных сессий не бывает.
STATE = {
    "project_root": None,
    "pending_action": None,  # dict с последним предложенным действием или None
}

PRIMING_TEMPLATE = """Ты — ИИ-агент, встроенный в редактор Godot через плагин. У тебя есть доступ к файлам проекта через специальный протокол команд.

Стиль общения: отвечай кратко и по существу, как агенты в инструментах для разработки (Claude Code, Cursor и т.п.) — минимум вступлений и заключений. Без фраз вроде "Отличный вопрос!", "Надеюсь, это поможет!", без пересказа того, что уже написал в этом же ответе. Экономь токены, но не в ущерб точности и полноте технической информации.

Структура проекта прислана ниже, в этом же сообщении. Запомни её на весь разговор — я не буду присылать её повторно, не проси прислать её снова.

Доступные действия:
1. read_file — прочитать содержимое конкретного файла.
2. write_file — предложить новое содержимое файла (правку).

Чтобы выполнить действие, ЗАКОНЧИ свой ответ ровно ОДНИМ блоком кода с языком agent_action (и не более одного такого блока за раз):

```agent_action
{"action": "read_file", "path": "res://путь/до/файла.gd", "reason": "почему тебе нужен этот файл"}
```

или

```agent_action
{"action": "write_file", "path": "res://путь/до/файла.gd", "content": "новое ПОЛНОЕ содержимое файла", "summary": "краткое описание изменения"}
```

Правила:
- Не более ОДНОГО блока agent_action за ответ. Нужно прочитать несколько файлов — запрашивай по одному, следующий уже после того как получишь содержимое предыдущего.
- КАЖДОЕ действие (и чтение, и запись) требует подтверждения от пользователя. Результат подтверждения придёт тебе в следующем сообщении.
- Если пользователь ОТКЛОНИЛ действие записи — считай файл БЕЗ ИЗМЕНЕНИЙ (старая версия/архитектура). Не предполагай, что правка применилась, и строй дальнейшие рекомендации с учётом того, что файл остался старым.
- Если действие не требуется — отвечай обычным текстом, без блока agent_action.

Структура проекта:
```
{tree}
```
"""


def _reply(prompt):
    """Отправляет prompt в чат и возвращает (текст_для_показа, действие_или_None)."""
    result = send_message_and_get_response(driver, prompt)
    if isinstance(result, dict):
        return result.get("text", ""), result.get("action")
    return result, None


def _describe_action(action):
    if not action:
        return None
    act = action.get("action")
    path = action.get("path", "")
    if act == "read_file":
        return f"Агент хочет прочитать файл: {path}"
    if act == "write_file":
        return f"Агент предлагает изменить файл: {path}"
    return f"Агент запросил неизвестное действие: {act}"


@app.route('/init', methods=['POST'])
def init_session():
    data = request.json or {}
    project_root = data.get('project_root')
    if not project_root:
        return jsonify({"error": "project_root не передан"}), 400

    STATE["project_root"] = project_root
    STATE["pending_action"] = None

    print(f"\n---> Инициализация сессии, проект: {project_root}")

    try:
        tree = build_project_tree(project_root)
        priming = PRIMING_TEMPLATE.format(tree=tree)

        text, action = _reply(priming)
        STATE["pending_action"] = action

        return jsonify({
            "answer": text,
            "pending_action": action,
            "pending_action_description": _describe_action(action),
        })
    except Exception as e:
        print(f"❌ ОШИБКА /init: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json or {}
    prompt = data.get('prompt', '')

    if STATE["pending_action"] is not None:
        return jsonify({
            "error": "Есть неподтверждённое действие агента — сначала подтвердите или отклоните его."
        }), 409

    print(f"\n---> Вопрос от Godot ({len(prompt)} симв.)")

    try:
        text, action = _reply(prompt)
        STATE["pending_action"] = action

        print("<--- Ответ успешно отправлен в Godot!")
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

    print(f"\n---> Подтверждение действия '{act_type}' ({path}): {'ДА' if approved else 'НЕТ'}")

    try:
        if not approved:
            followup = (
                f"Пользователь ОТКЛОНИЛ действие ({act_type}, {path}). "
                f"Файл остаётся без изменений (старая версия/архитектура). "
                f"Учти это в дальнейшей работе."
            )
        elif act_type == "read_file":
            content, truncated = read_project_file(project_root, path)
            note = " (файл обрезан, слишком большой для одного сообщения)" if truncated else ""
            followup = f"Содержимое файла {path}{note}:\n```\n{content}\n```"
        elif act_type == "write_file":
            write_project_file(project_root, path, action.get("content", ""))
            followup = f"Изменение применено к файлу {path}. Новое содержимое сохранено на диск."
        else:
            followup = f"Неизвестное действие '{act_type}' — пропускаю, уточни задачу."

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