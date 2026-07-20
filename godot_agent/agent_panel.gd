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
const ROLLBACK_PREVIEW_URL = "http://" + HOST + "/chat/rollback/preview"
const CHECK_LOG_URL = "http://" + HOST + "/project/check_log"
const SEND_LOG_URL = "http://" + HOST + "/project/send_log_errors"
const PROGRESS_URL = "http://" + HOST + "/chat/progress"
const API_EXPORT_URL = "http://" + HOST + "/project/update_api_cache"
const API_CACHE_STATUS_URL = "http://" + HOST + "/project/api_cache_status"
const PLAN_STEP_URL = "http://" + HOST + "/chat/plan/step"
const PLAN_STOP_URL = "http://" + HOST + "/chat/plan/stop"
const CHAT_STOP_URL = "http://" + HOST + "/chat/stop"
const PLAN_ROLLBACK_CHAIN_URL = "http://" + HOST + "/chat/plan/rollback_chain"

var _pending_request_kind: String = "chat"
var _is_network_busy: bool = false

# Plan-режим (цепочка действий): активен, когда пользователь подтвердил план
# и панель сама выполняет шаги через PLAN_STEP_URL по одному.
var _plan_active: bool = false
var _plan_chain_id: String = ""
var _plan_total: int = 0
var _plan_index: int = 0
var _plan_stop_button: Button = null
var _stop_button: Button = null
var _plan_rollback_dialog: ConfirmationDialog = null
var _plan_rollback_chain_id: String = ""
var _plan_rollback_force_next: bool = false

# Запоминаем детали последнего примененного WRITE-действия для сброса кэша
var _last_pending_action_type: String = ""
var _last_pending_action_path: String = ""
var _last_pending_action_dest: String = ""
var _scenes_to_reopen: PackedStringArray = PackedStringArray()  # v49: сцены, закрытые перед записью

# Если сервер ответил, что для отката нужно подтверждение (файл менялся
# после действия агента) — следующее нажатие кнопки отката отправит force.
var _rollback_force_next: bool = false

# Закрытие «вкладки-призрака» после отката, удалившего файл с диска.
var _ghost_close_path: String = ""
var _ghost_prev_script: Script = null

# Канал «Ошибки запуска игры»: кнопка создаётся кодом (без правки .tscn),
# а флаг означает, что текущее подтверждение — это отправка отчёта модели.
var _log_errors_button: Button = null
var _api_export_button: Button = null
var _pending_log_send: bool = false

# Автопроверка актуальности кэша API при старте панели: сервер (с браузером внутри) может подняться не сразу, поэтому при неудаче повторяем с нарастающей задержкой, а не молча сдаёмся после первой неудачи.
var _api_cache_check_attempts: int = 0
var _api_cache_check_timer: Timer = null

# Автопроверка лога после закрытия игры (переход is_playing_scene: true→false).
var _play_watch_timer: Timer = null
var _was_playing: bool = false
var _auto_check: bool = false

var _hl = null  # подсистема подсветки (agent_highlight.gd)
var _start_screen: Control = null
var _pending_chat_prompt: String = ""
var _site_dialog: ConfirmationDialog = null
var _resend_after_open: bool = false
var _guard_timer: Timer = null       # таймер-охранник кнопок (вместо await — переживает перезагрузку скрипта)
var _guard_until_msec: int = 0        # до какого момента кнопки подтверждения заблокированы


# Живая трансляция: пока идёт запрос, отдельный HTTPRequest раз в секунду
# опрашивает /chat/progress и показывает статус + хвост ответа модели.
var _progress_http: HTTPRequest = null
var _progress_timer: Timer = null
var _progress_inflight: bool = false
# Весь визуал чата (пузыри, печать, стрим, статус) — в agent_chat_view.gd.
var _view: Node = null
# --- Чаты: список, создание, переименование, удаление ---
var _link: Node = null               # связь с сервером — весь транспорт и автозапуск в agent_server_link.gd
var _pagewait_timer: Timer = null
var _pagewait_left: int = 0
var _pending_view: String = ""
var _loc = null                      # скрипт локализации agent_locale.gd
var _bar_btn_new: Button = null
var _bar_btn_ren: Button = null
var _bar_btn_del: Button = null
var _bar_btn_home: Button = null
var _delete_dialog: ConfirmationDialog = null
var _rollback_dialog: ConfirmationDialog = null
var _chat_select: OptionButton = null
var _rename_dialog: AcceptDialog = null
var _rename_edit: LineEdit = null
var _current_chat_id: String = ""
var _suppress_chat_select: bool = false


func _locale():
	if _loc == null:
		var sc := get_script() as Script
		if sc:
			var lp := sc.resource_path.get_base_dir() + "/agent_locale.gd"
			if FileAccess.file_exists(lp):
				_loc = load(lp)
	return _loc


func _t(key: String) -> String:
	var l = _locale()
	if l:
		return l.t(key)
	return key


func _ready() -> void:
	_ensure_script_autoreload_setting()
	chat_log.selection_enabled = true
	chat_log.context_menu_enabled = true
	chat_log.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	chat_log.scroll_following = true
	chat_log.text = "[color=green]" + _t("system_ready") + "[/color]\n"
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
		_log_errors_button.text = _t("log_errors")
		advanced_box.add_child(_log_errors_button)
		_log_errors_button.pressed.connect(_on_check_log_pressed)
	if advanced_box and _api_export_button == null:
		_api_export_button = Button.new()
		_api_export_button.text = _t("api_export_btn")
		advanced_box.add_child(_api_export_button)
		_api_export_button.pressed.connect(_on_export_api_pressed)
	call_deferred("_check_api_cache_freshness")
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
	if has_node("ChatView"):
		_view = get_node("ChatView")
	else:
		var view_script = load(get_script().resource_path.get_base_dir() + "/agent_chat_view.gd")
		_view = view_script.new()
		_view.name = "ChatView"
		add_child(_view)
	_view.setup(chat_log, $VBoxContainer)
	if _hl == null:
		var hl_script = load(get_script().resource_path.get_base_dir() + "/agent_highlight.gd")
		_hl = hl_script.new()
	if _link == null:
		if has_node("ServerLink"):
			_link = get_node("ServerLink")
		else:
			var link_script = load(get_script().resource_path.get_base_dir() + "/agent_server_link.gd")
			_link = link_script.new()
			_link.name = "ServerLink"
			add_child(_link)
	if not _link.chats_response.is_connected(_on_chats_payload):
		_link.chats_response.connect(_on_chats_payload)
	if not _link.link_status.is_connected(_notify):
		_link.link_status.connect(_notify)
	if not _link.show_loading_requested.is_connected(_on_link_show_loading):
		_link.show_loading_requested.connect(_on_link_show_loading)
	if not _link.hide_loading_requested.is_connected(_on_link_hide_loading):
		_link.hide_loading_requested.connect(_on_link_hide_loading)
	if not _link.server_state_changed.is_connected(_on_server_state_changed):
		_link.server_state_changed.connect(_on_server_state_changed)
	if $VBoxContainer.has_node("ChatsBar"):
		var bar_old: HBoxContainer = $VBoxContainer/ChatsBar
		_chat_select = bar_old.get_child(0)
		if not _chat_select.item_selected.is_connected(_on_chat_selected):
			_chat_select.item_selected.connect(_on_chat_selected)
		if bar_old.get_child_count() >= 5:
			_bar_btn_new = bar_old.get_child(1) as Button
			_bar_btn_ren = bar_old.get_child(2) as Button
			_bar_btn_del = bar_old.get_child(3) as Button
			_bar_btn_home = bar_old.get_child(4) as Button
		_apply_chatbar_texts()
	else:
		var bar := HBoxContainer.new()
		bar.name = "ChatsBar"
		_chat_select = OptionButton.new()
		_chat_select.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_chat_select.item_selected.connect(_on_chat_selected)
		bar.add_child(_chat_select)
		_bar_btn_new = Button.new()
		_bar_btn_new.text = "＋"
		_bar_btn_new.pressed.connect(_on_chat_new_pressed)
		bar.add_child(_bar_btn_new)
		_bar_btn_ren = Button.new()
		_bar_btn_ren.text = "✏"
		_bar_btn_ren.pressed.connect(_on_chat_rename_pressed)
		bar.add_child(_bar_btn_ren)
		_bar_btn_del = Button.new()
		_bar_btn_del.text = "🗑"
		_bar_btn_del.pressed.connect(_on_chat_delete_pressed)
		bar.add_child(_bar_btn_del)
		_bar_btn_home = Button.new()
		_bar_btn_home.pressed.connect(_show_start_ui)
		bar.add_child(_bar_btn_home)
		_apply_chatbar_texts()
		$VBoxContainer.add_child(bar)
		$VBoxContainer.move_child(bar, 0)
	# Фоновое авто-обновление списка чатов при открытии панели — БЕЗ автозапуск���
	# сервера: если сервер ещё не поднят, просто ждём, пока пользователь сам
	# нажмёт «новый чат»/«загрузить чат» (иначе при каждом открытии Godot
	# запускалась бы своя копия сервера, независимо от действий пользователя).
	call_deferred("_request_chats", "list", {}, false)
	if _start_screen == null:
		var ss_script = load(get_script().resource_path.get_base_dir() + "/agent_start_screen.gd")
		_start_screen = ss_script.new()
		_start_screen.name = "StartScreen"
		add_child(_start_screen)
		_start_screen.set_anchors_preset(Control.PRESET_FULL_RECT)
		_start_screen.new_chat_requested.connect(_on_start_new_chat)
		_start_screen.load_chat_requested.connect(_on_start_load_chat)
		_start_screen.sites_tab_requested.connect(_on_sites_tab_requested)
		_start_screen.chats_tab_requested.connect(_on_chats_tab_requested)
		if _start_screen.has_signal("language_changed"):
			_start_screen.language_changed.connect(_on_language_changed)
		if _start_screen.has_signal("open_server_requested"):
			_start_screen.open_server_requested.connect(_on_open_server_folder_pressed)
	_show_start_ui()
	call_deferred("_request_chats", "sites", {}, false)
	call_deferred("_on_language_changed")
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
	if _api_export_button: _api_export_button.disabled = busy
	input_field.editable = not busy
	if confirm_button: confirm_button.disabled = busy
	if reject_button: reject_button.disabled = busy
	send_button.text = _t("sending") if busy else _t("send")
	# Живая трансляция: опрашива����������м статус только пока идёт запрос.
	if busy:
		if _view:
			_view.reset_live()
		if _progress_timer and _progress_timer.is_stopped():
			_progress_timer.start()
		_show_stop_button()
	else:
		if _progress_timer:
			_progress_timer.stop()
		if _view:
			_view.hide_status()
		_progress_inflight = false
		_hide_stop_button()


func _on_server_state_changed(running: bool) -> void:
	# Кнопка ручного запуска сервера теперь живёт на стартовом экране
	# (agent_start_screen.gd), рядом с переключателем языка — видна только
	# пока сервер не отвечает. Раньше она добавлялась в $VBoxContainer, но
	# стартовый экран рисуется поверх него на весь экран и закрывал её целиком —
	# поэтому кнопку никто не видел. Автозапуск продолжает работать как раньше.
	if _start_screen and _start_screen.has_method("set_server_running"):
		_start_screen.set_server_running(running)


func _on_open_server_folder_pressed() -> void:
	if _link == null:
		return
	var exe: String = _link.open_server_folder()
	if exe == "":
		_notify("Не нашёл godot_agent_server.exe — соберите сервер (build_server_exe.bat) или укажите путь в server_path.txt", "error")
	else:
		_notify("Открыл папку сервера: " + exe, "info")


func _show_stop_button() -> void:
	# Кнопка «Стоп» для ОБЫЧНОЙ обработки запроса (не путать с остановкой плана).
	if _stop_button == null:
		_stop_button = Button.new()
		_stop_button.pressed.connect(_on_stop_pressed)
		if send_button and send_button.get_parent():
			send_button.get_parent().add_child(_stop_button)
		else:
			add_child(_stop_button)
	_stop_button.text = "■ Стоп"
	_stop_button.tooltip_text = "Остановить обработку текущего запроса"
	_stop_button.visible = true
	_stop_button.disabled = false


func _hide_stop_button() -> void:
	if _stop_button:
		_stop_button.visible = false


func _on_stop_pressed() -> void:
	# Основной http_request занят самим запросом /chat — шлём остановку
	# отдельным одноразовым HTTPRequest. Сервер прервёт ожидание ответа,
	# и текущий запрос вернётся с пометкой [Остановлено].
	if _stop_button:
		_stop_button.disabled = true
		_stop_button.text = "Останавливаю…"
	var req := HTTPRequest.new()
	add_child(req)
	req.request_completed.connect(func(_r, _rc, _h, _b): req.queue_free())
	var err = req.request(CHAT_STOP_URL, ["Content-Type: application/json"], HTTPClient.METHOD_POST, "{}")
	if err != OK:
		req.queue_free()
		if _stop_button:
			_stop_button.disabled = false
			_stop_button.text = "■ Стоп"


func _on_advanced_toggle() -> void:
	advanced_box.visible = not advanced_box.visible
	advanced_toggle_btn.text = _t("advanced_hide") if advanced_box.visible else _t("advanced_show")


func _on_input_field_gui_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_ENTER and event.ctrl_pressed:
			_on_send_pressed()
			accept_event()


func _on_reinit_pressed() -> void:
	if _is_network_busy: return
	chat_log.text += "[color=gray]" + _t("tree_refresh") + "[/color]\n"
	_rollback_force_next = false
	var project_root = ProjectSettings.globalize_path("res://")
	var headers = ["Content-Type: application/json"]
	var body = {"project_root": project_root, "user_data_dir": OS.get_user_data_dir(), "addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()), "reinit": true}
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "init"
	_set_ui_busy(true)
	http_request.request(INIT_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))


func _on_send_pressed() -> void:
	if _is_network_busy: return
	if pending_action_box and pending_action_box.visible:
		_log_error(_t("resolve_action_first"))
		return
	var user_text = input_field.text.strip_edges()
	if user_text.is_empty(): return
	input_field.text = ""
	_rollback_force_next = false
	_view.add_user_message(_escape_bbcode(user_text))
	_view.add_system(_t("analyzing"))
	_send_chat_raw(user_text, false)


func _send_chat_raw(prompt: String, ignore_mismatch: bool) -> void:
	_pending_chat_prompt = prompt
	var project_root = ProjectSettings.globalize_path("res://")
	var headers = ["Content-Type: application/json"]
	var body = {
		"prompt": prompt,
		"project_root": project_root,
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir())
	}
	if ignore_mismatch:
		body["ignore_site_mismatch"] = true
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "chat"
	_set_ui_busy(true)
	var err = http_request.request(CHAT_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("err_send"))
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
			chat_log.text += "[color=gray]" + _t("errs_cancelled") + "[/color]\n"
			return
		chat_log.text += "[color=gray]" + _t("errs_sending") + "[/color]\n"
		var log_headers = ["Content-Type: application/json"]
		http_request.set_http_proxy("", 0)
		_pending_request_kind = "chat"
		_set_ui_busy(true)
		var log_err = http_request.request(SEND_LOG_URL, log_headers, HTTPClient.METHOD_POST, JSON.stringify({}))
		if log_err != OK:
			_log_error(_t("err_send_report"))
			_set_ui_busy(false)
		return
	if approved:
		_close_scenes_before_write()  # v49: закрываем открытую целевую сцену перед записью
	var label = _t("approved_action") if approved else _t("rejected_action")
	chat_log.text += "[color=gray]" + label + _t("waiting_reply") + "[/color]\n"
	var headers = ["Content-Type: application/json"]
	var body = {"approved": approved}
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "confirm"
	_set_ui_busy(true)
	var err = http_request.request(CONFIRM_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("err_send_confirm"))
		_set_ui_busy(false)
		_reopen_scenes_after_write()  # v49: запрос не ушёл — вернуть закрытые сцены


func _start_plan_execution(total: int) -> void:
	_plan_active = true
	_plan_total = total
	_plan_index = 0
	chat_log.text += "[color=gray]" + (_t("plan_started") % total) + "[/color]\n"
	_show_plan_stop_button()
	_request_plan_step()


func _request_plan_step() -> void:
	if _is_network_busy: return
	var headers = ["Content-Type: application/json"]
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "plan_step"
	_set_ui_busy(true)
	var err = http_request.request(PLAN_STEP_URL, headers, HTTPClient.METHOD_POST, "{}")
	if err != OK:
		_log_error(_t("err_plan_step"))
		_set_ui_busy(false)
		_end_plan_execution()


func _end_plan_execution() -> void:
	_plan_active = false
	_hide_plan_stop_button()


func _show_plan_stop_button() -> void:
	if _plan_stop_button == null:
		_plan_stop_button = Button.new()
		_plan_stop_button.pressed.connect(_on_plan_stop_pressed)
		if advanced_box:
			advanced_box.add_child(_plan_stop_button)
		else:
			add_child(_plan_stop_button)
	_plan_stop_button.text = _t("plan_stop_btn")
	_plan_stop_button.visible = true
	_plan_stop_button.disabled = false


func _hide_plan_stop_button() -> void:
	if _plan_stop_button:
		_plan_stop_button.visible = false


func _on_plan_stop_pressed() -> void:
	if _is_network_busy or not _plan_active: return
	if _plan_stop_button: _plan_stop_button.disabled = true
	var headers = ["Content-Type: application/json"]
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "plan_stop"
	_set_ui_busy(true)
	var err = http_request.request(PLAN_STOP_URL, headers, HTTPClient.METHOD_POST, "{}")
	if err != OK:
		_log_error(_t("err_plan_step"))
		_set_ui_busy(false)
		_end_plan_execution()


var _reload_project_dialog: ConfirmationDialog = null


func _note_autoload_removed(json) -> void:
	# Откат мог оставить в project.godot висячую запись автозагрузки на файл,
	# которого больше нет (см. clean_dangling_autoloads на серве��е) — сообщаем,
	# что она уже убрана, чтобы пользователь не искал причину ошибок автозагрузки сам.
	var removed = json.get("autoload_removed")
	if removed is Array and removed.size() > 0:
		chat_log.text += "[color=gray]" + (_t("autoload_cleaned") % ", ".join(removed)) + "[/color]\n"


func _maybe_prompt_project_reload(json) -> void:
	# project.godot изменился в обход обычного действия модели (откат, откат
	# цепочки, чистка автозагрузки) — эти правки видны Godot ТОЛЬКО после
	# перезапуска редактора/ручного "Reload Current Project", иначе автозагрузка
	# ещё долго будет ошибаться на устаревшие пути. Предлагаем перезапуск сразу.
	var touched := false
	if bool(json.get("project_godot_changed", false)):
		touched = true
	else:
		var pths = json.get("paths")
		if pths is Array:
			for pp in pths:
				if str(pp).ends_with("project.godot"):
					touched = true
					break
		var cp = json.get("changed_path")
		if cp != null and str(cp).ends_with("project.godot"):
			touched = true
	if not touched:
		return
	if _reload_project_dialog == null:
		_reload_project_dialog = ConfirmationDialog.new()
		_reload_project_dialog.confirmed.connect(_on_reload_project_confirmed)
		add_child(_reload_project_dialog)
	_reload_project_dialog.title = _t("reload_project_title")
	_reload_project_dialog.dialog_text = _t("reload_project_text")
	_reload_project_dialog.ok_button_text = _t("reload_project_yes")
	_reload_project_dialog.get_cancel_button().text = _t("reload_project_no")
	_reload_project_dialog.popup_centered()


func _on_reload_project_confirmed() -> void:
	chat_log.text += "[color=gray]" + _t("reload_project_doing") + "[/color]\n"
	if _view: _view.flush()
	# true = перезапустить движок на том же проекте (Godot 4.3+); подхватывает
	# свежий project.godot (автозагрузки, main scene и т.п.) без ручных действий.
	EditorInterface.restart_editor(true)


func _show_plan_rollback_dialog(chain_id: String, desc: String) -> void:
	_plan_rollback_chain_id = chain_id
	if _plan_rollback_dialog == null:
		_plan_rollback_dialog = ConfirmationDialog.new()
		_plan_rollback_dialog.confirmed.connect(_on_plan_rollback_confirmed)
		add_child(_plan_rollback_dialog)
	_plan_rollback_dialog.title = _t("plan_rb_title")
	_plan_rollback_dialog.dialog_text = _t("plan_rb_text") % desc
	_plan_rollback_dialog.ok_button_text = _t("rb_yes")
	_plan_rollback_dialog.get_cancel_button().text = _t("rb_no")
	_plan_rollback_dialog.popup_centered()


func _on_plan_rollback_confirmed() -> void:
	# v40: если сервер ранее ответил needs_force (файл менялся не из этой цепочки),
	# это повторное подтверждение уже означает согласие откатить принудительно —
	# раньше сюда всегда уходил force=false, и повторное нажатие «Да» просто
	# бесконечно повторяло тот же отказ (внешне выглядело так, будто кнопка не работает).
	if _plan_rollback_force_next:
		chat_log.text += "[color=orange]" + _t("force_rollback") + "[/color]\n"
		_send_plan_rollback_chain_request(true)
		return
	_send_plan_rollback_chain_request(false)


func _send_plan_rollback_chain_request(force: bool) -> void:
	if _is_network_busy: return
	var headers = ["Content-Type: application/json"]
	var body = {"chain_id": _plan_rollback_chain_id, "force": force}
	_plan_rollback_force_next = false
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "plan_rollback_chain"
	_set_ui_busy(true)
	var err = http_request.request(PLAN_ROLLBACK_CHAIN_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("err_rollback"))
		_set_ui_busy(false)


func _on_rollback_pressed() -> void:
	if _is_network_busy: return
	if _rollback_force_next:
		# Повторное нажатие после needs_force — откатываем без лишних вопросов.
		chat_log.text += "[color=orange]" + _t("force_rollback") + "[/color]\n"
		_send_rollback_request(true)
		return
	# Сначала спрашиваем сервер, ЧТО именно будет отменено (и из какого
	# чата было это изменение), чтобы не откатить вслепую чужую работу.
	var headers = ["Content-Type: application/json"]
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "rollback_preview"
	_set_ui_busy(true)
	var err = http_request.request(ROLLBACK_PREVIEW_URL, headers, HTTPClient.METHOD_POST, "{}")
	if err != OK:
		_log_error(_t("err_rollback"))
		_set_ui_busy(false)


func _send_rollback_request(force: bool) -> void:
	var headers = ["Content-Type: application/json"]
	var body = {"force": force}
	_rollback_force_next = false
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "rollback"
	_set_ui_busy(true)
	var err = http_request.request(ROLLBACK_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("err_rollback"))
		_set_ui_busy(false)


func _show_rollback_dialog(desc: String) -> void:
	if _rollback_dialog == null:
		_rollback_dialog = ConfirmationDialog.new()
		_rollback_dialog.confirmed.connect(_on_rollback_confirmed)
		add_child(_rollback_dialog)
	_rollback_dialog.title = _t("rb_title")
	_rollback_dialog.dialog_text = _t("rb_text") % desc
	_rollback_dialog.ok_button_text = _t("rb_yes")
	_rollback_dialog.get_cancel_button().text = _t("rb_no")
	_rollback_dialog.popup_centered()


func _on_rollback_confirmed() -> void:
	chat_log.text += "[color=gray]" + _t("rollback_msg") + "[/color]\n"
	_send_rollback_request(false)


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
		_log_error(_t("resolve_action_first"))
		return
	chat_log.text += "[color=gray]" + _t("reading_log") + "[/color]\n"
	_pending_log_send = false
	_auto_check = false
	_rollback_force_next = false
	var headers = ["Content-Type: application/json"]
	var body = {
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()),
	}
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "check_log"
	_set_ui_busy(true)
	var err = http_request.request(CHECK_LOG_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("err_log_req"))
		_set_ui_busy(false)


func _check_api_cache_freshness() -> void:
	if _is_network_busy:
		_schedule_api_cache_check_retry()
		return
	var headers = ["Content-Type: application/json"]
	var body = {
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()),
		"godot_version": Engine.get_version_info().get("string", ""),
	}
	_pending_request_kind = "api_cache_status"
	_set_ui_busy(true)
	var err = http_request.request(API_CACHE_STATUS_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_set_ui_busy(false)
		_schedule_api_cache_check_retry()


func _schedule_api_cache_check_retry() -> void:
	_api_cache_check_attempts += 1
	if _api_cache_check_attempts > 8:
		return
	if _api_cache_check_timer == null:
		_api_cache_check_timer = Timer.new()
		_api_cache_check_timer.one_shot = true
		add_child(_api_cache_check_timer)
		_api_cache_check_timer.timeout.connect(_check_api_cache_freshness)
	_api_cache_check_timer.wait_time = min(2.0 * _api_cache_check_attempts, 15.0)
	_api_cache_check_timer.start()


func _on_export_api_pressed() -> void:
	if _is_network_busy: return
	if pending_action_box and pending_action_box.visible:
		_log_error(_t("resolve_action_first"))
		return
	_export_api_to_server(false)


# silent = true — тихий а��томатический запуск при старте плагина (не блокирует сеть для пользователя,
# просто показывает одно сообщение, если реально пришлось пересобирать).
func _export_api_to_server(silent: bool) -> void:
	if not silent:
		chat_log.text += "[color=gray]" + _t("api_export_sending") + "[/color]\n"
	var export_script = load(get_script().resource_path.get_base_dir() + "/agent_api_export.gd")
	var classes: Dictionary = export_script.export_classes()
	var headers = ["Content-Type: application/json"]
	var body = {
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()),
		"classes": classes,
		"godot_version": Engine.get_version_info().get("string", ""),
	}
	_pending_request_kind = "api_export"
	_set_ui_busy(true)
	var err = http_request.request(API_EXPORT_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("api_export_err"))
		_set_ui_busy(false)


func _on_request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	_set_ui_busy(false)
	var kind = _pending_request_kind
	var response_str = body.get_string_from_utf8()
	# Вызываем JSON.parse_string только при успешном соединении и непустом теле ответа —
	# иначе (например, когда сервер ещё не поднялся и соединение отказано/без тела)
	# сам JSON.parse_string на пустой строке логирует в консоль встроенную ошибку движка
	# «Parse JSON failed. Error at line 0: Unknown error getting token», даже если результат
	# всё равно игнорируется ниже — итоговая причина повторяющихся ошибок в консоли при ожидании запуска сервера.
	var json = null
	if result == OK and not response_str.is_empty():
		json = JSON.parse_string(response_str)

	if response_code == 200 and json != null:
		EditorInterface.get_resource_filesystem().scan()

		if json.has("site_mismatch") and bool(json.get("site_mismatch", false)):
			_handle_site_mismatch(str(json.get("site", "")), str(json.get("prompt", "")))
			return

		if kind == "init":
			chat_log.text += "\n[color=green]" + _t("reinit_done") + "[/color]\n"
			return

		if kind == "confirm" and bool(json.get("plan_started", false)):
			_reopen_scenes_after_write()  # v49: подтверждение запустило план — вернуть сцены
			_last_pending_action_type = ""
			_last_pending_action_path = ""
			_last_pending_action_dest = ""
			var has_answer_plan: bool = json.has("answer") and json["answer"] != null and str(json["answer"]) != ""
			if has_answer_plan:
				_view.add_agent_message(str(json["answer"]))
			_start_plan_execution(int(json.get("plan_total", 0)))
			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
			return

		if kind == "plan_step":
			var p_index := int(json.get("index", 0))
			var p_total := int(json.get("total", _plan_total))
			var p_chain := str(json.get("chain_id", _plan_chain_id))
			_plan_chain_id = p_chain
			_plan_index = p_index
			var p_msg := str(json.get("message", ""))
			var p_ok := bool(json.get("ok", false))
			var p_done := bool(json.get("done", false))
			var p_stopped := bool(json.get("stopped", false))
			if p_ok:
				chat_log.text += "[color=gray]" + _escape_bbcode(p_msg) + "[/color]\n"
			else:
				chat_log.text += "[color=orange]" + _escape_bbcode(p_msg) + "[/color]\n"
			var p_ch_path = json.get("changed_path")
			var p_ch_block = json.get("changed_block")
			if p_ch_path != null and p_ch_block != null and str(p_ch_block) != "":
				if _hl: _hl.apply(str(p_ch_path), str(p_ch_block))
			_force_reload_open_script()
			if p_ch_path != null:
				_auto_reload_changed_scene(str(p_ch_path))
			if p_done:
				_end_plan_execution()
				chat_log.text += "[color=green]" + _t("plan_done") + "[/color]\n"
			elif p_stopped:
				_end_plan_execution()
				chat_log.text += "[color=orange]" + (_t("plan_stopped_desc") % [p_index, p_total]) + "[/color]\n"
				_show_plan_rollback_dialog(p_chain, _t("plan_rb_step_desc") % [p_index, p_total])
			else:
				_request_plan_step()
			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
			return

		if kind == "plan_stop":
			var s_index := int(json.get("index", _plan_index))
			var s_total := int(json.get("total", _plan_total))
			var s_chain := str(json.get("chain_id", _plan_chain_id))
			_end_plan_execution()
			chat_log.text += "[color=orange]" + (_t("plan_stopped_manual") % [s_index, s_total]) + "[/color]\n"
			if s_index > 0:
				_show_plan_rollback_dialog(s_chain, _t("plan_rb_step_desc") % [s_index, s_total])
			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
			return

		if kind == "plan_rollback_chain":
			var pr_msg = str(json.get("message", _t("rollback_done")))
			chat_log.text += "\n[color=green]" + _t("success_prefix") + _escape_bbcode(pr_msg) + "[/color]\n"
			_note_autoload_removed(json)
			var pr_paths = json.get("paths")
			if pr_paths is Array:
				for pp in pr_paths:
					if FileAccess.file_exists(str(pp)):
						_sync_open_script_with_disk(str(pp))
						_auto_reload_changed_scene(str(pp))
					else:
						_close_ghost_script_tab(str(pp))
			if _hl: _hl.clear()
			_maybe_prompt_project_reload(json)
			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
			return

		if kind == "api_export":
			var cnt := int(json.get("classes_count", 0))
			chat_log.text += "[color=green]" + _t("api_export_done") % cnt + "[/color]\n"
			return

		if kind == "api_cache_status":
			_api_cache_check_attempts = 0
			var has_cache = bool(json.get("has_cache", false))
			var cached_version = str(json.get("cached_version", ""))
			var current_version = Engine.get_version_info().get("string", "")
			if not has_cache or cached_version != current_version:
				_export_api_to_server(true)
			return

		if kind == "rollback_preview":
			if bool(json.get("found", false)):
				# Если последнее действие — шаг ещё неоткатанной цепочки плана (есть
				# chain_id и в ней больше 1 шага), предлагаем откатить всю цепочку сразу
				# через уже готовый диалог/запрос отката цепочки, а не по одному действию.
				var pv_chain := str(json.get("chain_id", ""))
				var pv_chain_total := int(json.get("chain_total", 0))
				if pv_chain != "" and pv_chain_total > 1:
					_show_plan_rollback_dialog(pv_chain, _t("plan_rb_step_desc") % [pv_chain_total, pv_chain_total])
				else:
					_show_rollback_dialog(str(json.get("description", "")))
			else:
				chat_log.text += "[color=gray]" + _t("rb_nothing") + "[/color]\n"
			return

		if kind == "rollback":
			var msg = str(json.get("message", _t("rollback_done")))
			chat_log.text += "\n[color=green]" + _t("success_prefix") + _escape_bbcode(msg) + "[/color]\n"
			_note_autoload_removed(json)
			# Синхронизируем откаченные файлы с открытыми вкладками. Иначе
			# вкладка показывает ДО-откатный текст, и Godot может позже
			# молча пересохранить его ПОВЕРХ результата отката.
			var paths = json.get("paths")
			if paths is Array:
				for p in paths:
					if FileAccess.file_exists(str(p)):
						_sync_open_script_with_disk(str(p))
						_auto_reload_changed_scene(str(p))
					else:
						# Откат удалил созданный файл — закрываем его вкладку,
						# ина��е Godot держит «призрака» и может пересохранить файл обратно.
						_close_ghost_script_tab(str(p))
			# Подсвечиваем восстановленный после отката блок (или гасим старое).
			var rb_path = json.get("changed_path")
			var rb_block = json.get("changed_block")
			if rb_path != null and rb_block != null and str(rb_block) != "":
				if _hl: _hl.apply(str(rb_path), str(rb_block))
			else:
				if _hl: _hl.clear()
			_maybe_prompt_project_reload(json)
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
					chat_log.text += "[color=gray]" + (_t("log_auto_ok") % log_info) + "[/color]\n"
				else:
					chat_log.text += "\n[color=green]" + (_t("log_ok") % log_info) + "[/color]\n"
			else:
				var head := _t("log_errs_auto") if was_auto else _t("log_errs")
				chat_log.text += "\n[color=orange]" + head + str(found) + " (" + _t("log_from") + " " + log_info + ")[/color]\n" + _escape_bbcode(str(json.get("summary", ""))) + "\n"
				if action_label and pending_action_box:
					action_label.text = _t("send_errors_q") % str(found)
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
			if _last_pending_action_path != "":
				_auto_reload_changed_scene(_last_pending_action_path)
			if _last_pending_action_dest != "":
				_auto_reload_changed_scene(_last_pending_action_dest)
			_reopen_scenes_after_write()  # v49: вернуть сцены, закрытые перед записью, — уже в новом виде
			_last_pending_action_type = ""
			_last_pending_action_path = ""
			_last_pending_action_dest = ""
			# Открываем изменённый файл и подсвечиваем строки, написанные агентом.
			var ch_path = json.get("changed_path")
			var ch_block = json.get("changed_block")
			if ch_path != null and ch_block != null and str(ch_block) != "":
				if _hl: _hl.apply(str(ch_path), str(ch_block))

		# Текстовый ответ ИИ (не печатаем пустые ответы)
		var has_answer: bool = json.has("answer") and json["answer"] != null and str(json["answer"]) != ""
		if has_answer:
			_view.add_agent_message(str(json["answer"]))
			_request_chats("list", {})  # обновить авто-названия чатов

		# Промежуточное подтверждение файла из пачки на чтение:
		# сервер НЕ ходил в браузер, просто спрашивает про следующий файл.
		var nxt = json.get("next_confirmation")
		if nxt != null and action_label and pending_action_box:
			action_label.text = str(nxt.get("description", _t("agent_wants_file")))
			pending_action_box.visible = true
			_guard_confirm_buttons()
			await get_tree().process_frame
			chat_log.scroll_to_line(chat_log.get_line_count() - 1)
			return

		# WRITE-действие, требующее подтверждения
		var pending = json.get("pending_action")
		if pending != null and action_label and pending_action_box:
			var description = json.get("pending_action_description", _t("agent_wants_action"))
			if description == null: description = _t("agent_wants_action")
			# Красивый предпросмотр: сервер присылает ЧИСТЫЙ код (без JSON-обёртки).
			var pcode = json.get("pending_action_code")
			if pcode != null and str(pcode) != "":
				_view.add_code_preview(_escape_bbcode(str(pcode)))
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
				chat_log.text += "[color=gray]" + _t("empty_response") + "[/color]\n"

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
		if kind == "api_cache_status":
			_schedule_api_cache_check_retry()
			return
		if kind == "confirm":
			_reopen_scenes_after_write()  # v49: действие не выполнено — вернуть закрытые сцены
		var err_msg = _t("srv_no_reply")
		if json and json.has("error") and json["error"] != null:
			err_msg = str(json["error"])
		# Сервер просит подтвердить откат повторным нажатием кнопки.
		# v40: раньше здесь всегда выставлялся _rollback_force_next (флаг одиночного
		# отката), даже для отката всей цепочки плана (kind == "plan_rollback_chain") — а его
		# никто не читал, потому кнопка «Откатить» (одиночный откат) тут не задействована, а
		# диалог отката цеп��ци всё равно снова посылал force=false и молча падал снова и снова
		# (внешне выглядело как «нажал и ничего не произошло»). Теперь для plan_rollback_chain
		# ставится свой собственный флаг _plan_rollback_force_next, и диалог подтверждения показывается
		# ещё раз, чтобы следующее подтверждение ушло с force=true.
		if json != null and json.get("needs_force") == true:
			if kind == "plan_rollback_chain":
				_plan_rollback_force_next = true
				chat_log.text += "[color=orange]" + _t("plan_rb_needs_force") + "[/color]\n"
				_show_plan_rollback_dialog(_plan_rollback_chain_id, _t("plan_rb_force_desc"))
				await get_tree().process_frame
				chat_log.scroll_to_line(chat_log.get_line_count() - 1)
				return
			_rollback_force_next = true
		_log_error((_t("srv_error") % str(response_code)) + err_msg)


func _log_error(msg: String) -> void:
	if _view:
		_view.flush()
	chat_log.text += "\n[color=red]" + _t("error_prefix") + msg + "[/color]\n"


func _guard_confirm_buttons() -> void:
	# Защита от случайных быстрых/двой������ кликов: когда появляется НОВОЕ
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


func _auto_reload_changed_scene(p: String) -> void:
	# v46: агент изменил сцену на диске — если она открыта в редакторе, перечитываем
	# её САМИ, чтобы пользователю не приходилось вручную отвечать на вопрос
	# «файлы изменены снаружи — перезагрузить?» после каждого действия агента.
	if not (p.ends_with(".tscn") or p.ends_with(".scn")):
		return
	if not FileAccess.file_exists(p):
		return
	for sp in EditorInterface.get_open_scenes():
		if str(sp) == p:
			EditorInterface.reload_scene_from_path(p)
			return


func _close_scenes_before_write() -> void:
	# v49: Godot не применяет правки с ДИСКА к уже открытой сцене — изменения агента
	# «не видны», пока сцену не закрыть и не открыть заново. Поэтому перед одобренной
	# записью закрываем целевую сцену (сам файл агент правит на диске), а после ответа
	# сервера открываем её обратно уже в новом виде — без вопросов о перезагрузке.
	_scenes_to_reopen = PackedStringArray()
	var ei: Object = EditorInterface
	if not ei.has_method("close_scene"):
		return  # старый Godot без close_scene: остаётся авто-перечитывание (v46)
	for raw in [_last_pending_action_path, _last_pending_action_dest]:
		var sp := str(raw)
		if sp == "" or not (sp.ends_with(".tscn") or sp.ends_with(".scn")):
			continue
		if not EditorInterface.get_open_scenes().has(sp):
			continue
		EditorInterface.open_scene_from_path(sp)  # делаем вкладку сцены активной
		if int(ei.call("close_scene")) == OK and not _scenes_to_reopen.has(sp):
			_scenes_to_reopen.append(sp)


func _reopen_scenes_after_write() -> void:
	# v49: открываем обратно сцены, закрытые перед записью. Если действие
	# не выполнилось или файл переехал/удалён — просто пропускаем.
	for sp in _scenes_to_reopen:
		if FileAccess.file_exists(str(sp)):
			EditorInterface.open_scene_from_path(str(sp))
	_scenes_to_reopen = PackedStringArray()


func _ensure_script_autoreload_setting() -> void:
	# v46: включаем в настройках редактора автоперечитывание скриптов,
	# изменённых вне Godot (по аналогии с авто-включением файлового лога):
	# убирает постоянный вопрос о перезагрузке скриптов после правок агента.
	var es = EditorInterface.get_editor_settings()
	if es == null:
		return
	var key := "text_editor/behavior/files/auto_reload_scripts_on_external_change"
	if es.has_setting(key) and not bool(es.get_setting(key)):
		es.set_setting(key, true)


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
	# Читаем текст напрямую с диска через FileAccess, полностью в обход
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
	if _hl: _hl.watchdog()
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
		"addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()),
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
# Красим не по номерам строк, а ПО СОДЕРЖИМОМУ ��лока: при любой правке
# блок ищется заново, и подсветка «переезжает» вместе с кодом. Если
# пользователь отредактировал сам блок — подсветка гаснет (это уже
# не код агента).
# ---------------------------------------------------------------------------

func _on_progress_tick() -> void:
	if not _is_network_busy:
		if _progress_timer:
			_progress_timer.stop()
		if _view:
			_view.hide_status()
		return
	if _progress_inflight or _progress_http == null:
		return
	_progress_http.set_http_proxy("", 0)
	var err = _progress_http.request(PROGRESS_URL)
	if err == OK:
		_progress_inflight = true


func _on_progress_response(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_progress_inflight = false
	if not _is_network_busy or _view == null:
		return
	if response_code != 200:
		return
	var json = JSON.parse_string(body.get_string_from_utf8())
	if json == null or typeof(json) != TYPE_DICTIONARY:
		return
	if not bool(json.get("active", false)):
		return
	# Статус ��� только состояние бота; сам текст стримится прямо в чат (в _view).
	_view.show_status(str(json.get("phase", _t("working"))), int(json.get("elapsed", 0)), int(json.get("chars", 0)))
	_view.feed_live_stream(str(json.get("stream", "")))


# ---------------------------------------------------------------------------
# Чаты: список, созда��ие, выбор (открывает страницу в браузере),
# переименование, удаление. Сохранённ��й диалог восстанавливается в панели.
# ---------------------------------------------------------------------------

func _request_chats(kind: String, extra: Dictionary, allow_autostart: bool = true) -> void:
	if _link == null:
		return
	if _is_network_busy and kind != "list" and kind != "sites" and kind != "status":
		_log_error(_t("wait_current"))
		return
	_link.request(kind, extra, allow_autostart)


func _on_chats_payload(kind: String, json: Dictionary, _extra: Dictionary) -> void:
	if kind == "status":
		_on_browser_status(json)
		return
	if kind == "sites":
		if _start_screen:
			_start_screen.set_sites(json.get("sites", []))
			if _pending_view == "sites":
				_pending_view = ""
				_start_screen.show_sites()
		return
	var cur = json.get("current_id")
	if cur != null:
		_current_chat_id = str(cur)
	_fill_chat_list(json.get("chats", []))
	if _start_screen:
		_start_screen.set_chats(json.get("chats", []))
		if _pending_view == "chats":
			_pending_view = ""
			_start_screen.show_chats()
	if kind == "open" and _view:
		_view.clear()
		_render_transcript(json.get("transcript", []))
		_view.add_system(_t("chat_opened") % str(json.get("title", "")))
		var warn: String = str(json.get("warning", ""))
		if warn != "":
			_view.add_system(warn)
			_notify(warn, "error")
		_enter_chat_ui()
		_begin_page_wait()
		if _resend_after_open:
			_resend_after_open = false
			_send_chat_raw(_pending_chat_prompt, true)
	elif kind == "new" and _view:
		_view.clear()
		_view.add_system(_t("chat_created"))
		_view.add_hint(_t("pick_model_hint"))  # v48/v49: напоминание выбрать модель — заметным окошком
		_enter_chat_ui()
		_begin_page_wait()
	elif kind == "delete":
		# После удаления чата не открываем автоматически другой чат —
		# просто возвращаем на главный экран: пользователь сам выберет,
		# загрузить сохранённый чат или создать новый.
		_current_chat_id = ""
		_on_link_hide_loading()
		_show_start_ui()


func _fill_chat_list(chats) -> void:
	if _chat_select == null or typeof(chats) != TYPE_ARRAY:
		return
	_suppress_chat_select = true
	_chat_select.clear()
	var sel := -1
	for i in chats.size():
		var c = chats[i]
		if typeof(c) != TYPE_DICTIONARY:
			continue
		var label := str(c.get("title", _t("untitled")))
		var sname := str(c.get("site_name", ""))
		if sname != "":
			label += " — " + sname
		if bool(c.get("prompt_stale", false)):
			label += "  " + _t("prompt_stale_short")
		_chat_select.add_item(label, i)
		_chat_select.set_item_metadata(i, str(c.get("id", "")))
		if str(c.get("id", "")) == _current_chat_id:
			sel = i
	if sel >= 0:
		_chat_select.select(sel)
	_suppress_chat_select = false


func _on_chat_selected(index: int) -> void:
	if _suppress_chat_select or _chat_select == null:
		return
	var id := str(_chat_select.get_item_metadata(index))
	if id == "" or id == _current_chat_id:
		return
	if _start_screen:
		_show_start_ui()
		_start_screen.show_loading(_t("opening_chat"))
	_request_chats("open", {"id": id})


func _on_chat_new_pressed() -> void:
	# «＋» в чате открывает выбор сайта (нейросети). Важ��о сначала
	# показать стартовый экран — иначе экран загрузки останется невидимым.
	_show_start_ui()
	_on_sites_tab_requested()


func _on_chat_rename_pressed() -> void:
	if _current_chat_id == "":
		_log_error(_t("select_chat_hint"))
		return
	if _rename_dialog == null:
		_rename_dialog = AcceptDialog.new()
		_rename_dialog.title = _t("tip_rename")
		_rename_edit = LineEdit.new()
		_rename_edit.custom_minimum_size = Vector2(260, 0)
		_rename_dialog.add_child(_rename_edit)
		_rename_dialog.register_text_enter(_rename_edit)
		_rename_dialog.confirmed.connect(_on_rename_confirmed)
		add_child(_rename_dialog)
	if _chat_select and _chat_select.selected >= 0:
		_rename_edit.text = _chat_select.get_item_text(_chat_select.selected)
	_rename_dialog.title = _t("tip_rename")
	_rename_dialog.popup_centered()
	_rename_edit.grab_focus()


func _on_rename_confirmed() -> void:
	var t := _rename_edit.text.strip_edges()
	if t == "":
		return
	_request_chats("rename", {"id": _current_chat_id, "title": t})


func _on_chat_delete_pressed() -> void:
	if _current_chat_id == "":
		_log_error(_t("select_chat_first"))
		return
	# Защита от случайных нажатий: диалог подтверждения.
	if _delete_dialog == null:
		_delete_dialog = ConfirmationDialog.new()
		_delete_dialog.confirmed.connect(_on_delete_confirmed)
		add_child(_delete_dialog)
	_delete_dialog.title = _t("del_title")
	var chat_title := ""
	if _chat_select and _chat_select.selected >= 0:
		chat_title = _chat_select.get_item_text(_chat_select.selected)
	_delete_dialog.dialog_text = _t("del_text") % chat_title
	_delete_dialog.ok_button_text = _t("del_yes")
	_delete_dialog.get_cancel_button().text = _t("del_no")
	_delete_dialog.popup_centered()


func _on_delete_confirmed() -> void:
	if _current_chat_id == "":
		return
	_request_chats("delete", {"id": _current_chat_id})


func _render_transcript(entries) -> void:
	if typeof(entries) != TYPE_ARRAY or _view == null:
		return
	for e in entries:
		if typeof(e) != TYPE_DICTIONARY:
			continue
		var role := str(e.get("role", ""))
		var text := str(e.get("text", ""))
		if role == "user":
			_view.add_user_message(_escape_bbcode(text))
		elif role == "agent":
			_view.add_agent_message(text)
		else:
			_view.add_system(text)


# ---------------------------------------------------------------------------
# Стартовый экран, переключение сайтов и проверка "не тот сайт".
# ---------------------------------------------------------------------------

func _on_editor_script_changed(scr: Script) -> void:
	if _hl:
		_hl.on_editor_script_changed(scr)


func _show_start_ui() -> void:
	if _start_screen:
		_start_screen.visible = true
		_start_screen.show_home()
	if has_node("VBoxContainer"):
		$VBoxContainer.visible = false


func _enter_chat_ui() -> void:
	if _start_screen:
		_start_screen.visible = false
	if has_node("VBoxContainer"):
		$VBoxContainer.visible = true


func _apply_chatbar_texts() -> void:
	if _bar_btn_new:
		_bar_btn_new.tooltip_text = _t("tip_new")
	if _bar_btn_ren:
		_bar_btn_ren.tooltip_text = _t("tip_rename")
	if _bar_btn_del:
		_bar_btn_del.tooltip_text = _t("tip_delete")
	if _bar_btn_home:
		_bar_btn_home.text = _t("menu")
		_bar_btn_home.tooltip_text = _t("tip_menu")


func _on_language_changed() -> void:
	# Обновляем подписи панели сразу, без перезагрузки плагина.
	name = _t("dock_title")
	if send_button and not _is_network_busy:
		send_button.text = _t("send")
	if input_field:
		input_field.placeholder_text = _t("input_placeholder")
	if advanced_toggle_btn and advanced_box:
		advanced_toggle_btn.text = _t("advanced_hide") if advanced_box.visible else _t("advanced_show")
	if confirm_button:
		confirm_button.text = _t("allow")
	if reject_button:
		reject_button.text = _t("reject")
	if reinit_button:
		reinit_button.text = _t("reinit")
	if rollback_button:
		rollback_button.text = _t("rollback")
	if _log_errors_button:
		_log_errors_button.text = _t("log_errors")
	if _api_export_button:
		_api_export_button.text = _t("api_export_btn")
	_apply_chatbar_texts()
	# Обновляем заголовок вкладки дока.
	var tabs := get_parent() as TabContainer
	if tabs:
		var ti: int = tabs.get_tab_idx_from_control(self)
		if ti >= 0:
			tabs.set_tab_title(ti, _t("dock_title"))


func _on_sites_tab_requested() -> void:
	# Пользователь нажал «Новый чат» на главном экране — сразу показываем загрузку, список
	# сайтов покажем только после ответа сервера (см. _on_chats_payload).
	_pending_view = "sites"
	if _start_screen and _start_screen.has_method("show_loading"):
		_start_screen.show_loading(_t("connecting"))
	_request_chats("sites", {})


func _on_chats_tab_requested() -> void:
	# Аналогично для кнопки «Загрузиться».
	_pending_view = "chats"
	if _start_screen and _start_screen.has_method("show_loading"):
		_start_screen.show_loading(_t("connecting"))
	_request_chats("list", {})


func _on_start_new_chat(site_id: String) -> void:
	if _start_screen and _start_screen.has_method("show_loading"):
		_start_screen.show_loading(_t("connecting"))
	_request_chats("new", {"site_id": site_id})


func _on_start_load_chat(chat_id: String) -> void:
	if _start_screen and _start_screen.has_method("show_loading"):
		_start_screen.show_loading(_t("connecting"))
	_request_chats("open", {"id": chat_id})


func _handle_site_mismatch(site_name: String, prompt: String) -> void:
	_pending_chat_prompt = prompt
	if _site_dialog == null:
		_site_dialog = ConfirmationDialog.new()
		_site_dialog.title = _t("site_mismatch_title")
		_site_dialog.confirmed.connect(_on_site_switch_yes)
		_site_dialog.canceled.connect(_on_site_switch_no)
		add_child(_site_dialog)
	_site_dialog.dialog_text = _t("site_mismatch_prefix") + ((" (" + site_name + ")") if site_name != "" else "") + "?"
	_site_dialog.ok_button_text = _t("site_yes")
	_site_dialog.get_cancel_button().text = _t("site_no")
	_site_dialog.popup_centered()


func _on_site_switch_yes() -> void:
	if _current_chat_id == "":
		_send_chat_raw(_pending_chat_prompt, true)
		return
	_resend_after_open = true
	_request_chats("open", {"id": _current_chat_id})


func _on_site_switch_no() -> void:
	if _view:
		_view.add_system(_t("stay_on_page"))
	_send_chat_raw(_pending_chat_prompt, true)


# ---------------------------------------------------------------------------
# Уведомления о загрузке страницы + автозапуск сервера.
# ---------------------------------------------------------------------------

func _begin_page_wait() -> void:
	if _view:
		_view.add_system(_t("page_wait"))
	_pagewait_left = 40
	if _pagewait_timer == null:
		_pagewait_timer = Timer.new()
		_pagewait_timer.wait_time = 1.0
		_pagewait_timer.one_shot = false
		add_child(_pagewait_timer)
		_pagewait_timer.timeout.connect(_on_pagewait_tick)
	_pagewait_timer.start()


func _on_pagewait_tick() -> void:
	if _pagewait_left <= 0:
		if _pagewait_timer: _pagewait_timer.stop()
		if _view:
			_view.add_system(_t("page_slow"))
		return
	_pagewait_left -= 1
	if _link and _link.is_inflight():
		return
	_request_chats("status", {})


func _on_browser_status(json: Dictionary) -> void:
	if _pagewait_timer == null or _pagewait_timer.is_stopped():
		return
	if bool(json.get("ready", false)):
		_pagewait_timer.stop()
		if _view:
			_view.add_success(_t("page_ready"))


func _notify(text: String, kind: String = "info") -> void:
	# Показываем статус и на стартовом экране, и в чате — пользователь всегда
	# видит, что агент работает, а не завис.
	if _start_screen and _start_screen.has_method("set_status"):
		_start_screen.set_status(text, kind)
	if kind == "status":
		return
	if kind == "error":
		_log_error(text)
	elif kind == "success":
		if _view: _view.add_success(text)
	else:
		if _view: _view.add_system(text)


func _on_link_show_loading(text: String) -> void:
	if _start_screen and _start_screen.has_method("show_loading"):
		_start_screen.show_loading(text)


func _on_link_hide_loading() -> void:
	if _start_screen and _start_screen.has_method("is_loading") and _start_screen.is_loading():
		_start_screen.hide_loading()


func _close_ghost_script_tab(target_path: String) -> void:
	# Откат удалил файл с диска, но вкладка в редакторе скриптов осталась —
	# сам Godot её не закрывает, а Ctrl+S в ней «воскресит» файл. Штатного API
	# закрыть вкладку нет, поэтому активируем её и шлём редактору штатный
	# шорткат «Close File» (Ctrl/Cmd+W). Если шорткат переназначен — подскажем
	# закрыть вручную (см. _after_ghost_close).
	if target_path.is_empty() or FileAccess.file_exists(target_path):
		return
	var se := EditorInterface.get_script_editor()
	if not se:
		return
	var dead: Script = null
	for scr in se.get_open_scripts():
		if scr and scr.resource_path == target_path:
			dead = scr
			break
	if dead == null:
		return
	_ghost_prev_script = se.get_current_script()
	if _ghost_prev_script == dead:
		_ghost_prev_script = null
	_ghost_close_path = target_path
	EditorInterface.edit_script(dead, -1, 0, false)
	var ev := InputEventKey.new()
	ev.keycode = KEY_W
	ev.command_or_control_autoremap = true
	ev.pressed = true
	Input.parse_input_event(ev)
	var up := InputEventKey.new()
	up.keycode = KEY_W
	up.command_or_control_autoremap = true
	up.pressed = false
	Input.parse_input_event(up)
	get_tree().create_timer(0.4).timeout.connect(_after_ghost_close)


func _after_ghost_close() -> void:
	var se := EditorInterface.get_script_editor()
	if se and _ghost_close_path != "":
		for scr in se.get_open_scripts():
			if scr and scr.resource_path == _ghost_close_path:
				# Шорткат не сработал — честно просим закрыть вкладку вручную.
				_notify(_t("ghost_tab_manual") % _ghost_close_path, "info")
				break
	if _ghost_prev_script:
		EditorInterface.edit_script(_ghost_prev_script, -1, 0, false)
	_ghost_prev_script = null
	_ghost_close_path = ""
