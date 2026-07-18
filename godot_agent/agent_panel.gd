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

var _pending_request_kind: String = "chat"
var _is_network_busy: bool = false

# Запоминаем детали последнего примененного WRITE-действия для сброса кэша
var _last_pending_action_type: String = ""
var _last_pending_action_path: String = ""
var _last_pending_action_dest: String = ""

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
	call_deferred("_request_chats", "list", {})
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
	_show_start_ui()
	call_deferred("_request_chats", "sites", {})
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
	# Живая трансляция: опрашиваем статус только пока идёт запрос.
	if busy:
		if _view:
			_view.reset_live()
		if _progress_timer and _progress_timer.is_stopped():
			_progress_timer.start()
	else:
		if _progress_timer:
			_progress_timer.stop()
		if _view:
			_view.hide_status()
		_progress_inflight = false


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


func _on_export_api_pressed() -> void:
	if _is_network_busy: return
	if pending_action_box and pending_action_box.visible:
		_log_error(_t("resolve_action_first"))
		return
	_export_api_to_server(false)


# silent = true — тихий автоматический запуск при старте плагина (не блокирует сеть для пользователя,
# просто показывает одно сообщение, если реально пришлось пересобирать).
func _export_api_to_server(silent: bool) -> void:
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
	var json = JSON.parse_string(response_str)

	if response_code == 200 and json != null:
		EditorInterface.get_resource_filesystem().scan()

		if json.has("site_mismatch") and bool(json.get("site_mismatch", false)):
			_handle_site_mismatch(str(json.get("site", "")), str(json.get("prompt", "")))
			return

		if kind == "init":
			chat_log.text += "\n[color=green]" + _t("reinit_done") + "[/color]\n"
			return

		if kind == "api_export":
			var cnt := int(json.get("classes_count", 0))
			chat_log.text += "[color=green]" + _t("api_export_done") % cnt + "[/color]\n"
			return

		if kind == "rollback_preview":
			if bool(json.get("found", false)):
				_show_rollback_dialog(str(json.get("description", "")))
			else:
				chat_log.text += "[color=gray]" + _t("rb_nothing") + "[/color]\n"
			return

		if kind == "rollback":
			var msg = str(json.get("message", _t("rollback_done")))
			chat_log.text += "\n[color=green]" + _t("success_prefix") + _escape_bbcode(msg) + "[/color]\n"
			# Синхронизируем откаченные файлы с открытыми вкладками. Иначе
			# вкладка показывает ДО-откатный текст, и Godot может позже
			# молча пересохранить его ПОВЕРХ результата отката.
			var paths = json.get("paths")
			if paths is Array:
				for p in paths:
					if FileAccess.file_exists(str(p)):
						_sync_open_script_with_disk(str(p))
					else:
						# Откат удалил созданный файл — закрываем его вкладку,
						# иначе Godot держит «призрака» и может пересохранить файл обратно.
						_close_ghost_script_tab(str(p))
			# Подсвечиваем восстановленный после отката блок (или гасим старое).
			var rb_path = json.get("changed_path")
			var rb_block = json.get("changed_block")
			if rb_path != null and rb_block != null and str(rb_block) != "":
				if _hl: _hl.apply(str(rb_path), str(rb_block))
			else:
				if _hl: _hl.clear()
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
		var err_msg = _t("srv_no_reply")
		if json and json.has("error") and json["error"] != null:
			err_msg = str(json["error"])
		# Сервер просит подтвердить откат повторным нажатием кнопки.
		if json != null and json.get("needs_force") == true:
			_rollback_force_next = true
		_log_error((_t("srv_error") % str(response_code)) + err_msg)


func _log_error(msg: String) -> void:
	if _view:
		_view.flush()
	chat_log.text += "\n[color=red]" + _t("error_prefix") + msg + "[/color]\n"


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
# Красим не по номерам строк, а ПО СОДЕРЖИМОМУ блока: при любой правке
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
	# Статус — только состояние бота; сам текст стримится прямо в чат (в _view).
	_view.show_status(str(json.get("phase", _t("working"))), int(json.get("elapsed", 0)), int(json.get("chars", 0)))
	_view.feed_live_stream(str(json.get("stream", "")))


# ---------------------------------------------------------------------------
# Чаты: список, создание, выбор (открывает страницу в браузере),
# переименование, удаление. Сохранённый диалог восстанавливается в панели.
# ---------------------------------------------------------------------------

func _request_chats(kind: String, extra: Dictionary) -> void:
	if _link == null:
		return
	if _is_network_busy and kind != "list" and kind != "sites" and kind != "status":
		_log_error(_t("wait_current"))
		return
	_link.request(kind, extra)


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
		_enter_chat_ui()
		_begin_page_wait()
		if _resend_after_open:
			_resend_after_open = false
			_send_chat_raw(_pending_chat_prompt, true)
	elif kind == "new" and _view:
		_view.clear()
		_view.add_system(_t("chat_created"))
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
		_chat_select.add_item(str(c.get("title", _t("untitled"))), i)
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
	# «＋» в чате открывает выбор сайта (нейросети). Важно сначала
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
