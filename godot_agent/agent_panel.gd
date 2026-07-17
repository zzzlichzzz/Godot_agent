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
const CHECK_LOG_URL = "http://" + HOST + "/project/check_log"
const SEND_LOG_URL = "http://" + HOST + "/project/send_log_errors"
const PROGRESS_URL = "http://" + HOST + "/chat/progress"

var _pending_request_kind: String = "chat"
var _is_network_busy: bool = false

# Запоминаем детали последнего примененного WRITE-действия для сброса кэша
var _last_pending_action_type: String = ""
var _last_pending_action_path: String = ""
var _last_pending_action_dest: String = ""

# Если сервер ответил, что для отката нужно подтверждение (файл менялся
# после действия агента) — следующее нажатие кнопки отката отправит force.
var _rollback_force_next: bool = false

# Канал «Ошибки запуска игры»: кнопка создаётся кодом (без правки .tscn),
# а флаг означает, что текущее подтверждение — это отправка отчёта модели.
var _log_errors_button: Button = null
var _pending_log_send: bool = false

# Автопроверка лога после закрытия игры (переход is_playing_scene: true→false).
var _play_watch_timer: Timer = null
var _was_playing: bool = false
var _auto_check: bool = false

# Подсветка изменённых агентом строк: помним путь и ТЕКСТ блока и красим
# строки там, где блок находится СЕЙЧАС (поиск по содержимому, а не по номерам).
const HL_COLOR := Color(0.25, 0.85, 0.35, 0.16)
var _hl_path: String = ""
var _hl_block: String = ""
var _hl_lines: Array = []
var _hl_code_edit: CodeEdit = null
var _list_mark_dbg_done: bool = false  # разовый диагностический вывод пометки списка скриптов
var _guard_timer: Timer = null       # таймер-охранник кнопок (вместо await — переживает перезагрузку скрипта)
var _guard_until_msec: int = 0        # до какого момента кнопки подтверждения заблокированы


# Живая трансляция: пока идёт запрос, отдельный HTTPRequest раз в секунду
# опрашивает /chat/progress и показывает статус + хвост ответа модели.
var _progress_http: HTTPRequest = null
var _progress_timer: Timer = null
var _progress_inflight: bool = false
var _status_label: Label = null
# Плавная «печать» ответа: текст приходит снимком, а выводим по буквам.
var _tw_timer: Timer = null
var _tw_buffer: String = ""
# Живой стрим ответа прямо в чат: сколько символов уже показано.
var _live_active: bool = false
var _live_start_len: int = 0
var _live_sent: int = 0


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
	if advanced_box and _log_errors_button == null:
		_log_errors_button = Button.new()
		_log_errors_button.text = "🐞 Ошибки запуска игры"
		advanced_box.add_child(_log_errors_button)
		_log_errors_button.pressed.connect(_on_check_log_pressed)
	_ensure_file_logging_enabled()
	if _play_watch_timer == null:
		_play_watch_timer = Timer.new()
		_play_watch_timer.wait_time = 1.0
		_play_watch_timer.one_shot = false
		add_child(_play_watch_timer)
		_play_watch_timer.timeout.connect(_on_play_watch_tick)
		_play_watch_timer.start()
	if _guard_timer == null:
		_guard_timer = Timer.new()
		_guard_timer.one_shot = true
		add_child(_guard_timer)
		_guard_timer.timeout.connect(_on_guard_timeout)
	if _progress_timer == null:
		_progress_timer = Timer.new()
		_progress_timer.wait_time = 1.0
		_progress_timer.one_shot = false
		add_child(_progress_timer)
		_progress_timer.timeout.connect(_on_progress_tick)
	if _progress_http == null:
		_progress_http = HTTPRequest.new()
		_progress_http.timeout = 4.0
		add_child(_progress_http)
		_progress_http.request_completed.connect(_on_progress_response)
	if _status_label == null:
		_status_label = Label.new()
		_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_status_label.add_theme_color_override("font_color", Color(0.62, 0.74, 0.95))
		_status_label.visible = false
		var vbox := $VBoxContainer
		vbox.add_child(_status_label)
		vbox.move_child(_status_label, chat_log.get_index() + 1)
	if _tw_timer == null:
		_tw_timer = Timer.new()
		_tw_timer.wait_time = 0.02
		_tw_timer.one_shot = false
		add_child(_tw_timer)
		_tw_timer.timeout.connect(_on_tw_tick)
	# Восстановление после перезагрузки скрипта: если панель перезагрузилась,
	# пока кнопки были временно заблокированы охранником — вернуть их в рабочее состояние.
	if confirm_button and reject_button and not _is_network_busy:
		confirm_button.disabled = false
		reject_button.disabled = false
	var se := EditorInterface.get_script_editor()
	if se and not se.editor_script_changed.is_connected(_on_editor_script_changed):
		se.editor_script_changed.connect(_on_editor_script_changed)
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
	if _log_errors_button: _log_errors_button.disabled = busy
	input_field.editable = not busy
	if confirm_button: confirm_button.disabled = busy
	if reject_button: reject_button.disabled = busy
	send_button.text = "Ждём..." if busy else "Отправить"
	# Живая трансляция: опрашиваем статус только пока идёт запрос.
	if busy:
		_tw_flush()
		_live_active = false
		_live_sent = 0
		if _progress_timer and _progress_timer.is_stopped():
			_progress_timer.start()
	else:
		if _progress_timer:
			_progress_timer.stop()
		if _status_label:
			_status_label.visible = false
		_progress_inflight = false


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
	_rollback_force_next = false
	var project_root = ProjectSettings.globalize_path("res://")
	var headers = ["Content-Type: application/json"]
	var body = {"project_root": project_root, "user_data_dir": OS.get_user_data_dir(), "reinit": true}
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
	_rollback_force_next = false
	chat_log.text += _bubble("Вы", "#a5d6a7", _escape_bbcode(user_text), "#1f3320", "#3a5a3c")
	chat_log.text += "[color=gray]Агент анализирует проект...[/color]\n"
	var project_root = ProjectSettings.globalize_path("res://")
	var headers = ["Content-Type: application/json"]
	var body = {
		"prompt": user_text,
		"project_root": project_root,
		"user_data_dir": OS.get_user_data_dir()
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
	# Подтверждение отправки отчёта об ошибках запуска — отдельная ветка:
	# при отказе сервер вообще не трогаем (и браузер тоже).
	if _pending_log_send:
		_pending_log_send = false
		if not approved:
			chat_log.text += "[color=gray]Отправка ошибок модели отменена.[/color]\n"
			return
		chat_log.text += "[color=gray]Отправляю ошибки модели. Жду ответа...[/color]\n"
		var log_headers = ["Content-Type: application/json"]
		http_request.set_http_proxy("", 0)
		_pending_request_kind = "chat"
		_set_ui_busy(true)
		var log_err = http_request.request(SEND_LOG_URL, log_headers, HTTPClient.METHOD_POST, JSON.stringify({}))
		if log_err != OK:
			_log_error("Ошибка отправки отчёта об ошибках.")
			_set_ui_busy(false)
		return
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
	if _rollback_force_next:
		chat_log.text += "[color=orange]Принудительный откат (подтверждено повторным нажатием)...[/color]\n"
	else:
		chat_log.text += "[color=gray]Отмена последнего изменения...[/color]\n"
	var headers = ["Content-Type: application/json"]
	var body = {"force": _rollback_force_next}
	_rollback_force_next = false
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "rollback"
	_set_ui_busy(true)
	var err = http_request.request(ROLLBACK_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error("Ошибка при отправке запроса отката.")
		_set_ui_busy(false)


func _ensure_file_logging_enabled() -> void:
	# Чтобы кнопка «Ошибки запуска» работала, игра должна писать лог в
	# user://logs/godot.log. На десктопе это обычно уже включено (override
	# .pc), но если выключено — включаем один раз и сохраняем настройки.
	var base_on := bool(ProjectSettings.get_setting("debug/file_logging/enable_file_logging", false))
	var pc_on := bool(ProjectSettings.get_setting("debug/file_logging/enable_file_logging.pc", true))
	if not base_on and not pc_on:
		ProjectSettings.set_setting("debug/file_logging/enable_file_logging.pc", true)
		ProjectSettings.save()
		print("Включено файловое логирование запусков игры (user://logs/godot.log).")


func _on_check_log_pressed() -> void:
	if _is_network_busy: return
	if pending_action_box and pending_action_box.visible:
		_log_error("Сначала разрешите или отклоните текущее действие агента!")
		return
	chat_log.text += "[color=gray]Читаю лог последнего ��апуска игры...[/color]\n"
	_pending_log_send = false
	_auto_check = false
	_rollback_force_next = false
	var headers = ["Content-Type: application/json"]
	var body = {
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
	}
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "check_log"
	_set_ui_busy(true)
	var err = http_request.request(CHECK_LOG_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error("Ошибка отправки запроса проверки лога.")
		_set_ui_busy(false)


func _on_request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	_set_ui_busy(false)
	var kind = _pending_request_kind
	var response_str = body.get_string_from_utf8()
	var json = JSON.parse_string(response_str)

	if response_code == 200 and json != null:
		EditorInterface.get_resource_filesystem().scan()

		if kind == "init":
			chat_log.text += "\n[color=green]Успех: Карта файлов сброшена. Следующий запрос заново настроит контекст ИИ.[/color]\n"
			return

		if kind == "rollback":
			var msg = str(json.get("message", "Последнее изменение файла отменено!"))
			chat_log.text += "\n[color=green]Успех: " + _escape_bbcode(msg) + "[/color]\n"
			# Синхронизируем откаченные файлы с открытыми вкладками. Иначе
			# вкладка показывает ДО-откатный текст, и Godot может позже
			# молча пересохранить его ПОВЕРХ результата отката.
			var paths = json.get("paths")
			if paths is Array:
				for p in paths:
					_sync_open_script_with_disk(str(p))
			# Подсвечиваем восстановленный после отката блок (или гасим старое).
			var rb_path = json.get("changed_path")
			var rb_block = json.get("changed_block")
			if rb_path != null and rb_block != null and str(rb_block) != "":
				_apply_agent_highlight(str(rb_path), str(rb_block))
			else:
				_clear_agent_highlight()
			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
			return

		if kind == "check_log":
			var was_auto := _auto_check
			_auto_check = false
			var found := int(json.get("found", 0))
			var log_info := str(json.get("log_time", "?"))
			if found == 0:
				if was_auto:
					chat_log.text += "[color=gray]Авто-проверка: в логе запуска (" + log_info + ") ошибок нет.[/color]\n"
				else:
					chat_log.text += "\n[color=green]✅ В логе запу��ка (" + log_info + ") ошибок не найдено.[/color]\n"
			else:
				var head := "🐞 Игра закрыта, в логе найдены ошибки: " if was_auto else "Найдено ошибок: "
				chat_log.text += "\n[color=orange]" + head + str(found) + " (лог от " + log_info + ")[/color]\n" + _escape_bbcode(str(json.get("summary", ""))) + "\n"
				if action_label and pending_action_box:
					action_label.text = "Отправить " + str(found) + " ошибок модели на исправление?"
					pending_action_box.visible = true
					_pending_log_send = true
					_guard_confirm_buttons()
			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
			return

		# После подтверждённого WRITE-действия — синхронизируем открытую вкладку.
		# При пакетном чтении файлов _last_pending_action_type пуст — ничего не трогаем.
		if kind == "confirm" and _last_pending_action_type != "":
			_force_reload_open_script()
			_last_pending_action_type = ""
			_last_pending_action_path = ""
			_last_pending_action_dest = ""
			# Открываем изменённый файл и подсвечиваем строки, написанные агентом.
			var ch_path = json.get("changed_path")
			var ch_block = json.get("changed_block")
			if ch_path != null and ch_block != null and str(ch_block) != "":
				_apply_agent_highlight(str(ch_path), str(ch_block))

		# Текстовый ответ ИИ (не печатаем пустые ответы)
		var has_answer: bool = json.has("answer") and json["answer"] != null and str(json["answer"]) != ""
		if has_answer:
			_finalize_live_block()
			chat_log.text += _bubble("ИИ-Агент", "#ffd54f", str(json["answer"]), "#26303d", "#3a4a63")

		# Промежуточное подтверждение файла из пачки на чтение:
		# сервер НЕ ходил в браузер, просто спрашивает про следующий файл.
		var nxt = json.get("next_confirmation")
		if nxt != null and action_label and pending_action_box:
			action_label.text = str(nxt.get("description", "Агент запрашивает файл..."))
			pending_action_box.visible = true
			_guard_confirm_buttons()
			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
			return

		# WRITE-действие, требующее подтверждения
		var pending = json.get("pending_action")
		if pending != null and action_label and pending_action_box:
			var description = json.get("pending_action_description", "Агент запрашивает действие...")
			if description == null: description = "Агент запрашивает действие."
			# Красивый предпросмотр: сервер присылает ЧИСТЫЙ код (без JSON-обёртки).
			var pcode = json.get("pending_action_code")
			if pcode != null and str(pcode) != "":
				chat_log.text += "[bgcolor=#1f2430][color=#8ab4f8] ▸ предлагаемый код [/color][/bgcolor]\n[bgcolor=#2b2b2b][code]" + _escape_bbcode(str(pcode)) + "[/code][/bgcolor]\n"
			action_label.text = str(description)
			pending_action_box.visible = true
			_last_pending_action_type = str(pending.get("action", ""))
			_last_pending_action_path = str(pending.get("path", ""))
			_last_pending_action_dest = str(pending.get("dest", ""))
			_guard_confirm_buttons()
		elif pending_action_box:
			pending_action_box.visible = false
			# Ни текста, ни действий — не молчим, чтобы ответ не "пропадал" бесследно.
			if not has_answer and (kind == "chat" or kind == "confirm"):
				chat_log.text += "[color=gray][Система]: Сервер вернул пустой ответ (без текста и действий). Проверьте вкладку AI Studio.[/color]\n"

		await get_tree().process_frame
		chat_log.scroll_to_line(chat_log.get_line_count() - 1)
	else:
		if kind == "check_log" and _auto_check:
			# Авто-проверка не спамит в чат: нет лога, лог уже отправлялся,
			# сервер занят или выключен — просто тихо пропускаем.
			_auto_check = false
			if json and json.has("error"):
				print("Авто-проверка лога пропущена: ", str(json["error"]))
			return
		var err_msg = "Сервер не отвечает."
		if json and json.has("error") and json["error"] != null:
			err_msg = str(json["error"])
		# Сервер просит подтвердить откат повторным нажатием кнопки.
		if json != null and json.get("needs_force") == true:
			_rollback_force_next = true
		_log_error("Ошибка сервера (" + str(response_code) + "): " + err_msg)


func _log_error(msg: String) -> void:
	_tw_flush()
	chat_log.text += "\n[color=red][Ошибка]: " + msg + "[/color]\n"


func _guard_confirm_buttons() -> void:
	# Защита от случайных быстрых/двойных кликов: когда появляется НОВОЕ
	# подтверждение, кнопки ненадолго блокируются, чтобы второй клик по
	# инерции не одобрил следующее действие мгновенно.
	# ВАЖНО: без await/корутин. При перезагрузке плагина Godot отменял
	# приостановленный await — и кнопки навсегда оставались серыми.
	if not confirm_button or not reject_button:
		return
	confirm_button.disabled = true
	reject_button.disabled = true
	_guard_until_msec = Time.get_ticks_msec() + 700
	if _guard_timer:
		_guard_timer.stop()
		_guard_timer.wait_time = 0.7
		_guard_timer.start()


func _on_guard_timeout() -> void:
	if not _is_network_busy and confirm_button and reject_button:
		confirm_button.disabled = false
		reject_button.disabled = false


func _reconcile_confirm_buttons() -> void:
	# Страховка на случай, если таймер-охранник не сработал из-за
	# перезагрузки скрипта: раз в секунду проверяем и возвращаем кнопки,
	# если окно подтверждения открыто, сеть свободна и время охраны прошло.
	if not confirm_button or not reject_button:
		return
	if not pending_action_box or not pending_action_box.visible:
		return
	if _is_network_busy:
		return
	if Time.get_ticks_msec() >= _guard_until_msec and (confirm_button.disabled or reject_button.disabled):
		confirm_button.disabled = false
		reject_button.disabled = false


func _force_reload_open_script() -> void:
	var target_path := _last_pending_action_path
	if _last_pending_action_type == "move_file" and not _last_pending_action_dest.is_empty():
		target_path = _last_pending_action_dest
	_sync_open_script_with_disk(target_path)


func _sync_open_script_with_disk(target_path: String) -> void:
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
	# Чит��ем текст напрямую с диска через FileAccess, полностью в обход
	# ResourceLoader/GDScriptCache — именно там была причина отката на старый текст.
	var file := FileAccess.open(target_path, FileAccess.READ)
	if not file:
		push_warning("Не удалось открыть файл для чтения: " + target_path)
		return
	var real_text := file.get_as_text()
	file.close()
	# Запоминаем текущую активную вкладку, чтобы вернуться к ней после обновления.
	var previous_script := script_editor.get_current_script()
	EditorInterface.edit_script(target_script, -1, 0, false)
	var current_editor := script_editor.get_current_editor()
	if current_editor:
		var base_editor: Control = current_editor.get_base_editor()
		var code_edit := base_editor as CodeEdit
		if code_edit:
			# Защита от потери работы пользователя: если в открытой вкладке
			# ЕСТЬ несохранённые ручные правки — НЕ перетираем их автоматически.
			var has_unsaved_edits := code_edit.get_version() != code_edit.get_saved_version()
			if has_unsaved_edits:
				push_warning("Вкладка '%s' содержит несохранённые правки — авто-обновление пропущено, чтобы не потерять их." % target_path)
			elif code_edit.text != real_text:
				var caret_line := code_edit.get_caret_line()
				var caret_col := code_edit.get_caret_column()
				code_edit.text = real_text
				code_edit.set_caret_line(min(caret_line, max(0, code_edit.get_line_count() - 1)))
				code_edit.set_caret_column(caret_col)
				# Помечаем текущее состояние как "сохранённое", чтобы не было лишнего "*".
				code_edit.tag_saved_version()
				print("Вкладка скрипта синхронизирована с диском: ", target_path)
	if previous_script and previous_script != target_script:
		EditorInterface.edit_script(previous_script, -1, 0, false)


# ---------------------------------------------------------------------------
# Автопроверка лога после закрытия игры: следим за is_playing_scene()
# и после остановки игры сами проверяем лог. В браузер при этом НИЧЕГО
# не уходит — отправка ошибок по-прежнему только после подтверждения.
# ---------------------------------------------------------------------------

func _on_play_watch_tick() -> void:
	_highlight_watchdog()
	_reconcile_confirm_buttons()
	var playing := EditorInterface.is_playing_scene()
	if _was_playing and not playing:
		_was_playing = false
		# Игра только что закрылась: даём Godot дописать лог и проверяем.
		await get_tree().create_timer(1.2).timeout
		_auto_check_log()
		return
	_was_playing = playing


func _auto_check_log() -> void:
	# Не мешаем текущей работе: если идёт запрос или ждём подтверждения —
	# тихо пропускаем (ручная кнопка всегда доступна).
	if _is_network_busy: return
	if pending_action_box and pending_action_box.visible: return
	_auto_check = true
	_pending_log_send = false
	var headers = ["Content-Type: application/json"]
	var body = {
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
	}
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "check_log"
	_set_ui_busy(true)
	var err = http_request.request(CHECK_LOG_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_set_ui_busy(false)
		_auto_check = false


# ---------------------------------------------------------------------------
# Подсветка строк, изменённых агентом.
# Красим не по номерам строк, а ПО СОДЕРЖИМОМУ блока: при любой правке
# блок ищется заново, и подсветка «переезжает» вместе с кодом. Если
# пользователь отредактировал сам блок — подсветка гаснет (это уже
# не код агента).
# ---------------------------------------------------------------------------

func _apply_agent_highlight(path: String, block: String) -> void:
	_clear_agent_highlight()
	_list_mark_dbg_done = false
	if not path.begins_with("res://") or not path.ends_with(".gd"):
		return
	if not FileAccess.file_exists(path):
		return
	var scr := load(path) as Script
	if scr == null:
		return
	_hl_path = path
	_hl_block = block.replace("\r\n", "\n").strip_edges(false, true)
	if _hl_block.is_empty():
		return
	# Открываем изменённый скрипт в редакторе, чтобы изменения были на виду.
	EditorInterface.edit_script(scr, -1, 0, false)
	_hook_current_code_edit()
	_repaint_highlight()
	if _hl_code_edit and _hl_lines.size() > 0:
		_hl_code_edit.set_caret_line(_hl_lines[0])
	_mark_script_in_list_experimental(path)


func _hook_current_code_edit() -> void:
	_hl_code_edit = null
	var script_editor := EditorInterface.get_script_editor()
	if not script_editor: return
	var current := script_editor.get_current_editor()
	if not current: return
	var code_edit := current.get_base_editor() as CodeEdit
	if not code_edit: return
	_hl_code_edit = code_edit
	if not code_edit.text_changed.is_connected(_on_hl_text_changed):
		code_edit.text_changed.connect(_on_hl_text_changed)


func _on_hl_text_changed() -> void:
	# Текст меняется — блок мог сместиться. Ищем его заново и перекрашиваем.
	if _hl_block != "":
		_repaint_highlight()


func _on_editor_script_changed(scr: Script) -> void:
	# Вернулись на вкладку с подсвеченным скриптом — восстанавливаем покрас.
	if scr and _hl_path != "" and scr.resource_path == _hl_path:
		_hook_current_code_edit()
		_repaint_highlight()


func _clear_agent_highlight() -> void:
	if _hl_code_edit and is_instance_valid(_hl_code_edit):
		for l in range(_hl_code_edit.get_line_count()):
			_hl_code_edit.set_line_background_color(l, Color(0, 0, 0, 0))
	_hl_lines = []
	_hl_path = ""
	_hl_block = ""
	_hl_code_edit = null


func _repaint_highlight() -> void:
	if _hl_code_edit == null or not is_instance_valid(_hl_code_edit):
		return
	# Сначала гасим все строки: после правок номера могли сместиться,
	# и точечная очистка по старым номерам оставила бы «хвосты».
	for l in range(_hl_code_edit.get_line_count()):
		_hl_code_edit.set_line_background_color(l, Color(0, 0, 0, 0))
	_hl_lines = []
	if _hl_block == "":
		return
	var idx := _hl_code_edit.text.find(_hl_block)
	if idx == -1:
		return  # блок изменён/удалён пользователем — подсвечивать нечего
	var start_line := _hl_code_edit.text.substr(0, idx).count("\n")
	var block_line_count := _hl_block.count("\n") + 1
	for i in range(block_line_count):
		var line := start_line + i
		if line < _hl_code_edit.get_line_count():
			_hl_code_edit.set_line_background_color(line, HL_COLOR)
			_hl_lines.append(line)


func _highlight_watchdog() -> void:
	# Редактор Godot при перепроверке кода (наведение мыши, пауза после
	# правок) САМ сбрасывает фоновые цвета строк (так он рисует строки
	# с ошибками). Раз в секунду проверяем и восстанавливаем подсветку,
	# если её затёрли. То же с зелёным именем в списке скриптов — список
	# часто перестраивается, поэтому пометка наносится заново каждый тик.
	if _hl_block == "":
		return
	if _hl_code_edit == null or not is_instance_valid(_hl_code_edit):
		return
	var intact := _hl_lines.size() > 0
	for l in _hl_lines:
		if l >= _hl_code_edit.get_line_count() or _hl_code_edit.get_line_background_color(l) != HL_COLOR:
			intact = false
			break
	if not intact:
		_repaint_highlight()
	_mark_script_in_list_experimental(_hl_path)


func _mark_script_in_list_experimental(path: String) -> void:
	# ЭКСПЕРИМЕНТ: список скриптов слева — внутренний UI редактора без
	# публичного API. Если внутренности Godot изменятся — функция просто
	# тихо ничего не сделает, не влияя на остальной плагин.
	if path.is_empty(): return
	var script_editor := EditorInterface.get_script_editor()
	if not script_editor: return
	var fname := path.get_file()
	var lists_found := 0
	var matched := 0
	# Проходим ПО ВСЕМ ItemList внутри редактора скриптов. Совпадение ищем
	# и по видимому тексту, и по tooltip — в нём редактор хранит полный
	# путь к скрипту (надёжнее, чем текст, который может быть с пометками).
	for node in script_editor.find_children("*", "ItemList", true, false):
		var item_list := node as ItemList
		if item_list == null: continue
		lists_found += 1
		for i in range(item_list.item_count):
			var t := item_list.get_item_text(i)
			var tip := item_list.get_item_tooltip(i)
			if t == fname or t.begins_with(fname + "(") or tip == path or tip.ends_with("/" + fname):
				item_list.set_item_custom_fg_color(i, Color(0.45, 1.0, 0.45))
				matched += 1
	if not _list_mark_dbg_done:
		_list_mark_dbg_done = true
		print("[ИИ-Агент] Пометка в списке скриптов: ItemList найдено %d, совпадений %d (файл: %s)" % [lists_found, matched, fname])


# ---------------------------------------------------------------------------
# Живая трансляция ответа: пока идёт запрос к серверу, раз в секунду
# спрашиваем /chat/progress и показываем фазу («думает…», «пишет…»),
# время, счётчик символов и хвост ответа прямо под чатом.
# Отдельный HTTPRequest не мешает основному запросу (у Godot один
# HTTPRequest = один запрос за раз), а сервер отдаёт снимок состояния
# мгновенно, не трогая браузер.
# ---------------------------------------------------------------------------

func _on_progress_tick() -> void:
	if not _is_network_busy:
		if _progress_timer:
			_progress_timer.stop()
		if _status_label:
			_status_label.visible = false
		return
	if _progress_inflight or _progress_http == null:
		return
	_progress_http.set_http_proxy("", 0)
	var err = _progress_http.request(PROGRESS_URL)
	if err == OK:
		_progress_inflight = true


func _on_progress_response(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_progress_inflight = false
	if not _is_network_busy or _status_label == null:
		return
	if response_code != 200:
		return
	var json = JSON.parse_string(body.get_string_from_utf8())
	if json == null or typeof(json) != TYPE_DICTIONARY:
		return
	if not bool(json.get("active", false)):
		return
	var phase := str(json.get("phase", "работаю…"))
	var elapsed := int(json.get("elapsed", 0))
	var chars := int(json.get("chars", 0))
	var line := "🤖 " + phase
	if elapsed > 0:
		line += " · " + str(elapsed) + " с"
	if chars > 0:
		line += " · " + str(chars) + " симв."
	_status_label.text = line
	_status_label.visible = true
	# Текст ответа больше НЕ показываем в статусе — он стримится прямо в чат.
	_feed_live_stream(str(json.get("stream", "")))


# ---------------------------------------------------------------------------
# Плавная «печать» ответа. Ответ приходит целиком (снимком), но выводим
# его порциями по буквам — выглядит как живая печать. BBCode-теги
# вставляются целиком, чтобы разметка не ломалась на середине тега.
# ---------------------------------------------------------------------------

func _tw_flush() -> void:
	# Мгновенно допечатать всё оставшееся (перед новым запросом/ошибкой).
	if _tw_buffer != "":
		chat_log.text += _tw_buffer
		_tw_buffer = ""
	if _tw_timer:
		_tw_timer.stop()


func _chat_append_typed(text: String) -> void:
	_tw_buffer += text
	if _tw_timer and _tw_timer.is_stopped():
		_tw_timer.start()


func _on_tw_tick() -> void:
	if _tw_buffer == "":
		if _tw_timer:
			_tw_timer.stop()
		return
	# Скорость адаптивная: чем длиннее остаток, тем крупнее порция —
	# короткий ответ печатается по буквам, длинный не заставляет ждать.
	var step: int = clamp(int(_tw_buffer.length() / 100.0) + 2, 2, 40)
	var out := ""
	while step > 0 and _tw_buffer != "":
		var c := _tw_buffer[0]
		if c == "[":
			var close := _tw_buffer.find("]")
			if close == -1:
				out += _tw_buffer
				_tw_buffer = ""
				break
			out += _tw_buffer.substr(0, close + 1)
			_tw_buffer = _tw_buffer.substr(close + 1)
		else:
			out += c
			_tw_buffer = _tw_buffer.substr(1)
		step -= 1
	chat_log.text += out
	if _tw_buffer == "":
		if _tw_timer:
			_tw_timer.stop()


# ---------------------------------------------------------------------------
# «Пузыри» сообщений и живой стрим ответа прямо в чат.
# Пока модель печатает в браузере, текст сразу появляется в чате
# (печатается по буквам), а по завершении черновик заменяется
# финальным оформленным ответом (код-блоки, цвета) в виде пузыря.
# ---------------------------------------------------------------------------

func _bubble(header: String, header_color: String, body: String, bg: String, border: String) -> String:
	return "\n[table=1][cell bg=" + bg + " border=" + border + " padding=10,8,10,8][color=" + header_color + "][b]" + header + "[/b][/color]\n" + body + "\n[/cell][/table]\n"


func _finalize_live_block() -> void:
	# Стрим окончен: убираем черновой текст, дальше придёт финальный
	# оформленный ответ в виде пузыря.
	_tw_flush()
	if _live_active:
		chat_log.text = chat_log.text.substr(0, _live_start_len)
	_live_active = false
	_live_sent = 0


func _feed_live_stream(stream: String) -> void:
	if stream == "":
		return
	if not _live_active:
		_tw_flush()
		_live_start_len = chat_log.text.length()
		chat_log.text += "\n[color=yellow]ИИ-Агент[/color] [color=gray](печатает…)[/color]\n"
		_live_active = true
		_live_sent = 0
	if stream.length() > _live_sent:
		var delta := stream.substr(_live_sent)
		_live_sent = stream.length()
		_chat_append_typed(_escape_bbcode(delta))
