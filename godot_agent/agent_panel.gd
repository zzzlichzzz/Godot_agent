@tool
extends Control

@onready var chat_log: RichTextLabel = $VBoxContainer/ChatLog
@onready var input_field: TextEdit = $VBoxContainer/HBoxContainer/InputField
@onready var send_button: Button = $VBoxContainer/HBoxContainer/SendButton
@onready var http_request: HTTPRequest = $HTTPRequest

# Элементы подтверждения действий ИИ
@onready var pending_action_box: HBoxContainer = $VBoxContainer/PendingActionBox
@onready var action_label: Label = $VBoxContainer/PendingActionBox/ActionLabel
@onready var confirm_button: Button = $VBoxContainer/PendingActionBox/ConfirmButton
@onready var reject_button: Button = $VBoxContainer/PendingActionBox/RejectButton

# Панель инструментов
@onready var advanced_toggle_btn: Button = $VBoxContainer/AdvancedToggleBtn
@onready var advanced_box: VBoxContainer = $VBoxContainer/AdvancedBox
@onready var reinit_button: Button = $VBoxContainer/AdvancedBox/ReinitButton
@onready var rollback_button: Button = $VBoxContainer/AdvancedBox/RollbackButton

const HOST = "127.0.0.1:5000"
const CHAT_URL = "http://" + HOST + "/chat"
const INIT_URL = "http://" + HOST + "/init"
const CONFIRM_URL = "http://" + HOST + "/chat/confirm_action"
const ROLLBACK_URL = "http://" + HOST + "/chat/rollback"


var _pending_request_kind: String = "chat"  
var _is_network_busy: bool = false
# Запоминаем детали последнего примененного действия для сброса кэша
var _last_pending_action_type: String = ""
var _last_pending_action_path: String = ""
var _last_pending_action_dest: String = ""


func _ready() -> void:
	chat_log.selection_enabled = true
	chat_log.context_menu_enabled = true
	chat_log.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	chat_log.scroll_following = true
	chat_log.text = "[color=green]Система готова. Работаем через локальный Браузерный ИИ-Агент![/color]\n"

	if pending_action_box:
		pending_action_box.visible = false

	if not send_button.pressed.is_connected(_on_send_pressed):
		send_button.pressed.connect(_on_send_pressed)
	if not http_request.request_completed.is_connected(_on_request_completed):
		http_request.request_completed.connect(_on_request_completed)
	if confirm_button and not confirm_button.pressed.is_connected(_on_confirm_pressed):
		confirm_button.pressed.connect(_on_confirm_pressed)
	if reject_button and not reject_button.pressed.is_connected(_on_reject_pressed):
		reject_button.pressed.connect(_on_reject_pressed)
	if reinit_button and not reinit_button.pressed.is_connected(_on_reinit_pressed):
		reinit_button.pressed.connect(_on_reinit_pressed)
		
	if advanced_toggle_btn and not advanced_toggle_btn.pressed.is_connected(_on_advanced_toggle):
		advanced_toggle_btn.pressed.connect(_on_advanced_toggle)
	if rollback_button and not rollback_button.pressed.is_connected(_on_rollback_pressed):
		rollback_button.pressed.connect(_on_rollback_pressed)


	if not input_field.gui_input.is_connected(_on_input_field_gui_input):
		input_field.gui_input.connect(_on_input_field_gui_input)

	if has_node("VBoxContainer/SettingsBox"):
		$VBoxContainer/SettingsBox.hide()

func _escape_bbcode(text: String) -> String:
	var result = ""
	for i in range(text.length()):
		var c = text[i]
		if c == "[":
			result += "[lb]"
		elif c == "]":
			result += "[rb]"
		else:
			result += c
	return result

func _set_ui_busy(busy: bool) -> void:
	_is_network_busy = busy
	send_button.disabled = busy
	reinit_button.disabled = busy
	rollback_button.disabled = busy
	input_field.editable = not busy
	if confirm_button: confirm_button.disabled = busy
	if reject_button: reject_button.disabled = busy
	send_button.text = "Ждём..." if busy else "Отправить"

func _on_advanced_toggle() -> void:
	advanced_box.visible = not advanced_box.visible
	advanced_toggle_btn.text = "⚙️ Скрыть доп. инструменты" if advanced_box.visible else "⚙️ Дополнительно"

func _on_input_field_gui_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_ENTER and event.ctrl_pressed:
			_on_send_pressed()
			accept_event()

func _on_reinit_pressed() -> void:
	if _is_network_busy: return
	chat_log.text += "[color=gray]Запрос на принудительное обновление дерева файлов...[/color]\n"
	
	var project_root = ProjectSettings.globalize_path("res://")
	var headers = ["Content-Type: application/json"]
	var body = {"project_root": project_root}

	http_request.set_http_proxy("", 0)
	_pending_request_kind = "init"
	_set_ui_busy(true)
	http_request.request(INIT_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))

func _on_send_pressed() -> void:
	if _is_network_busy: return
	if pending_action_box and pending_action_box.visible:
		_log_error("Сначала разрешите или отклоните текущее действие агента!")
		return

	var user_text = input_field.text.strip_edges()
	if user_text.is_empty(): return

	input_field.text = ""
	chat_log.text += "\n[color=lightblue]Вы:[/color] " + _escape_bbcode(user_text) + "\n"
	chat_log.text += "[color=gray]Агент анализирует проект...[/color]\n"

	var project_root = ProjectSettings.globalize_path("res://")
	var headers = ["Content-Type: application/json"]
	
	var body = {
		"prompt": user_text,
		"project_root": project_root
	}

	http_request.set_http_proxy("", 0)
	_pending_request_kind = "chat"
	_set_ui_busy(true)
	
	var err = http_request.request(CHAT_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error("Ошибка отправки сообщения.")
		_set_ui_busy(false)

func _on_confirm_pressed() -> void:
	_send_confirm_request(true)

func _on_reject_pressed() -> void:
	_send_confirm_request(false)

func _send_confirm_request(approved: bool) -> void:
	if _is_network_busy: return
	if pending_action_box:
		pending_action_box.visible = false
		
	var label = "Вы РАЗРЕШИЛИ действие" if approved else "Вы ОТКЛОНИЛИ действие"
	chat_log.text += "[color=gray]" + label + ". Жду ответа...[/color]\n"

	var headers = ["Content-Type: application/json"]
	var body = {"approved": approved}

	http_request.set_http_proxy("", 0)
	_pending_request_kind = "confirm"
	_set_ui_busy(true)
	
	var err = http_request.request(CONFIRM_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error("Ошибка отправки подтверждения.")
		_set_ui_busy(false)

func _on_rollback_pressed() -> void:
	if _is_network_busy: return
	chat_log.text += "[color=gray]Отмена последнего изменения...[/color]\n"

	http_request.set_http_proxy("", 0)
	_pending_request_kind = "rollback"
	_set_ui_busy(true)
	
	var err = http_request.request(ROLLBACK_URL, [], HTTPClient.METHOD_POST, "{}")
	if err != OK:
		_log_error("Ошибка при отправке запроса отката.")
		_set_ui_busy(false)

func _on_request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	_set_ui_busy(false)
	var kind = _pending_request_kind
	var response_str = body.get_string_from_utf8()
	var json = JSON.parse_string(response_str)

	if response_code == 200 and json != null:
		EditorInterface.get_resource_filesystem().scan()

		if kind == "confirm":
			_force_reload_open_script()

		if kind == "init":
			chat_log.text += "\n[color=green]Успех: Карта файлов сброшена. Следующий запрос заново настроит контекст ИИ.[/color]\n"
			return
		if kind == "rollback":
			chat_log.text += "\n[color=green]Успех: Последнее изменение файла отменено![/color]\n"
			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
			return

		if json.has("answer"):
			var ai_text = json["answer"]
			if ai_text == null: ai_text = ""
				
			chat_log.text += "\n[color=yellow]ИИ-Агент:[/color]\n" + str(ai_text) + "\n\n-----------------\n"

			var pending = json.get("pending_action")
			if pending != null and action_label and pending_action_box:
				var description = json.get("pending_action_description", "Агент запрашивает действие...")
				if description == null: description = "Агент запрашивает действие."
				action_label.text = str(description)
				pending_action_box.visible = true

				_last_pending_action_type = str(pending.get("action", ""))
				_last_pending_action_path = str(pending.get("path", ""))
				_last_pending_action_dest = str(pending.get("dest", ""))
			elif pending_action_box:
				pending_action_box.visible = false

			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
	else:
		var err_msg = "Сервер не отвечает."
		if json and json.has("error") and json["error"] != null:
			err_msg = str(json["error"])
		_log_error("Ошибка сервера (" + str(response_code) + "): " + err_msg)

func _log_error(msg: String) -> void:
	chat_log.text += "\n[color=red][Ошибка]: " + msg + "[/color]\n"

func _force_reload_open_script() -> void:
	var target_path := _last_pending_action_path
	if _last_pending_action_type == "move_file" and not _last_pending_action_dest.is_empty():
		target_path = _last_pending_action_dest

	if target_path.is_empty() or not target_path.begins_with("res://"):
		return
	if not FileAccess.file_exists(target_path):
		return

	var script_editor := EditorInterface.get_script_editor()
	if not script_editor:
		return

	# Ищем среди уже открытых вкладок нужный путь.
	# Если вкладка не открыта — трогать нечего, файл на диске и так актуален.
	var target_script: Script = null
	for scr in script_editor.get_open_scripts():
		if scr and scr.resource_path == target_path:
			target_script = scr
			break
	if target_script == null:
		return

	# КЛЮЧЕВОЕ ОТЛИЧИЕ от прошлой версии: читаем текст напрямую с диска
	# через FileAccess, полностью в обход ResourceLoader/GDScriptCache —
	# именно там была причина отката на старый текст.
	var file := FileAccess.open(target_path, FileAccess.READ)
	if not file:
		push_warning("Не удалось открыть файл для чтения: " + target_path)
		return
	var real_text := file.get_as_text()
	file.close()

	# Запоминаем текущую активную вкладку, чтобы вернуться к ней после
	# обновления и не "прыгать" перед глазами пользователя без необходимости.
	var previous_script := script_editor.get_current_script()

	EditorInterface.edit_script(target_script, -1, 0, false)
	var current_editor := script_editor.get_current_editor()
	if current_editor:
		var base_editor: Control = current_editor.get_base_editor()
		var code_edit := base_editor as CodeEdit

		if code_edit:
			# Защита от потери работы пользователя: если в открытой вкладке
			# ЕСТЬ несохранённые ручные правки (get_version() отличается от
			# get_saved_version()), НЕ перетираем их автоматически.
			var has_unsaved_edits := code_edit.get_version() != code_edit.get_saved_version()

			if has_unsaved_edits:
				push_warning("Вкладка '%s' содержит несохранённые правки — авто-обновление пропущено, чтобы не потерять их." % target_path)
			elif code_edit.text != real_text:
				var caret_line := code_edit.get_caret_line()
				var caret_col := code_edit.get_caret_column()
				code_edit.text = real_text
				code_edit.set_caret_line(min(caret_line, max(0, code_edit.get_line_count() - 1)))
				code_edit.set_caret_column(caret_col)
				# Помечаем текущее состояние как "сохранённое", иначе Godot
				# будет считать вкладку изменённой и может позже перезаписать
				# диск этим же (уже актуальным) содержимым — не страшно, но
				# лишний "*" в заголовке вкладки сбивает с толку.
				code_edit.tag_saved_version()
				print("Вкладка скрипта синхронизирована с диском: ", target_path)

	if previous_script and previous_script != target_script:
		EditorInterface.edit_script(previous_script, -1, 0, false)
