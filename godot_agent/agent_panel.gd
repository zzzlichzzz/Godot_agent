@tool
extends Control
@onready var chat_log: RichTextLabel = $VBoxContainer/ChatLog
@onready var input_field: TextEdit = $VBoxContainer/HBoxContainer/InputField
@onready var send_button: Button = $VBoxContainer/HBoxContainer/SendButton
@onready var http_request: HTTPRequest = $HTTPRequest
@onready var attach_checkbox: CheckBox = $VBoxContainer/AttachCodeCheckbox
# Ссылка на наш локальный Python-сервер
const LOCAL_SERVER_URL = "http://127.0.0.1:5000/chat"

func _ready() -> void:
	chat_log.selection_enabled = true
	chat_log.context_menu_enabled = true
	chat_log.text = "[color=green]Система готова. Работаем через локальный Python эмулятор (G4F)![/color]\n"

	if not send_button.pressed.is_connected(_on_send_pressed):
		send_button.pressed.connect(_on_send_pressed)
	if not http_request.request_completed.is_connected(_on_request_completed):
		http_request.request_completed.connect(_on_request_completed)

	# Нам больше не нужны настройки API-ключей, поэтому мы просто скрываем верхний блок
	if has_node("VBoxContainer/SettingsBox"):
		$VBoxContainer/SettingsBox.hide()

# BBCode использует [ и ] как спецсимволы для тегов. Текст, который печатает
# ПОЛЬЗОВАТЕЛЬ (например, вставленный кусок GDScript с массивами вроде
# [1, 2, 3] или Array[int]), может случайно сломать разметку в chat_log,
# т.к. RichTextLabel работает с bbcode_enabled = true. Экранируем перед
# вставкой — так же, как это уже сделано в парсере ответов ИИ на стороне Python.
func _escape_bbcode(text: String) -> String:
	return text.replace("[", "[lb]").replace("]", "[rb]")

func _on_send_pressed() -> void:
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

	# Отправляем запрос на локальный Python
	var headers = ["Content-Type: application/json"]
	var body = {"prompt": final_prompt}

	# Отключаем прокси (так как мы стучимся на локалхост)
	http_request.set_http_proxy("", 0)
	var err = http_request.request(LOCAL_SERVER_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))

	if err != OK:
		chat_log.text += "[color=red]Ошибка: Убедитесь, что Python скрипт ai_server.py запущен![/color]\n"

func _on_request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	if response_code == 200:
		var json = JSON.parse_string(body.get_string_from_utf8())
		if json and json.has("answer"):
			# ai_text уже приходит из Python в виде готового BBCode
			# (экранирование скобок там уже сделано) — повторно НЕ экранируем,
			# иначе собственные теги [b], [code] и т.п. превратятся в текст.
			var ai_text = json["answer"]
			chat_log.text += "\n[color=yellow]ИИ:[/color]\n" + ai_text + "\n\n-----------------\n"
		else:
			chat_log.text += "\n[color=red]Ошибка парсинга ответа от Python сервера.[/color]\n"
	else:
		chat_log.text += "\n[color=red]Ошибка сервера (Код " + str(response_code) + "): Python скрипт не отвечает.[/color]\n"
