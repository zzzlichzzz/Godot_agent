@tool
extends Control
@onready var chat_log: RichTextLabel = $VBoxContainer/ChatLog
@onready var input_field: TextEdit = $VBoxContainer/HBoxContainer/InputField
@onready var send_button: Button = $VBoxContainer/HBoxContainer/SendButton
@onready var http_request: HTTPRequest = $HTTPRequest
@onready var attach_checkbox: CheckBox = $VBoxContainer/AttachCodeCheckbox
@onready var pending_action_box: HBoxContainer = $VBoxContainer/PendingActionBox
@onready var action_label: Label = $VBoxContainer/PendingActionBox/ActionLabel
@onready var confirm_button: Button = $VBoxContainer/PendingActionBox/ConfirmButton
@onready var reject_button: Button = $VBoxContainer/PendingActionBox/RejectButton
@onready var reinit_button: Button = $VBoxContainer/ReinitButton

# Ссылки на наш локальный Python-сервер
const CHAT_URL = "http://127.0.0.1:5000/chat"
const INIT_URL = "http://127.0.0.1:5000/init"
const CONFIRM_URL = "http://127.0.0.1:5000/chat/confirm_action"

# HTTPRequest один на всю панель, а эндпоинтов несколько — помечаем, какого
# рода запрос сейчас "в полёте", чтобы правильно обработать ответ в общем
# колбэке _on_request_completed.
var _pending_request_kind: String = "chat"  # "init" | "chat" | "confirm"

func _ready() -> void:
	print("[AgentPanel] _ready() вызван")

	chat_log.selection_enabled = true
	chat_log.context_menu_enabled = true
	# Явно включаем перенос по словам — без этого длинные абзацы/строки кода
	# могут растягивать контрол по горизонтали вместо переноса на новую строку.
	chat_log.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	chat_log.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	# Автопрокрутка вниз при добавлении нового текста (пока пользователь сам
	# не проскроллит вверх — тогда Godot временно перестаёт "следовать").
	chat_log.scroll_following = true
	chat_log.text = "[color=green]Система готова. Работаем через локальный Python эмулятор (G4F)![/color]\n"

	# Безопасно на случай, если сцена ещё не перезагружена (например, плагин
	# не был выключен/включён заново после добавления PendingActionBox) —
	# без этой проверки null-доступ ниже прервал бы весь _ready(), и
	# инициализация сессии (отправка структуры проекта) вообще не запустилась бы.
	if pending_action_box:
		pending_action_box.visible = false
	else:
		print("PendingActionBox не найден — пересохраните/перезагрузите сцену (выключите и включите плагин).")

	if not send_button.pressed.is_connected(_on_send_pressed):
		send_button.pressed.connect(_on_send_pressed)
	if not http_request.request_completed.is_connected(_on_request_completed):
		http_request.request_completed.connect(_on_request_completed)
	if confirm_button and not confirm_button.pressed.is_connected(_on_confirm_pressed):
		confirm_button.pressed.connect(_on_confirm_pressed)
	if reject_button and not reject_button.pressed.is_connected(_on_reject_pressed):
		reject_button.pressed.connect(_on_reject_pressed)
	if reinit_button and not reinit_button.pressed.is_connected(_send_init_request):
		reinit_button.pressed.connect(_send_init_request)

	# Нам больше не нужны настройки API-ключей, поэтому мы просто скрываем верхний блок
	if has_node("VBoxContainer/SettingsBox"):
		$VBoxContainer/SettingsBox.hide()

	_send_init_request()

# BBCode использует [ и ] как спецсимволы для тегов. Текст, который печатает
# ПОЛЬЗОВАТЕЛЬ (например, вставленный кусок GDScript с массивами вроде
# [1, 2, 3] или Array[int]), может случайно сломать разметку в chat_log,
# т.к. RichTextLabel работает с bbcode_enabled = true. Экранируем перед
# вставкой — так же, как это уже сделано в парсере ответов ИИ на стороне Python.
func _escape_bbcode(text: String) -> String:
	return text.replace("[", "[lb]").replace("]", "[rb]")

# Отправляет Python абсолютный путь к проекту — на его основе Python сам
# построит дерево файлов и пришлёт модели ОДИН РАЗ при старте сессии.
func _send_init_request() -> void:
	print("[AgentPanel] _send_init_request() вызван, отправляю POST на ", INIT_URL)
	chat_log.text += "[color=gray]Инициализация сессии, отправляю структуру проекта...[/color]\n"

	var project_root = ProjectSettings.globalize_path("res://")
	print("[AgentPanel] project_root = ", project_root)
	var headers = ["Content-Type: application/json"]
	var body = {"project_root": project_root}

	http_request.set_http_proxy("", 0)
	_pending_request_kind = "init"
	var err = http_request.request(INIT_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	print("[AgentPanel] http_request.request() вернул код: ", err, " (OK = ", OK, ")")

	if err != OK:
		print("Ошибка инициализации: убедитесь, что Python-сервер запущен")

func _on_send_pressed() -> void:
	# Пока есть неподтверждённое действие агента — новые сообщения не отправляем,
	# сначала нужно подтвердить/отклонить текущее.
	if pending_action_box and pending_action_box.visible:
		return

	var user_text = input_field.text.strip_edges()
	if user_text.is_empty(): return

	input_field.text = ""
	chat_log.text += "\n[color=lightblue]Вы:[/color] " + _escape_bbcode(user_text) + "\n"

	var final_prompt = user_text

	# Прикрепляем код, если стоит галочка
	if attach_checkbox.button_pressed:
		var current_code = ""
		var script_editor = EditorInterface.get_script_editor()
		var current_editor = script_editor.get_current_editor()
		if current_editor and current_editor.get_base_editor():
			current_code = current_editor.get_base_editor().text

		if current_code != "":
			final_prompt = "Ответь на вопрос по моему GDScript коду:\n\n```gdscript\n" + current_code + "\n```\nВопрос: " + user_text
			chat_log.text += "[color=gray][Код прикреплен: " + str(current_code.length()) + " симв.][/color]\n"

	chat_log.text += "[color=gray]Python-сервер эмулирует браузер... ждем.[/color]\n"

	var headers = ["Content-Type: application/json"]
	var body = {"prompt": final_prompt}

	http_request.set_http_proxy("", 0)
	_pending_request_kind = "chat"
	var err = http_request.request(CHAT_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))

	if err != OK:
		print("Ошибка: Убедитесь, что Python скрипт ai_server.py запущен")

func _on_confirm_pressed() -> void:
	_send_confirm_request(true)

func _on_reject_pressed() -> void:
	_send_confirm_request(false)

func _send_confirm_request(approved: bool) -> void:
	if pending_action_box:
		pending_action_box.visible = false
	var label = "Подтверждено" if approved else "Отклонено"
	chat_log.text += "[color=gray]" + label + ". Жду реакции агента...[/color]\n"

	var headers = ["Content-Type: application/json"]
	var body = {"approved": approved}

	http_request.set_http_proxy("", 0)
	_pending_request_kind = "confirm"
	var err = http_request.request(CONFIRM_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))

	if err != OK:
		print("Ошибка отправки подтверждения")

# Общий колбэг для /init, /chat и /chat/confirm_action — все три возвращают
# один и тот же формат {"answer": ..., "pending_action": ...}.
func _on_request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	var kind = _pending_request_kind
	print("[AgentPanel] Ответ получен: kind=", kind, " response_code=", response_code, " result=", result)

	if response_code == 200:
		var json = JSON.parse_string(body.get_string_from_utf8())
		if json and json.has("answer"):
			# ai_text уже приходит из Python в виде готового BBCode
			# (экранирование скобок там уже сделано) — повторно НЕ экранируем,
			# иначе собственные теги [b], [code] и т.п. превратятся в текст.
			var ai_text = json["answer"]
			if kind == "init":
				chat_log.text += "\n[color=yellow]ИИ (инициализация):[/color]\n" + ai_text + "\n\n-----------------\n"
			else:
				chat_log.text += "\n[color=yellow]ИИ:[/color]\n" + ai_text + "\n\n-----------------\n"

			var pending = json.get("pending_action")
			if pending != null and action_label and pending_action_box:
				var description = json.get("pending_action_description", "Агент запросил действие.")
				action_label.text = description
				pending_action_box.visible = true
			elif pending_action_box:
				pending_action_box.visible = false

			# Страховка: явно прокручиваем к последней строке даже если
			# scroll_following почему-то не сработал (например, из-за большого
			# BBCode-блока, который пересчитывается не сразу).
			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
		else:
			print("Ошибка парсинга ответа от Python сервера")
	elif response_code == 409:
		print("Есть неподтверждённое действие — подтвердите/отклоните прежде чем продолжить")
	else:
		print("Ошибка сервера (Код " + str(response_code) + "): Python скрипт не отвечает")
