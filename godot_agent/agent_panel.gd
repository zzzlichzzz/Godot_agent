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

# Кнопка выбора нейросети для открытого чата (под полем ввода) и ящик редких
# инструментов, который панель переносит в окно настроек — см.
# _on_settings_pressed и пояснение в plugin_universal.gd.
@onready var chat_model_btn: Button = $VBoxContainer/ChatModelBtn
@onready var advanced_box: VBoxContainer = $VBoxContainer/AdvancedBox
@onready var reinit_button: Button = $VBoxContainer/AdvancedBox/ReinitButton

const HOST = "127.0.0.1:5000"
# Файл токена проекта. Создаёт его agent_server_link.gd (там же вся логика),
# здесь путь нужен только как запасной способ прочитать токен, если узел
# ServerLink почему-то недоступен. Значение обязано совпадать с TOKEN_FILE
# в agent_server_link.gd.
const TOKEN_FILE := "user://godot_agent_token.txt"
const CHAT_URL = "http://" + HOST + "/chat"
const INIT_URL = "http://" + HOST + "/init"
const CONFIRM_URL = "http://" + HOST + "/chat/confirm_action"
const EDITOR_ACTION_RESULT_URL = "http://" + HOST + "/chat/editor_action/result"
const RUNTIME_RESULT_URL = "http://" + HOST + "/chat/runtime_inspect/result"
const RUNTIME_CHECK_RESULT_URL = "http://" + HOST + "/chat/runtime_check/result"
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
const LIVE_INPUT_URL = "http://" + HOST + "/chat/live_input"
const REFACTOR_FILE_PREVIEW_URL = "http://" + HOST + "/project/refactor/file/preview"
const REFACTOR_FILE_APPLY_URL = "http://" + HOST + "/project/refactor/file/apply"
const REFACTOR_NODE_PREVIEW_URL = "http://" + HOST + "/scene/refactor/node/preview"
const REFACTOR_NODE_APPLY_URL = "http://" + HOST + "/scene/refactor/node/apply"

var _pending_request_kind: String = "chat"
var _is_network_busy: bool = false
# Есть ли сейчас неотвеченное подтверждение. РАНЬШЕ этим флагом служило
# pending_action_box.visible, из-за чего старая панель кнопок рисовалась над
# строкой ввода одновременно с карточкой в чате. Теперь состояние живёт в
# переменной, а сама панель не показывается никогда (см. _set_pending_action).
var _pending_action_active: bool = false

# Plan-режим (цепочка действий): активен, когда пользователь подтвердил план
# и панель сама выполняет шаги через PLAN_STEP_URL по одному.
var _plan_active: bool = false
var _plan_chain_id: String = ""
var _plan_total: int = 0
var _plan_index: int = 0
var _plan_stop_button: Button = null
var _stop_button: Button = null
var _plan_rollback_chain_id: String = ""
var _plan_rollback_force_next: bool = false

# Визуальная карточка-чеклист активного плана (в чате).
var _active_plan_card: PlanChecklistCard = null

# Запоминаем детали последнего примененного WRITE-действия для сброса кэша
var _last_pending_action_type: String = ""
var _last_pending_action_path: String = ""
var _last_pending_action_dest: String = ""
var _last_pending_action_paths: PackedStringArray = PackedStringArray()
var _editor_plugin: EditorPlugin = null
var _scene_executor = null
var _pending_scene_action: Dictionary = {}
var _pending_scene_expected_hash: String = ""
var _pending_scene_semantic_hash: String = ""
var _pending_scene_finalize_body: Dictionary = {}
var _scene_finalize_retries: int = 0
var _scene_finalize_retrying: bool = false
var _project_settings_executor = null
var _pending_project_settings_action: Dictionary = {}
var _pending_project_settings_expected_hash: String = ""
var _pending_project_settings_semantic_hash: String = ""
var _pending_project_settings_finalize_body: Dictionary = {}
var _project_settings_finalize_retries: int = 0
var _project_settings_finalize_retrying: bool = false
var _resource_executor = null
var _pending_resource_action: Dictionary = {}
var _pending_resource_expected_hash: String = ""
var _pending_resource_semantic_hash: String = ""
var _pending_resource_dependency_fingerprint: String = ""
var _pending_resource_finalize_body: Dictionary = {}
var _resource_finalize_retries: int = 0
var _resource_finalize_retrying: bool = false
var _runtime_debugger = null
var _runtime_status: Dictionary = {"enabled": false, "protocol": 1, "sessions": []}
var _pending_runtime_request: Dictionary = {}
var _runtime_timeout_timer: Timer = null
var _pending_runtime_check: Dictionary = {}
var _runtime_check_session_id: int = -1
var _runtime_check_run_id: String = ""
var _pending_runtime_check_result_body: Dictionary = {}
var _scenes_to_reopen: PackedStringArray = PackedStringArray()  # v49: сцены, закрытые перед записью

# Если сервер ответил, что для отката нужно подтверждение (файл менялся
# после действия агента) — следующее нажатие кнопки отката отправит force.
var _rollback_force_next: bool = false
# Адрес записи журнала для текущего отката (см. _on_message_rollback_requested).
# Пусто — откат «последнего изменения» из дополнительных настроек.
var _rollback_entry_id: String = ""
# Для какого именно адреса взведён force. Раньше флаг был общим, и повторное
# нажатие у ДРУГОГО сообщения молча откатывало с force, минуя подтверждение.
var _rollback_force_entry_id: String = ""

# Закрытие «вкладки-призрака» после отката, удалившего файл с диска.
var _ghost_close_path: String = ""
var _ghost_prev_script: Script = null

# Канал «Ошибки запуска игры»: кнопка создаётся кодом (без правки .tscn),
# а флаг означает, что текущее подтверждение — это отправка отчёта модели.
var _log_errors_button: Button = null
var _api_export_button: Button = null
var _safe_rename_button: Button = null
var _safe_rename_dialog: ConfirmationDialog = null
var _safe_rename_old_edit: LineEdit = null
var _safe_rename_new_edit: LineEdit = null
var _safe_rename_refs_check: CheckBox = null
var _safe_rename_addons_check: CheckBox = null
var _safe_rename_status_label: Label = null
var _safe_rename_file_dialog: FileDialog = null
var _safe_rename_prepared: Dictionary = {}
var _safe_node_rename_button: Button = null
var _safe_node_rename_dialog: ConfirmationDialog = null
var _safe_node_rename_scene_edit: LineEdit = null
var _safe_node_rename_node_edit: LineEdit = null
var _safe_node_rename_new_edit: LineEdit = null
var _safe_node_rename_addons_check: CheckBox = null
var _safe_node_rename_status_label: Label = null
var _safe_node_rename_scene_dialog: FileDialog = null
var _safe_node_rename_prepared: Dictionary = {}
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
var _pending_editor_context: Dictionary = {}
var _editor_context_script = null
var _site_resend_envelope: Dictionary = {}
var _chat_navigation_generation: int = 0
var _chat_drafts: Dictionary = {}
var _guard_timer: Timer = null       # таймер-охранник кнопок (вместо await — переживает перезагрузку скрипта)
var _guard_until_msec: int = 0        # до какого момента кнопки подтверждения заблокированы


# Живая трансляция: пока идёт запрос, отдельный HTTPRequest раз в секунду
# опрашивает /chat/progress и показывает статус + хвост ответа модели.
var _progress_http: HTTPRequest = null

# v88.11: живой ввод — текст из поля панели зеркалируется в поле ввода сайта
# по мере набора (тротлинг-таймер + отдельный HTTPRequest, настройка в
# «Расширенных»; сервер вставляет текст без отправки).
const LIVE_INPUT_SETTING_FILE := "user://godot_agent_live_input.txt"
var _live_http: HTTPRequest = null
var _live_timer: Timer = null
var _live_toggle: CheckBox = null
var _live_enabled: bool = true
var _live_dirty: bool = false
var _live_inflight: bool = false
var _live_seq: int = 0
var _live_last_sent: String = ""
var _live_force_send: bool = false
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
var _chat_select: OptionButton = null
var _rename_edit: LineEdit = null  # inline-правка названия в строке чатов
var _current_chat_id: String = ""
# Модель ОТКРЫТОГО чата по ключу или "" — если открыт браузерный чат либо не
# открыт никакой. Нужна ровно для одного: показать на экране настроек кнопку
# «продолжить открытый чат на этой модели» и не показывать её там, где менять
# нечего. Отдельное поле, а не чтение записи чата: панель и так получает model в
# ответах /chats/open, /chats/new и /chats/model.
var _api_chat_model: String = ""
# Подпись открытого чата «провайдер · модель» — её присылает сервер готовой
# (site в ответах /chats/open, /chats/new, /chats/model; это же site_name записи
# чата). Панель её НЕ склеивает сама: имя провайдера знает только сервер, и
# вторая сборка той же строки разошлась бы с подписью чата в списке.
var _api_chat_site: String = ""
# Ждём ответ со списком провайдеров, чтобы открыть окно выбора нейросети.
var _chat_model_pick_wanted: bool = false
var _suppress_chat_select: bool = false

# v57: экспериментальные настройки (mini-lich) — кнопка ⛙ в панели чатов.
var _bar_btn_settings: Button = null
var _settings_dialog: AcceptDialog = null
var _settings_exp_header: Label = null
# Заголовок раздела редких инструментов в том же окне («Дополнительно»).
var _settings_adv_header: Label = null
var _minilich_check: CheckBox = null
var _minilich_status_label: Label = null
var _minilich_set_pending: bool = false  # true пока ответ на minilich_set не пришёл — не даём устаревшему minilich_status затирать галочку
# v58: кнопка «Обучение модели» + живая консоль прогресса обучения.
var _minilich_train_check: CheckBox = null
var _minilich_train_warn: Label = null
var _minilich_repos_edit: LineEdit = null
var _minilich_github_btn: Button = null
var _minilich_github_label: Label = null


func set_editor_plugin(plugin: EditorPlugin) -> void:
	_editor_plugin = plugin
	var executor_path: String = get_script().resource_path.get_base_dir() + "/agent_scene_executor.gd"
	if FileAccess.file_exists(executor_path):
		var executor_script = load(executor_path)
		if executor_script:
			_scene_executor = executor_script.new()
			_scene_executor.configure(plugin)
	var settings_executor_path: String = get_script().resource_path.get_base_dir() + "/agent_project_settings_executor.gd"
	if FileAccess.file_exists(settings_executor_path):
		var settings_executor_script = load(settings_executor_path)
		if settings_executor_script:
			_project_settings_executor = settings_executor_script.new()
			_project_settings_executor.configure(plugin)
	var resource_executor_path: String = get_script().resource_path.get_base_dir() + "/agent_resource_executor.gd"
	if FileAccess.file_exists(resource_executor_path):
		var resource_executor_script = load(resource_executor_path)
		if resource_executor_script:
			_resource_executor = resource_executor_script.new()
			_resource_executor.configure(plugin)


func set_runtime_debugger(debugger) -> void:
	_runtime_debugger = debugger
	if _runtime_debugger == null:
		return
	_runtime_status = _runtime_debugger.get_status()
	_runtime_debugger.status_changed.connect(_on_runtime_status_changed)
	_runtime_debugger.inspect_completed.connect(_on_runtime_inspect_completed)
	_runtime_debugger.check_completed.connect(_on_runtime_check_completed)
	_runtime_timeout_timer = Timer.new()
	_runtime_timeout_timer.one_shot = true
	add_child(_runtime_timeout_timer)
	_runtime_timeout_timer.timeout.connect(_on_runtime_inspect_timeout)


func _on_runtime_status_changed(status: Dictionary) -> void:
	_runtime_status = status.duplicate(true)


func _start_runtime_inspect(envelope: Dictionary) -> void:
	_pending_runtime_request = (envelope.get("runtime_request", {}) as Dictionary).duplicate(true)
	var result := {"ok": false, "status": "bridge_unavailable"}
	if _runtime_debugger:
		result = _runtime_debugger.inspect(_pending_runtime_request)
	if not bool(result.get("ok", false)):
		_send_runtime_result(str(result.get("status", "bridge_unavailable")), {})
		return
	_runtime_timeout_timer.start(maxf(0.1, float(_pending_runtime_request.get("timeout_ms", 3000)) / 1000.0))
	_view.add_system("Получаю read-only снимок запущенной игры...")


func _on_runtime_inspect_completed(result: Dictionary) -> void:
	if _pending_runtime_request.is_empty():
		return
	if str(result.get("request_id", "")) != str(_pending_runtime_request.get("request_id", "")):
		return
	if _runtime_timeout_timer:
		_runtime_timeout_timer.stop()
	_send_runtime_result(str(result.get("status", "protocol_error")), result.get("snapshot", {}))


func _on_runtime_inspect_timeout() -> void:
	if not _pending_runtime_check.is_empty():
		if _runtime_debugger:
			_runtime_debugger.cancel_pending("timeout")
		return
	if _runtime_debugger:
		_runtime_debugger.cancel_pending("timeout")


func _send_runtime_result(status: String, snapshot) -> void:
	if _pending_runtime_request.is_empty():
		return
	var body := {
		"request_id": str(_pending_runtime_request.get("request_id", "")),
		"result_token": str(_pending_runtime_request.get("result_token", "")),
		"session_id": int(_pending_runtime_request.get("session_id", -1)),
		"run_id": str(_pending_runtime_request.get("run_id", "")),
		"status": status,
		"snapshot": snapshot if snapshot is Dictionary else {},
	}
	_pending_request_kind = "runtime_result"
	_set_ui_busy(true)
	var err := http_request.request(RUNTIME_RESULT_URL, _json_headers(), HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error("Не удалось передать runtime snapshot серверу")
		_pending_runtime_request = {}
		if _runtime_timeout_timer:
			_runtime_timeout_timer.stop()
		_set_ui_busy(false)


func _start_runtime_check(envelope: Dictionary) -> void:
	_pending_runtime_check = (envelope.get("runtime_check_request", {}) as Dictionary).duplicate(true)
	if _pending_runtime_check.is_empty():
		return
	_runtime_check_session_id = -1
	_runtime_check_run_id = ""
	# Godot 4.6.1 exposes neither editor-run PIDs nor a debugger-session remote
	# PID. A sole/new session, scene name or bridge-reported PID is not proof
	# that play_custom_scene launched it. Refuse before launching or sending input.
	_view.add_system("run_check unavailable: Godot 4.6.1 cannot prove ownership of the launched debugger session. No scene was launched or stopped.")
	_send_runtime_check_result("bridge_unavailable", {})


func _exit_tree() -> void:
	if not _pending_runtime_check.is_empty():
		if _runtime_debugger:
			_runtime_debugger.cancel_pending("cancelled")


func _execute_bound_runtime_check(_envelope: Dictionary) -> void:
	# A server bind response cannot establish local process ownership either.
	_send_runtime_check_result("bridge_unavailable", {})


func _on_runtime_check_completed(result: Dictionary) -> void:
	if _pending_runtime_check.is_empty():
		return
	if str(result.get("request_id", "")) != str(_pending_runtime_check.get("request_id", "")):
		return
	if _runtime_timeout_timer:
		_runtime_timeout_timer.stop()
	_send_runtime_check_result(str(result.get("status", "protocol_error")), result.get("result", {}))


func _send_runtime_check_result(status: String, result_value) -> void:
	if _pending_runtime_check.is_empty():
		return
	_pending_runtime_check_result_body = {
		"request_id": str(_pending_runtime_check.get("request_id", "")),
		"result_token": str(_pending_runtime_check.get("result_token", "")),
		"session_id": _runtime_check_session_id,
		"run_id": _runtime_check_run_id,
		"status": status,
		"result": result_value if result_value is Dictionary else {},
	}
	_send_pending_runtime_check_result()


func _send_pending_runtime_check_result() -> void:
	if _pending_runtime_check_result_body.is_empty() or _is_network_busy:
		return
	_pending_request_kind = "runtime_check_result"
	_set_ui_busy(true)
	var error := http_request.request(RUNTIME_CHECK_RESULT_URL, _json_headers(), HTTPClient.METHOD_POST,
		JSON.stringify(_pending_runtime_check_result_body))
	if error != OK:
		_set_ui_busy(false)
		_log_error("Не удалось передать результат локальной игровой проверки серверу")


func _clear_runtime_check_state() -> void:
	_pending_runtime_check = {}
	_pending_runtime_check_result_body = {}
	_runtime_check_session_id = -1
	_runtime_check_run_id = ""
	if _runtime_timeout_timer:
		_runtime_timeout_timer.stop()


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


func _json_headers() -> PackedStringArray:
	# Заголовки для всех прямых запросов панели к серверу: Content-Type плюс
	# токен проекта (см. server_auth.py).
	#
	# Токен берётся у УЗЛА ServerLink, а не у загруженного скрипта: у объекта
	# GDScript метод has_method() не даёт надёжного ответа про пользовательские
	# static func, и молчаливое «нет» означало бы запросы без токена — сервер
	# после привязки отклонял бы их все, и плагин выглядел бы сломанным целиком.
	# У экземпляра узла has_method() работает однозначно.
	#
	# Запасной путь — прочитать файл токена напрямую. Он НЕ создаёт файл: если
	# токена ещё нет, значит сервер к нему и не привязан, и запрос пройдёт.
	var token := ""
	if _link != null and _link.has_method("project_token"):
		token = str(_link.project_token())
	elif FileAccess.file_exists(TOKEN_FILE):
		var f := FileAccess.open(TOKEN_FILE, FileAccess.READ)
		if f:
			token = f.get_as_text().strip_edges()
			f.close()
	if token == "":
		return PackedStringArray(["Content-Type: application/json"])
	return PackedStringArray([
		"Content-Type: application/json",
		"X-Agent-Token: " + token,
	])


var _theme_script = null


func _T():
	# Единый модуль оформления (цвета/иконки/стили) — agent_theme.gd.
	if _theme_script == null:
		var sc := get_script() as Script
		if sc:
			var p := sc.resource_path.get_base_dir() + "/agent_theme.gd"
			if FileAccess.file_exists(p):
				_theme_script = load(p)
	return _theme_script


func _apply_panel_theme() -> void:
	# Панель собирается кодом в plugin_universal.gd (agent_panel.tscn не
	# используется — см. комментарий там), поэтому оформление навешивается
	# здесь: так оно применяется при любом способе сборки дерева.
	var T = _T()
	if T == null:
		return

	# Поле ввода и кнопка отправки.
	T.style_input(input_field)
	if send_button:
		T.style_button(send_button, "accent", false)
		send_button.icon = T.icon(&"ArrowRight")

	# Кнопка выбора нейросети и инструменты из «Дополнительно».
	if chat_model_btn:
		# Тот же вид, что у кнопки провайдера на экране настроек по ключу: это
		# одно и то же действие, открывающее одно и то же окно.
		T.style_button(chat_model_btn, "neutral", false)
		chat_model_btn.icon = T.first_icon(["GuiDropdown", "GuiOptionArrow", "Tools"])
	if reinit_button:
		T.style_button(reinit_button, "neutral")
		reinit_button.icon = T.icon(&"Reload")
	if _log_errors_button:
		T.style_button(_log_errors_button, "neutral")
		_log_errors_button.icon = T.first_icon(["StatusError", "Debug"])
	if _api_export_button:
		T.style_button(_api_export_button, "neutral")
		_api_export_button.icon = T.first_icon(["Script", "File"])
	if _safe_rename_button:
		T.style_button(_safe_rename_button, "neutral")
		_safe_rename_button.icon = T.first_icon(["Rename", "Edit", "ActionCopy"])
	if _safe_node_rename_button:
		T.style_button(_safe_node_rename_button, "neutral")
		_safe_node_rename_button.icon = T.first_icon(["Rename", "Edit", "Node"])
	if _plan_stop_button:
		T.style_button(_plan_stop_button, "error")
		_plan_stop_button.icon = T.first_icon(["Stop", "Pause"])

	# Строка чатов: иконки редактора вместо эмодзи-символов.
	if _bar_btn_new:
		T.style_icon_button(_bar_btn_new, ["Add"], "＋", "success")
	if _bar_btn_ren:
		T.style_icon_button(_bar_btn_ren, ["Rename", "Edit"], "✏")
	if _bar_btn_del:
		T.style_icon_button(_bar_btn_del, ["Remove"], "🗑", "error")
	if _bar_btn_home:
		T.style_button(_bar_btn_home, "neutral")
		_bar_btn_home.icon = T.first_icon(["Home", "GuiTabMenuHl", "ArrowLeft"])
	if _bar_btn_settings:
		T.style_icon_button(_bar_btn_settings, ["Tools", "GDScript"], "⚙")


func _ready() -> void:
	_ensure_script_autoreload_setting()
	# ChatLog остаётся в дереве (его прячет agent_chat_view.setup), но больше
	# ничего в него не пишется: все сообщения идут карточками через _view.
	chat_log.selection_enabled = true
	chat_log.context_menu_enabled = true
	chat_log.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	chat_log.scroll_following = true
	if pending_action_box:
		pending_action_box.visible = false
	# Подтверждения показываются ТОЛЬКО карточкой в чате. Старая панель
	# PendingActionBox остаётся в дереве (её кнопки — приёмники сигналов и
	# охранник _guard_confirm_buttons), но больше никогда не показывается:
	# состояние «есть неотвеченное действие» держит _pending_action_active.
	if action_label:
		action_label.visible = false
		# Надпись из .tscn русская. Панель эту строку никогда не показывает
		# (подтверждения идут карточкой в чате), но держать в дереве русский
		# текст при английском языке нельзя: узел живой, и любая будущая правка,
		# которая снова его покажет, покажет и русское. Ставим из словаря сразу.
		action_label.text = _t("pending_default")
	if confirm_button:
		confirm_button.visible = false
	if reject_button:
		reject_button.visible = false
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
	if chat_model_btn and not chat_model_btn.pressed.is_connected(_on_chat_model_pressed):
		chat_model_btn.pressed.connect(_on_chat_model_pressed)
	if advanced_box and advanced_box.get_parent() == $VBoxContainer:
		# Ящик редких инструментов не показывается в чате никогда: панель
		# переносит его в окно настроек при первом открытии настроек. До того он
		# просто лежит скрытым — кнопки в нём создаются и подключаются здесь.
		#
		# Проверка родителя обязательна: _ready() выполняется заново после
		# перезагрузки скрипта аддона, а ящик к этому моменту может уже стоять в
		# окне настроек — и тогда «спрятать» означало бы стереть весь раздел из
		# настроек до перезапуска редактора.
		advanced_box.visible = false
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
	if advanced_box and _safe_rename_button == null:
		_safe_rename_button = Button.new()
		_safe_rename_button.text = _t("safe_rename_btn")
		advanced_box.add_child(_safe_rename_button)
		_safe_rename_button.pressed.connect(_on_safe_rename_pressed)
	if advanced_box and _safe_node_rename_button == null:
		_safe_node_rename_button = Button.new()
		_safe_node_rename_button.text = _t("safe_node_rename_btn")
		advanced_box.add_child(_safe_node_rename_button)
		_safe_node_rename_button.pressed.connect(_on_safe_node_rename_pressed)
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
	# v88.11: живой ввод — зеркалирование текста в браузер по мере набора
	_live_enabled = _load_live_input_setting()
	if _live_timer == null:
		_live_timer = Timer.new()
		_live_timer.wait_time = 0.35
		_live_timer.one_shot = false
		add_child(_live_timer)
		_live_timer.timeout.connect(_on_live_input_tick)
		_live_timer.start()
	if _live_http == null:
		_live_http = HTTPRequest.new()
		_live_http.timeout = 5.0
		add_child(_live_http)
		_live_http.request_completed.connect(_on_live_input_response)
	if input_field and not input_field.text_changed.is_connected(_on_live_input_changed):
		input_field.text_changed.connect(_on_live_input_changed)
	if advanced_box and _live_toggle == null:
		_live_toggle = CheckBox.new()
		_live_toggle.text = _t("live_input_toggle")
		_live_toggle.tooltip_text = _t("live_input_tip")
		_live_toggle.button_pressed = _live_enabled
		advanced_box.add_child(_live_toggle)
		_live_toggle.toggled.connect(_on_live_input_toggled)
	if has_node("ChatView"):
		_view = get_node("ChatView")
	else:
		var view_script = load(get_script().resource_path.get_base_dir() + "/agent_chat_view.gd")
		_view = view_script.new()
		_view.name = "ChatView"
		add_child(_view)
	_view.setup($VBoxContainer)
	# Откат доступен прямо из карточки ответа агента: карточка шлёт сигнал,
	# а вопрос и запрос на сервер обрабатываются здесь.
	if not _view.message_rollback_requested.is_connected(_on_message_rollback_requested):
		_view.message_rollback_requested.connect(_on_message_rollback_requested)
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
		# v63: bez etogo dlinnoe nazvanie chata rastyagivaet svoyo minimalnoe
		# shirinu po vsey svoey dline, i kogda panel uzhe tsentra ekrana (dok v bok),
		# knopki sprava vytesnyayutsya za granitsu. Obrezaem tekst ellipsisom i dayom
		# emu neboljshoy garantirovanniy minimum vmesto estestvennoy shiriny teksta.
		if _chat_select is OptionButton:
			_chat_select.clip_text = true
			_chat_select.custom_minimum_size.x = 40.0
		if not _chat_select.item_selected.is_connected(_on_chat_selected):
			_chat_select.item_selected.connect(_on_chat_selected)
		if bar_old.get_child_count() >= 5:
			_bar_btn_new = bar_old.get_child(1) as Button
			_bar_btn_ren = bar_old.get_child(2) as Button
			_bar_btn_del = bar_old.get_child(3) as Button
			_bar_btn_home = bar_old.get_child(4) as Button
		if bar_old.has_node("MiniLichSettingsBtn"):
			_bar_btn_settings = bar_old.get_node("MiniLichSettingsBtn") as Button
			if not _bar_btn_settings.pressed.is_connected(_on_settings_pressed):
				_bar_btn_settings.pressed.connect(_on_settings_pressed)
		else:
			_bar_btn_settings = Button.new()
			_bar_btn_settings.name = "MiniLichSettingsBtn"
			_bar_btn_settings.text = "⚙"
			_bar_btn_settings.pressed.connect(_on_settings_pressed)
			bar_old.add_child(_bar_btn_settings)
		_apply_chatbar_texts()
	else:
		var bar := HBoxContainer.new()
		bar.name = "ChatsBar"
		_chat_select = OptionButton.new()
		_chat_select.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		# v63: obrezaem dlinnye nazvaniya chata ellipsisom, chtoby knopki
		# spravsa za krayem paneli pri uzkoy panele ne vytesnyalisj.
		_chat_select.clip_text = true
		_chat_select.custom_minimum_size.x = 40.0
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
		_bar_btn_settings = Button.new()
		_bar_btn_settings.name = "MiniLichSettingsBtn"
		_bar_btn_settings.text = "⚙"
		_bar_btn_settings.pressed.connect(_on_settings_pressed)
		bar.add_child(_bar_btn_settings)
		_apply_chatbar_texts()
		$VBoxContainer.add_child(bar)
		$VBoxContainer.move_child(bar, 0)
	# Фоновое авто-обновление списка чатов при открытии панели — БЕЗ автозапуска
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
		_start_screen.delete_chat_requested.connect(_on_start_delete_chat)
		_start_screen.sites_tab_requested.connect(_on_sites_tab_requested)
		_start_screen.chats_tab_requested.connect(_on_chats_tab_requested)
		if _start_screen.has_signal("language_changed"):
			_start_screen.language_changed.connect(_on_language_changed)
		if _start_screen.has_signal("open_server_requested"):
			_start_screen.open_server_requested.connect(_on_open_server_folder_pressed)
		if _start_screen.has_signal("settings_requested"):
			_start_screen.settings_requested.connect(_on_settings_pressed)
		# Работа по ключу API. has_signal — на случай, если панель и стартовый
		# экран оказались из разных версий аддона после обновления.
		if _start_screen.has_signal("api_tab_requested"):
			_start_screen.api_tab_requested.connect(_on_api_tab_requested)
			_start_screen.api_settings_save_requested.connect(_on_api_settings_save)
			_start_screen.api_models_refresh_requested.connect(_on_api_models_refresh)
			_start_screen.api_test_requested.connect(_on_api_test_requested)
			_start_screen.new_api_chat_requested.connect(_on_start_new_api_chat)
		# Отдельной проверкой, а не рядом выше: сигнал смены модели у открытого
		# чата добавлен позже, и панель могла оказаться от более новой версии
		# аддона, чем сохранённая сцена — обращение к несуществующему сигналу
		# оборвало бы всё подключение и экран остался бы мёртвым.
		if _start_screen.has_signal("api_chat_model_requested"):
			_start_screen.api_chat_model_requested.connect(_on_api_chat_model)
		# Отдельной проверкой, а не внутри блока выше: сигнал появился позже
		# остальных, и экран прошлой версии его не объявляет — обращение к нему
		# оборвало бы подключение и всех предыдущих сигналов вместе с ним.
		if _start_screen.has_signal("api_models_scan_requested"):
			_start_screen.api_models_scan_requested.connect(_on_api_models_scan)
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
	# Оформление — последним: к этому моменту созданы и кнопки строки чатов,
	# и кнопки редких инструментов, иначе часть из них осталась бы без стиля.
	_apply_panel_theme()
	_refresh_chat_model_btn()


func _set_pending_action(active: bool, description: String = "") -> void:
	# Единая точка вкл/выкл состояния «ждём ответа на подтверждение».
	# Саму панель не показываем — её роль выполняет карточка в чате.
	_pending_action_active = active
	if action_label and description != "":
		action_label.text = description
	if pending_action_box:
		pending_action_box.visible = false


func _has_pending_action() -> bool:
	return (_pending_action_active or not _pending_scene_finalize_body.is_empty()
		or not _pending_project_settings_finalize_body.is_empty()
		or not _pending_resource_finalize_body.is_empty()
		or not _pending_runtime_request.is_empty() or not _pending_runtime_check.is_empty()
		or not _pending_runtime_check_result_body.is_empty())


func _clear_pending_action_state() -> void:
	# Подтверждение относится только к чату, в котором оно было создано.
	_set_pending_action(false)
	_last_pending_action_type = ""
	_last_pending_action_path = ""
	_last_pending_action_dest = ""
	_last_pending_action_paths = PackedStringArray()
	_pending_scene_action = {}
	_pending_scene_expected_hash = ""
	_pending_scene_semantic_hash = ""
	_pending_project_settings_action = {}
	_pending_project_settings_expected_hash = ""
	_pending_project_settings_semantic_hash = ""
	_pending_resource_action = {}
	_pending_resource_expected_hash = ""
	_pending_resource_semantic_hash = ""
	_pending_resource_dependency_fingerprint = ""
	# Finalize envelope очищается только после терминального ответа сервера.
	# Обычная смена/очистка pending action не должна терять уже записанный ресурс.
	_pending_log_send = false


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
		_show_stop_button()
	else:
		if _progress_timer:
			_progress_timer.stop()
		if _view:
			_view.hide_status()
		_progress_inflight = false
		_hide_stop_button()
		if input_field and input_field.is_visible_in_tree():
			input_field.call_deferred("grab_focus")
			input_field.queue_redraw()


func _clear_chat_input(reset_live: bool = true) -> void:
	if input_field == null:
		return
	input_field.clear()
	input_field.set_caret_line(0)
	input_field.set_caret_column(0)
	if input_field.has_method("deselect"):
		input_field.call("deselect")
	input_field.scroll_vertical = 0
	input_field.scroll_horizontal = 0
	input_field.queue_redraw()
	if reset_live:
		_live_seq += 1
		_live_force_send = true
		_live_dirty = true
	if not _is_network_busy and input_field.is_visible_in_tree():
		input_field.call_deferred("grab_focus")


func _restore_chat_draft() -> void:
	if input_field == null or _pending_chat_prompt.is_empty():
		return
	if input_field.text.is_empty():
		input_field.text = _pending_chat_prompt
		input_field.set_caret_line(max(0, input_field.get_line_count() - 1))
		input_field.set_caret_column(input_field.get_line(input_field.get_caret_line()).length())
		input_field.queue_redraw()
	_live_dirty = true
	input_field.call_deferred("grab_focus")


func _finish_chat_send() -> void:
	_pending_chat_prompt = ""
	_pending_editor_context = {}
	if _current_chat_id != "":
		_chat_drafts.erase(_current_chat_id)


func _switch_chat_draft(next_chat_id: String) -> void:
	if input_field == null or next_chat_id == _current_chat_id:
		return
	var previous_draft := input_field.text
	if previous_draft.is_empty() and not _pending_chat_prompt.is_empty():
		previous_draft = _pending_chat_prompt
	if _current_chat_id != "":
		if previous_draft.is_empty():
			_chat_drafts.erase(_current_chat_id)
		else:
			_chat_drafts[_current_chat_id] = previous_draft
	input_field.text = str(_chat_drafts.get(next_chat_id, ""))
	input_field.set_caret_line(max(0, input_field.get_line_count() - 1))
	input_field.set_caret_column(input_field.get_line(input_field.get_caret_line()).length())
	input_field.queue_redraw()
	_live_seq += 1
	_live_force_send = true
	_live_dirty = true


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
		# Текст и иконка были захардкожены по-русски и не переводились.
		var T = _T()
		if T:
			T.style_button(_stop_button, "error")
			_stop_button.icon = T.first_icon(["Stop", "Pause"])
	_stop_button.text = _t("stop_btn")
	_stop_button.tooltip_text = _t("stop_tip")
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
		_stop_button.text = _t("stopping")
	var req := HTTPRequest.new()
	add_child(req)
	req.request_completed.connect(func(_r, _rc, _h, _b): req.queue_free())
	var err = req.request(CHAT_STOP_URL, _json_headers(), HTTPClient.METHOD_POST, "{}")
	if err != OK:
		req.queue_free()
		if _stop_button:
			_stop_button.disabled = false
			_stop_button.text = _t("stop_btn")


func _refresh_chat_model_btn() -> void:
	# Подпись кнопки = нейросеть и провайдер ОТКРЫТОГО чата.
	if chat_model_btn == null:
		return
	# У браузерного чата модель выбирают на самой странице сервиса, и сменить её
	# отсюда нечем: сервер такой запрос честно отклоняет (/chats/model). Кнопки
	# там нет вовсе — предлагать действие, которое заведомо не сработает, хуже,
	# чем не предлагать его.
	chat_model_btn.visible = _api_chat_model != ""
	chat_model_btn.text = _api_chat_site if _api_chat_site != "" else _t("chat_model_pick")
	chat_model_btn.tooltip_text = _t("chat_model_pick_tip")


func _on_chat_model_pressed() -> void:
	# Выбор нейросети для ЭТОГО чата: то же окно, что и в настройках работы по
	# ключу. Своего списка моделей у чата нет намеренно — второй список стал бы
	# вторым источником правды о том, что доступно и у кого есть ключ.
	if _start_screen == null or not _start_screen.has_method("open_chat_provider_pick"):
		return
	# Список провайдеров, ключей и моделей живёт на СЕРВЕРЕ, и панель своего
	# представления о нём не держит (см. раздел «Работа по ключу API» ниже).
	# Поэтому спрашиваем его заново: за время переписки ключ мог исчерпаться, и
	# окно с прошлыми пометками предложило бы модель, которая уже не отвечает.
	# Само окно открываем в ответе (_on_api_payload) — открытое до ответа, оно
	# нарисовалось бы пустым.
	_chat_model_pick_wanted = true
	chat_model_btn.text = _t("chat_model_loading")
	_request_chats("api_providers", {})


func _on_input_field_gui_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_ENTER and event.ctrl_pressed:
			_on_send_pressed()
			accept_event()


# --- v88.11: живой ввод — зеркалирование текста панели в поле сайта ---

func _on_live_input_changed() -> void:
	if _live_enabled:
		_live_dirty = true


func _on_live_input_tick() -> void:
	if not _live_enabled or not _live_dirty or _live_inflight: return
	if _is_network_busy: return  # идёт обмен — конвейер сам вставит финальный промпт
	if input_field == null or _live_http == null: return
	var txt: String = input_field.text
	if txt == _live_last_sent and not _live_force_send:
		_live_dirty = false
		return
	_live_seq += 1
	var body = {"text": txt, "seq": _live_seq}
	_live_http.set_http_proxy("", 0)
	var err = _live_http.request(LIVE_INPUT_URL, _json_headers(), HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		return  # сервер занят/недоступен — молча попробуем на следующем тике
	_live_inflight = true
	_live_last_sent = txt
	_live_force_send = false
	_live_dirty = false


func _on_live_input_response(_result: int, _code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
	# Ошибки молча игнорируем: зеркалирование — best effort, отправке оно
	# не мешает (конвейер v88.4 сам вставляет и сверяет финальный промпт).
	_live_inflight = false


func _on_live_input_toggled(pressed: bool) -> void:
	_live_enabled = pressed
	_save_live_input_setting(pressed)
	if pressed:
		_live_dirty = true  # сразу дослать текущий текст поля


func _load_live_input_setting() -> bool:
	if not FileAccess.file_exists(LIVE_INPUT_SETTING_FILE):
		return true  # по умолчанию включено
	var f = FileAccess.open(LIVE_INPUT_SETTING_FILE, FileAccess.READ)
	if f == null:
		return true
	return f.get_as_text().strip_edges() != "0"


func _save_live_input_setting(enabled: bool) -> void:
	var f = FileAccess.open(LIVE_INPUT_SETTING_FILE, FileAccess.WRITE)
	if f == null:
		return
	f.store_string("1" if enabled else "0")


func _on_reinit_pressed() -> void:
	if _is_network_busy: return
	_view.add_system(_t("tree_refresh"))
	_rollback_force_next = false
	var project_root = ProjectSettings.globalize_path("res://")
	var headers = _json_headers()
	var body = {"project_root": project_root, "user_data_dir": OS.get_user_data_dir(), "addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()), "godot_version": Engine.get_version_info().get("string", ""), "godot_executable": OS.get_executable_path(), "runtime_status": _runtime_status, "reinit": true}
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "init"
	_set_ui_busy(true)
	http_request.request(INIT_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))


func _on_send_pressed() -> void:
	if _is_network_busy: return
	if _has_pending_action():
		_log_error(_t("resolve_action_first"))
		return
	var user_text := input_field.text
	if user_text.strip_edges().is_empty(): return
	_clear_chat_input(true)
	_rollback_force_next = false
	_view.add_user_message(_escape_bbcode(user_text))
	_view.add_system(_t("analyzing"))
	_send_chat_raw(user_text, false)


func _send_chat_raw(prompt: String, ignore_mismatch: bool) -> void:
	_pending_chat_prompt = prompt
	if not ignore_mismatch or _pending_editor_context.is_empty():
		_pending_editor_context = _capture_editor_context()
	var project_root = ProjectSettings.globalize_path("res://")
	var headers = _json_headers()
	var body = {
		"prompt": prompt,
		"chat_id": _current_chat_id,
		"project_root": project_root,
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()),
		"godot_executable": OS.get_executable_path(),
		"runtime_status": _runtime_status
	}
	if not _pending_editor_context.is_empty():
		body["editor_context"] = _pending_editor_context
	if ignore_mismatch:
		body["ignore_site_mismatch"] = true
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "chat"
	_set_ui_busy(true)
	var err = http_request.request(CHAT_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("err_send"))
		_set_ui_busy(false)
		_restore_chat_draft()


func _capture_editor_context() -> Dictionary:
	if _editor_context_script == null:
		var script_path: String = get_script().resource_path.get_base_dir() + "/agent_editor_context.gd"
		if FileAccess.file_exists(script_path):
			_editor_context_script = load(script_path)
	if _editor_context_script != null:
		var snapshot = _editor_context_script.capture()
		if snapshot is Dictionary:
			return snapshot
	return {}


func _on_confirm_pressed() -> void:
	_send_confirm_request(true)


func _on_reject_pressed() -> void:
	_send_confirm_request(false)


func _send_confirm_request(approved: bool) -> void:
	if _is_network_busy: return
	if approved and _last_pending_action_type in ["rename_symbol", "rename_file", "rename_node", "reparent_node", "delete_node", "transaction", "create_file", "patch_file", "move_file"]:
		var targets := _last_pending_action_paths.duplicate()
		for path in [_last_pending_action_path, _last_pending_action_dest]:
			if not str(path).is_empty() and not targets.has(str(path)):
				targets.append(str(path))
		var dirty_paths := _dirty_open_scripts(targets)
		if not dirty_paths.is_empty():
			_view.add_warning("Сначала сохраните изменённые вкладки: " + ", ".join(dirty_paths))
			return
	# Подтверждение отправки отчёта об ошибках запуска — отдельная ветка:
	# при отказе сервер вообще не трогаем (и браузер тоже).
	if _pending_log_send:
		_set_pending_action(false)
		_pending_log_send = false
		if not approved:
			_view.add_system(_t("errs_cancelled"))
			return
		_view.add_system(_t("errs_sending"))
		var log_headers = _json_headers()
		http_request.set_http_proxy("", 0)
		_pending_request_kind = "chat"
		_set_ui_busy(true)
		var log_err = http_request.request(SEND_LOG_URL, log_headers, HTTPClient.METHOD_POST, JSON.stringify({}))
		if log_err != OK:
			_log_error(_t("err_send_report"))
			_set_ui_busy(false)
		return
	if approved and _last_pending_action_type not in ["edit_scene", "create_scene", "rename_node", "reparent_node", "delete_node", "edit_project_settings", "edit_resource", "inspect_runtime", "run_check"]:
		var open_targets := _open_pending_scene_paths()
		if not open_targets.is_empty():
			_view.add_warning("Сохраните и закройте целевые сцены перед файловой операцией: " + ", ".join(open_targets))
			return
	_set_pending_action(false)
	var label = _t("approved_action") if approved else _t("rejected_action")
	_view.add_system(label + _t("waiting_reply"))
	var headers = _json_headers()
	var body = {"approved": approved}
	if approved and _last_pending_action_type in ["edit_scene", "create_scene"]:
		body["editor_semantic_hash"] = _pending_scene_semantic_hash
	elif approved and _last_pending_action_type == "edit_project_settings":
		body["editor_semantic_hash"] = _pending_project_settings_semantic_hash
	elif approved and _last_pending_action_type == "edit_resource":
		body["editor_semantic_hash"] = _pending_resource_semantic_hash
		body["dependency_fingerprint"] = _pending_resource_dependency_fingerprint
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "confirm"
	_set_ui_busy(true)
	var err = http_request.request(CONFIRM_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("err_send_confirm"))
		_set_ui_busy(false)
		_reopen_scenes_after_write()  # v49: запрос не ушёл — вернуть закрытые сцены


func _send_scene_result(execution: Dictionary, envelope: Dictionary) -> void:
	_pending_scene_finalize_body = {
		"action_id": str(envelope.get("action_id", "")),
		"execution_token": str(envelope.get("execution_token", "")),
		"success": bool(execution.get("ok", false)),
		"scene_hash": str(execution.get("scene_hash", "")),
		"target_written": bool(execution.get("target_written", false)),
		"staged_hash": str(execution.get("staged_hash", "")),
		"error_code": str(execution.get("code", "")),
		"error": str(execution.get("error", "")),
	}
	_scene_finalize_retries = 0
	_send_pending_scene_finalize()


func _send_pending_scene_finalize() -> void:
	if _pending_scene_finalize_body.is_empty():
		return
	if _is_network_busy:
		_schedule_scene_finalize_retry()
		return
	_pending_request_kind = "scene_finalize"
	_set_ui_busy(true)
	_scene_finalize_retries += 1
	var err := http_request.request(
		EDITOR_ACTION_RESULT_URL, _json_headers(), HTTPClient.METHOD_POST,
		JSON.stringify(_pending_scene_finalize_body))
	if err != OK:
		_set_ui_busy(false)
		_schedule_scene_finalize_retry()


func _schedule_scene_finalize_retry() -> void:
	if _scene_finalize_retrying or _pending_scene_finalize_body.is_empty():
		return
	_scene_finalize_retrying = true
	await get_tree().create_timer(float(mini(_scene_finalize_retries + 1, 5))).timeout
	_scene_finalize_retrying = false
	if not _is_network_busy:
		_send_pending_scene_finalize()
	else:
		_schedule_scene_finalize_retry()


func _prepare_scene_action(pending: Dictionary, prepare_data: Dictionary) -> Dictionary:
	if _scene_executor == null:
		return {"ok": false, "error": "Исполнитель структурных сцен недоступен"}
	_pending_scene_action = pending.duplicate(true)
	_pending_scene_expected_hash = str(prepare_data.get("expected_scene_hash", ""))
	var result: Dictionary = _scene_executor.prepare(_pending_scene_action, _pending_scene_expected_hash)
	_pending_scene_semantic_hash = str(result.get("semantic_hash", "")) if bool(result.get("ok", false)) else ""
	return result


func _execute_scene_action(envelope: Dictionary) -> void:
	var execution: Dictionary
	if _scene_executor == null:
		execution = {"ok": false, "error": "Исполнитель структурных сцен недоступен", "scene_hash": ""}
	else:
		var action: Dictionary = envelope.get("editor_action", {}).duplicate(true)
		if str(action.get("action", "")) == "create_scene":
			action["_create_action_id"] = str(envelope.get("action_id", ""))
		if _pending_scene_semantic_hash != "":
			action["_expected_semantic_hash"] = _pending_scene_semantic_hash
		execution = _scene_executor.execute(action, str(envelope.get("expected_scene_hash", "")))
	_send_scene_result(execution, envelope)


func _prepare_project_settings_action(pending: Dictionary, prepare_data: Dictionary) -> Dictionary:
	if _project_settings_executor == null:
		return {"ok": false, "error": "Исполнитель настроек проекта недоступен"}
	_pending_project_settings_action = pending.duplicate(true)
	_pending_project_settings_expected_hash = str(prepare_data.get("expected_project_hash", ""))
	var result: Dictionary = _project_settings_executor.prepare(
		_pending_project_settings_action, _pending_project_settings_expected_hash)
	_pending_project_settings_semantic_hash = str(result.get("semantic_hash", "")) if bool(result.get("ok", false)) else ""
	return result


func _execute_project_settings_action(envelope: Dictionary) -> void:
	var execution: Dictionary
	if _project_settings_executor == null:
		execution = {"ok": false, "error": "Исполнитель настроек проекта недоступен", "project_hash": ""}
	else:
		var action: Dictionary = envelope.get("editor_action", {}).duplicate(true)
		if _pending_project_settings_semantic_hash != "":
			action["_expected_semantic_hash"] = _pending_project_settings_semantic_hash
		execution = _project_settings_executor.execute(
			action, str(envelope.get("expected_project_hash", "")))
	_pending_project_settings_finalize_body = {
		"action_id": str(envelope.get("action_id", "")),
		"execution_token": str(envelope.get("execution_token", "")),
		"editor_action_kind": "project_settings",
		"success": bool(execution.get("ok", false)),
		"project_hash": str(execution.get("project_hash", "")),
		"already_satisfied": bool(execution.get("already_satisfied", false)),
		"error_code": str(execution.get("code", "")),
		"error": str(execution.get("error", "")),
	}
	_project_settings_finalize_retries = 0
	_send_pending_project_settings_finalize()


func _send_pending_project_settings_finalize() -> void:
	if _pending_project_settings_finalize_body.is_empty():
		return
	if _is_network_busy:
		_schedule_project_settings_finalize_retry()
		return
	_pending_request_kind = "project_settings_finalize"
	_set_ui_busy(true)
	_project_settings_finalize_retries += 1
	var err := http_request.request(
		EDITOR_ACTION_RESULT_URL, _json_headers(), HTTPClient.METHOD_POST,
		JSON.stringify(_pending_project_settings_finalize_body))
	if err != OK:
		_set_ui_busy(false)
		_schedule_project_settings_finalize_retry()


func _schedule_project_settings_finalize_retry() -> void:
	if _project_settings_finalize_retrying or _pending_project_settings_finalize_body.is_empty():
		return
	_project_settings_finalize_retrying = true
	await get_tree().create_timer(float(mini(_project_settings_finalize_retries + 1, 5))).timeout
	_project_settings_finalize_retrying = false
	if not _is_network_busy:
		_send_pending_project_settings_finalize()
	else:
		_schedule_project_settings_finalize_retry()


func _prepare_resource_action(pending: Dictionary, prepare_data: Dictionary) -> Dictionary:
	if _resource_executor == null:
		return {"ok": false, "error": "Исполнитель ресурсов недоступен"}
	_pending_resource_action = pending.duplicate(true)
	_pending_resource_expected_hash = str(prepare_data.get("expected_resource_hash", ""))
	var result: Dictionary = _resource_executor.prepare(
		_pending_resource_action, _pending_resource_expected_hash)
	if bool(result.get("ok", false)):
		_pending_resource_semantic_hash = str(result.get("semantic_hash", ""))
		_pending_resource_dependency_fingerprint = str(result.get("dependency_fingerprint", ""))
	else:
		_pending_resource_semantic_hash = ""
		_pending_resource_dependency_fingerprint = ""
	return result


func _execute_resource_action(envelope: Dictionary) -> void:
	var execution: Dictionary
	if _resource_executor == null:
		execution = {"ok": false, "error": "Исполнитель ресурсов недоступен", "resource_hash": ""}
	else:
		var action: Dictionary = envelope.get("editor_action", {}).duplicate(true)
		action["_expected_semantic_hash"] = _pending_resource_semantic_hash
		action["_expected_dependency_fingerprint"] = str(
			envelope.get("expected_dependency_fingerprint", _pending_resource_dependency_fingerprint))
		execution = _resource_executor.execute(
			action, str(envelope.get("expected_resource_hash", "")))
	_pending_resource_finalize_body = {
		"action_id": str(envelope.get("action_id", "")),
		"execution_token": str(envelope.get("execution_token", "")),
		"editor_action_kind": "resource",
		"success": bool(execution.get("ok", false)),
		"resource_hash": str(execution.get("resource_hash", "")),
		"error_code": str(execution.get("code", "")),
		"error": str(execution.get("error", "")),
	}
	_resource_finalize_retries = 0
	_send_pending_resource_finalize()


func _send_pending_resource_finalize() -> void:
	if _pending_resource_finalize_body.is_empty():
		return
	if _is_network_busy:
		_schedule_resource_finalize_retry()
		return
	_pending_request_kind = "resource_finalize"
	_set_ui_busy(true)
	_resource_finalize_retries += 1
	var err := http_request.request(
		EDITOR_ACTION_RESULT_URL, _json_headers(), HTTPClient.METHOD_POST,
		JSON.stringify(_pending_resource_finalize_body))
	if err != OK:
		_set_ui_busy(false)
		_schedule_resource_finalize_retry()


func _schedule_resource_finalize_retry() -> void:
	if _resource_finalize_retrying or _pending_resource_finalize_body.is_empty():
		return
	_resource_finalize_retrying = true
	await get_tree().create_timer(float(mini(_resource_finalize_retries + 1, 5))).timeout
	_resource_finalize_retrying = false
	if not _is_network_busy:
		_send_pending_resource_finalize()
	else:
		_schedule_resource_finalize_retry()


func _start_plan_execution(total: int) -> void:
	_plan_active = true
	_plan_total = total
	_plan_index = 0
	# Карточка-чеклист плана прямо в чате (чистый визуал, логика не меняется).
	var step_descs := []
	for i in range(total):
		step_descs.append(_t("plan_step_n") % (i + 1))
	_active_plan_card = _view.add_plan_checklist(_t("plan_started") % total, step_descs)
	if _active_plan_card:
		# Кнопка «Пауза» на карточке = обычная остановка плана (та же логика).
		_active_plan_card.plan_paused.connect(_on_plan_stop_pressed)
	_show_plan_stop_button()
	_request_plan_step()


func _request_plan_step() -> void:
	if _is_network_busy: return
	var headers = _json_headers()
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
	if _active_plan_card:
		_active_plan_card.queue_free()
		_active_plan_card = null


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
	var headers = _json_headers()
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "plan_stop"
	_set_ui_busy(true)
	var err = http_request.request(PLAN_STOP_URL, headers, HTTPClient.METHOD_POST, "{}")
	if err != OK:
		_log_error(_t("err_plan_step"))
		_set_ui_busy(false)
		_end_plan_execution()


func _note_autoload_removed(json) -> void:
	# Откат мог оставить в project.godot висячую запись автозагрузки на файл,
	# которого больше нет (см. clean_dangling_autoloads на сервере) — сообщаем,
	# что она уже убрана, чтобы пользователь не искал причину ошибок автозагрузки сам.
	var removed = json.get("autoload_removed")
	if removed is Array and removed.size() > 0:
		_view.add_system(_t("autoload_cleaned") % ", ".join(removed))


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
	# Раньше здесь всплывал ConfirmationDialog поверх редактора. Теперь вопрос
	# показывается карточкой в чате — рядом с откатом, который его вызвал.
	if _view:
		_view.add_question_card(
			"reload_project",
			_t("reload_project_title"),
			_t("reload_project_text"),
			_t("reload_project_yes"),
			_t("reload_project_no"),
			func(): _on_reload_project_confirmed(),
			func(): pass
		)


func _on_reload_project_confirmed() -> void:
	_view.add_system(_t("reload_project_doing"))
	if _view: _view.flush()
	# true = перезапустить движок на том же проекте (Godot 4.3+); подхватывает
	# свежий project.godot (автозагрузки, main scene и т.п.) без ручных действий.
	EditorInterface.restart_editor(true)


func _show_plan_rollback_dialog(chain_id: String, desc: String) -> void:
	_plan_rollback_chain_id = chain_id
	# Вопрос показывается карточкой в чате вместо модального окна.
	# Тон "ask": это обычное подтверждение, а не предупреждение об аварии.
	if _view:
		_view.add_question_card(
			"plan_rollback",
			_t("plan_rb_title"),
			_t("plan_rb_text") % desc,
			_t("rb_yes"),
			_t("rb_no"),
			func(): _on_plan_rollback_confirmed(),
			func(): pass,
			"ask",
			["UndoRedo", "Undo", "Reload"]
		)


func _on_plan_rollback_confirmed() -> void:
	# v40: если сервер ранее ответил needs_force (файл менялся не из этой цепочки),
	# это повторное подтверждение уже означает согласие откатить принудительно —
	# раньше сюда всегда уходил force=false, и повторное нажатие «Да» просто
	# бесконечно повторяло тот же отказ (внешне выглядело так, будто кнопка не работает).
	if _plan_rollback_force_next:
		_view.add_warning(_t("force_rollback"))
		_send_plan_rollback_chain_request(true)
		return
	_send_plan_rollback_chain_request(false)


func _send_plan_rollback_chain_request(force: bool) -> void:
	if _is_network_busy: return
	var headers = _json_headers()
	var body = {"chain_id": _plan_rollback_chain_id, "force": force}
	_plan_rollback_force_next = false
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "plan_rollback_chain"
	_set_ui_busy(true)
	var err = http_request.request(PLAN_ROLLBACK_CHAIN_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("err_rollback"))
		_set_ui_busy(false)


func _on_message_rollback_requested(entry_id: String) -> void:
	# Откат по клику на карточке ответа агента.
	# Карточка присылает АДРЕС своей записи в журнале изменений, поэтому
	# откатывается именно это изменение. Раньше адреса не было: сервер получал
	# просьбу «откатить последнее» и отменял самое свежее изменение проекта —
	# из другого сообщения, а иногда и из другого чата.
	# Сначала спрашиваем сервер, что именно будет отменено, и показываем это
	# в карточке подтверждения — вслепую ничего не откатывается.
	if _is_network_busy:
		# Молча игнорировать клик нельзя: пользователь решит, что кнопка сломана.
		_log_error(_t("wait_current"))
		return
	if entry_id == "":
		# Кнопки на таких карточках быть не должно (см. _wire_card_rollback),
		# но если она как-то появилась — лучше сказать честно, чем откатить
		# наугад чужое изменение.
		_log_error(_t("rb_no_target"))
		return
	_on_rollback_pressed(entry_id)


func _show_battle_choice_summary(data: Dictionary) -> void:
	if _view == null:
		return
	var selected := str(data.get("selected", "A"))
	var message := _t("battle_choice_scores") % [
		selected,
		int(data.get("score_a", 0)),
		int(data.get("score_b", 0)),
	]
	match str(data.get("reason", "")):
		"other_continues":
			message += " " + (_t("battle_choice_continues") % str(data.get("other", "")))
		"equal":
			message += " " + (_t("battle_choice_equal") % selected)
		"only_acceptable":
			message += " " + _t("battle_choice_only")
		"only_verifiable":
			message += " " + _t("battle_choice_verifiable")
		"not_verifiable":
			message += " " + (_t("battle_choice_unverifiable") % selected)
		_:
			message += " " + _t("battle_choice_higher")
	_view.add_hint(message)


func _on_rollback_pressed(entry_id: String = "") -> void:
	if _is_network_busy: return
	# Адрес отката запоминаем до ответа на предпросмотр: подтверждение придёт
	# позже, а откатить надо ровно то, на что нажали.
	_rollback_entry_id = entry_id
	if _rollback_force_next and _rollback_force_entry_id == entry_id:
		# Повторное нажатие после needs_force — откатываем без лишних вопросов.
		# Сравнение адреса обязательно: раньше «взведённый» force срабатывал на
		# нажатие у ЛЮБОГО другого сообщения и молча, без подтверждения,
		# перезаписывал правки пользователя.
		_view.add_warning(_t("force_rollback"))
		_send_rollback_request(true)
		return
	_rollback_force_next = false
	# Сначала спрашиваем сервер, ЧТО именно будет отменено (и из какого
	# чата было это изменение), чтобы не откатить вслепую чужую работу.
	var headers = _json_headers()
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "rollback_preview"
	_set_ui_busy(true)
	var body := {}
	if entry_id != "":
		body["entry_id"] = entry_id
	var err = http_request.request(ROLLBACK_PREVIEW_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("err_rollback"))
		_set_ui_busy(false)


func _send_rollback_request(force: bool) -> void:
	var headers = _json_headers()
	var body = {"force": force}
	if _rollback_entry_id != "":
		body["entry_id"] = _rollback_entry_id
	_rollback_force_next = false
	http_request.set_http_proxy("", 0)
	_pending_request_kind = "rollback"
	_set_ui_busy(true)
	var err = http_request.request(ROLLBACK_URL, headers, HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_log_error(_t("err_rollback"))
		_set_ui_busy(false)


func _show_rollback_dialog(desc: String) -> void:
	# Вопрос об откате — карточкой в чате, а не модальным окном: так он
	# остаётся в истории рядом с изменением, которое откатывается.
	# Тон "ask": откат — обычное действие, а не авария. Раньше карточка была
	# жёлтой, со знаком «внимание», и рутинный откат выглядел как проблема.
	if _view:
		_view.add_question_card(
			"rollback",
			_t("rb_title"),
			desc,
			_t("rb_yes"),
			_t("rb_no"),
			func(): _on_rollback_confirmed(),
			func(): pass,
			"ask",
			["UndoRedo", "Undo", "Reload"]
		)


func _on_rollback_confirmed() -> void:
	_view.add_system(_t("rollback_msg"))
	_send_rollback_request(false)


func _ensure_file_logging_enabled() -> void:
	# Read-only inspection must never alter project.godot automatically.
	var base_on := bool(ProjectSettings.get_setting("debug/file_logging/enable_file_logging", false))
	var pc_on := bool(ProjectSettings.get_setting("debug/file_logging/enable_file_logging.pc", true))
	if not base_on and not pc_on:
		print("Godot Agent: файловое логирование выключено; включите его вручную для встроенных runtime errors.")


func _on_check_log_pressed() -> void:
	if _is_network_busy: return
	if _has_pending_action():
		_log_error(_t("resolve_action_first"))
		return
	_view.add_system(_t("reading_log"))
	_pending_log_send = false
	_auto_check = false
	_rollback_force_next = false
	var headers = _json_headers()
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
	var headers = _json_headers()
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
	if _has_pending_action():
		_log_error(_t("resolve_action_first"))
		return
	_export_api_to_server(false)


# silent = true — тихий автоматический запуск при старте плагина (не блокирует сеть для пользователя,
# просто показывает одно сообщение, если реально пришлось пересобирать).
func _export_api_to_server(silent: bool) -> void:
	if not silent:
		_view.add_system(_t("api_export_sending"))
	var export_script = load(get_script().resource_path.get_base_dir() + "/agent_api_export.gd")
	var classes: Dictionary = export_script.export_classes()
	var headers = _json_headers()
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
		if kind == "chat":
			_finish_chat_send()
			var transcript_warning := str(json.get("transcript_warning", ""))
			if transcript_warning != "":
				if _view:
					_view.add_system(transcript_warning)
				_notify(transcript_warning, "error")

		if kind == "init":
			_view.add_success(_t("reinit_done"))
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
			_scroll_chat_to_end()
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
			# Обновляем карточку-чеклист плана (чистый визуал, логика не меняется).
			if _active_plan_card and _active_plan_card.steps_container.get_child_count() > p_index:
				var step_item := _active_plan_card.steps_container.get_child(p_index) as PlanStepItem
				if step_item:
					step_item.description_label.text = p_msg
				if p_done:
					_active_plan_card.update_step(p_index, "done")
				elif p_ok:
					_active_plan_card.update_step(p_index, "active")
				else:
					_active_plan_card.update_step(p_index, "error")
			if p_ok:
				_view.add_system(p_msg)
			else:
				_view.add_warning(p_msg)
			# Шаг уже записан на диск, поэтому карточка идёт без кнопок —
			# только «файл +N -M» с возможностью развернуть код.
			var p_diff = json.get("step_diff")
			if p_ok and p_diff is Dictionary:
				var p_diff_path := str((p_diff as Dictionary).get("path", ""))
				if p_diff_path == "":
					p_diff_path = str(json.get("changed_path", ""))
				_view.add_applied_diff(p_diff_path, p_diff)
			var p_ch_path = json.get("changed_path")
			var p_ch_block = json.get("changed_block")
			if p_ch_path != null and p_ch_block != null and str(p_ch_block) != "":
				if _hl: _hl.apply(str(p_ch_path), str(p_ch_block))
			_force_reload_open_script()
			if p_ch_path != null:
				_auto_reload_changed_scene(str(p_ch_path))
			if p_done:
				_end_plan_execution()
				if _active_plan_card:
					_active_plan_card.queue_free()
					_active_plan_card = null
				_view.add_success(_t("plan_done"))
			elif p_stopped:
				_end_plan_execution()
				if _active_plan_card:
					_active_plan_card.queue_free()
					_active_plan_card = null
				_view.add_warning(_t("plan_stopped_desc") % [p_index, p_total])
				_show_plan_rollback_dialog(p_chain, _t("plan_rb_step_desc") % [p_index, p_total])
			else:
				_request_plan_step()
			await get_tree().process_frame
			return

		if kind == "plan_stop":
			var s_index := int(json.get("index", _plan_index))
			var s_total := int(json.get("total", _plan_total))
			var s_chain := str(json.get("chain_id", _plan_chain_id))
			_end_plan_execution()
			if _active_plan_card:
				_active_plan_card.queue_free()
				_active_plan_card = null
			_view.add_warning(_t("plan_stopped_manual") % [s_index, s_total])
			if s_index > 0:
				_show_plan_rollback_dialog(s_chain, _t("plan_rb_step_desc") % [s_index, s_total])
			await get_tree().process_frame
			_scroll_chat_to_end()
			return

		if kind == "plan_rollback_chain":
			var pr_msg = str(json.get("message", _t("rollback_done")))
			_view.add_success(_t("success_prefix") + pr_msg)
			_note_autoload_removed(json)
			if bool(json.get("requires_editor_restart", false)):
				_view.add_warning("Перезапустите редактор Godot, чтобы восстановленные настройки проекта полностью применились.")
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
			_scroll_chat_to_end()
			return

		if kind == "api_export":
			var cnt := int(json.get("classes_count", 0))
			_view.add_success(_t("api_export_done") % cnt)
			return

		if kind == "api_cache_status":
			_api_cache_check_attempts = 0
			var has_cache = bool(json.get("has_cache", false))
			var cached_version = str(json.get("cached_version", ""))
			var current_version = Engine.get_version_info().get("string", "")
			if not has_cache or cached_version != current_version:
				_export_api_to_server(true)
			return

		if kind == "confirm" and bool(json.get("execute_in_editor", false)):
			var editor_action_kind := str(json.get("editor_action_kind", "scene"))
			if editor_action_kind == "project_settings":
				_execute_project_settings_action(json)
			elif editor_action_kind == "resource":
				_execute_resource_action(json)
			elif editor_action_kind == "scene":
				_execute_scene_action(json)
			else:
				_log_error("Неизвестный тип editor-транзакции: " + editor_action_kind)
			return

		if kind == "confirm" and json.get("runtime_request") is Dictionary:
			_start_runtime_inspect(json)
			return

		if kind == "confirm" and json.get("runtime_check_request") is Dictionary:
			_start_runtime_check(json)
			return

		if kind == "runtime_check_bind":
			_execute_bound_runtime_check(json)
			return

		if kind == "runtime_result":
			_pending_runtime_request = {}
			if _runtime_timeout_timer:
				_runtime_timeout_timer.stop()

		if kind == "runtime_check_result":
			_clear_runtime_check_state()

		if kind == "resource_finalize":
			var resource_path := str(_pending_resource_action.get("resource", ""))
			if bool(json.get("success", false)):
				_view.add_agent_message(str(json.get("answer", "Структурные изменения ресурса применены.")),
					str(json.get("history_entry_id", "")))
			elif bool(json.get("restored", false)):
				_view.add_warning(str(json.get("answer", "Исходный ресурс восстановлен.")))
				if _resource_executor:
					_resource_executor.reload_after_recovery(resource_path)
			else:
				_view.add_error(str(json.get("answer", "Не удалось безопасно завершить транзакцию ресурса.")))
			_pending_resource_action = {}
			_pending_resource_expected_hash = ""
			_pending_resource_semantic_hash = ""
			_pending_resource_dependency_fingerprint = ""
			_pending_resource_finalize_body = {}
			_resource_finalize_retries = 0
			_resource_finalize_retrying = false
			_last_pending_action_type = ""
			_last_pending_action_paths = PackedStringArray()
			return

		if kind == "project_settings_finalize":
			if bool(json.get("success", false)):
				_view.add_agent_message(str(json.get("answer", "Настройки проекта применены.")),
					str(json.get("history_entry_id", "")))
				_view.add_warning("Перезапустите редактор Godot, чтобы все настройки и autoload гарантированно обновились.")
			elif bool(json.get("restored", false)):
				_view.add_warning(str(json.get("answer", "Исходный project.godot восстановлен. Перезапустите редактор.")))
			else:
				_view.add_error(str(json.get("answer", "Не удалось безопасно завершить транзакцию настроек.")))
			_pending_project_settings_action = {}
			_pending_project_settings_expected_hash = ""
			_pending_project_settings_semantic_hash = ""
			_pending_project_settings_finalize_body = {}
			_project_settings_finalize_retries = 0
			_project_settings_finalize_retrying = false
			_last_pending_action_type = ""
			_last_pending_action_paths = PackedStringArray()
			return

		if kind == "scene_finalize":
			var scene_path := str(_pending_scene_action.get("scene", ""))
			if bool(json.get("success", false)):
				_view.add_agent_message(str(json.get("answer", "Структурные изменения сцены применены.")),
					str(json.get("history_entry_id", "")))
			elif bool(json.get("restored", false)):
				_view.add_warning(str(json.get("answer", "Исходная сцена восстановлена.")))
				if _scene_executor:
					_scene_executor.reload_after_recovery(scene_path)
			else:
				_view.add_error(str(json.get("answer", "Не удалось безопасно завершить транзакцию сцены.")))
			_pending_scene_action = {}
			_pending_scene_expected_hash = ""
			_pending_scene_semantic_hash = ""
			_pending_scene_finalize_body = {}
			_scene_finalize_retries = 0
			_scene_finalize_retrying = false
			_last_pending_action_type = ""
			_last_pending_action_paths = PackedStringArray()
			return

		if kind == "rollback_preview":
			if bool(json.get("found", false)):
				if bool(json.get("blocked", false)):
					# Тот же файл агент правил позже. Откатывать через эти
					# правки нельзя — потерялась бы их работа. Объясняем и
					# НЕ предлагаем подтверждение: тут нечего подтверждать.
					_view.add_warning(str(json.get("description", "")))
					_view.scroll_to_end(true)
					_rollback_entry_id = ""
					return
				# Расширение одиночного отката до ВСЕЙ цепочки плана возможно
				# ТОЛЬКО когда адрес не указан (кнопка «откатить последнее» в
				# дополнительных настройках). При клике по карточке сообщения
				# адрес есть, и пользователь ждёт отката именно этого шага —
				# раньше здесь молча откатывался весь план целиком.
				var pv_chain := str(json.get("chain_id", ""))
				var pv_chain_total := int(json.get("chain_total", 0))
				if _rollback_entry_id == "" and pv_chain != "" and pv_chain_total > 1:
					_show_plan_rollback_dialog(pv_chain, _t("plan_rb_step_desc") % [pv_chain_total, pv_chain_total])
				else:
					_show_rollback_dialog(str(json.get("description", "")))
			else:
				# Откатывать нечего — это ответ на нажатие кнопки, поэтому
				# прокручиваем принудительно: иначе человек, читавший историю
				# выше, решит, что кнопка отката просто не сработала.
				_view.add_system(_t("rb_gone") if bool(json.get("gone", false)) else _t("rb_nothing"))
				_view.scroll_to_end(true)
				_rollback_entry_id = ""
			return

		if kind == "rollback":
			var msg = str(json.get("message", _t("rollback_done")))
			_view.add_success(_t("success_prefix") + msg)
			_note_autoload_removed(json)
			if bool(json.get("requires_editor_restart", false)):
				_view.add_warning("Перезапустите редактор Godot, чтобы восстановленные настройки проекта полностью применились.")
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
						# иначе Godot держит «призрака» и может пересохранить файл обратно.
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
			_scroll_chat_to_end()
			return

		if kind == "check_log":
			var was_auto := _auto_check
			_auto_check = false
			var found := int(json.get("found", 0))
			var log_info := str(json.get("log_time", "?"))
			if found == 0:
				if was_auto:
					_view.add_system(_t("log_auto_ok") % log_info)
				else:
					_view.add_success(_t("log_ok") % log_info)
			else:
				var head := _t("log_errs_auto") if was_auto else _t("log_errs")
				_view.add_system(head + str(found) + " (" + _t("log_from") + " " + log_info + ")\n" + str(json.get("summary", "")))
				if action_label and pending_action_box:
					var desc_text = _t("send_errors_q") % str(found)
					_set_pending_action(true, desc_text)
					_pending_log_send = true
					_guard_confirm_buttons()
					_view.add_confirmation_card(
						desc_text,
						func(): _on_confirm_pressed(),
						func(): _on_reject_pressed()
					)
			await get_tree().process_frame
			return

		if kind == "safe_rename_preview":
			var prep = json.get("prepared", {})
			_safe_rename_prepared = prep
			var ref_count := int(prep.get("reference_count", 0))
			var file_count := int(prep.get("file_count", 0))
			var aff_count := (prep.get("affected_paths", []) as Array).size()
			if _safe_rename_status_label:
				_safe_rename_status_label.text = _t("safe_rename_preview_found") % [ref_count, file_count, aff_count]
			var diffs = prep.get("diffs", [])
			if diffs is Array and not diffs.is_empty() and _view:
				_view.add_system("Предпросмотр безопасного переименования: %s -> %s" % [prep.get("old_path"), prep.get("new_path")])
				for d in diffs:
					if d is Dictionary:
						_view.add_readonly_diff(str(d.get("path", "")), d)
			return

		if kind == "safe_rename_apply":
			if bool(json.get("ok", false)):
				EditorInterface.get_resource_filesystem().scan()
				var old_p := str(json.get("old_path", ""))
				var new_p := str(json.get("new_path", ""))
				var ref_cnt := int(json.get("reference_count", 0))
				var file_cnt := int(json.get("file_count", 0))
				var changed_paths = json.get("changed_paths", [])
				if changed_paths is Array:
					for cp in changed_paths:
						_sync_open_script_with_disk(str(cp))
						_auto_reload_changed_scene(str(cp))
				_close_ghost_script_tab(old_p)
				if FileAccess.file_exists(new_p) and new_p.ends_with(".gd"):
					var scr = load(new_p)
					if scr is Script:
						EditorInterface.edit_script(scr, -1, 0, false)
				var msg := _t("safe_rename_success") % [old_p, new_p, ref_cnt, file_cnt]
				if _view:
					_view.add_agent_message(msg, str(json.get("entry_id", "")))
				if _safe_rename_dialog:
					_safe_rename_dialog.hide()
				_maybe_prompt_project_reload(json)
			else:
				var err_msg := str(json.get("error", "Ошибка применения переименования"))
				if _safe_rename_status_label:
					_safe_rename_status_label.text = err_msg
				_log_error(err_msg)
			return

		if kind == "safe_node_rename_preview":
			var prep = json.get("prepared", {})
			_safe_node_rename_prepared = prep
			var ref_count := int(prep.get("reference_count", 0))
			var file_count := int(prep.get("file_count", 0))
			var aff_count := (prep.get("affected_paths", []) as Array).size()
			if _safe_node_rename_status_label:
				_safe_node_rename_status_label.text = _t("safe_node_rename_preview_found") % [ref_count, file_count, aff_count]
			var diffs = prep.get("diffs", [])
			if diffs is Array and not diffs.is_empty() and _view:
				_view.add_system("Предпросмотр безопасного переименования узла: %s -> %s в %s" % [prep.get("node_path"), prep.get("new_name"), prep.get("scene")])
				for d in diffs:
					if d is Dictionary:
						_view.add_readonly_diff(str(d.get("path", "")), d)
			return

		if kind == "safe_node_rename_apply":
			if bool(json.get("ok", false)):
				EditorInterface.get_resource_filesystem().scan()
				var scene_p := str(json.get("scene", ""))
				var old_p := str(json.get("node_path", ""))
				var new_p := str(json.get("new_name", ""))
				var ref_cnt := int(json.get("reference_count", 0))
				var file_cnt := int(json.get("file_count", 0))
				var changed_paths = json.get("changed_paths", [])
				if changed_paths is Array:
					for cp in changed_paths:
						_sync_open_script_with_disk(str(cp))
						_auto_reload_changed_scene(str(cp))
				var msg := _t("safe_node_rename_success") % [old_p, new_p, scene_p, ref_cnt, file_cnt]
				if _view:
					_view.add_agent_message(msg, str(json.get("entry_id", "")))
				if _safe_node_rename_dialog:
					_safe_node_rename_dialog.hide()
			else:
				var err_msg := str(json.get("error", "Ошибка применения переименования узла"))
				if _safe_node_rename_status_label:
					_safe_node_rename_status_label.text = err_msg
				_log_error(err_msg)
			return

		# После подтверждённого WRITE-действия — синхронизируем открытую вкладку.
		# При пакетном чтении файлов _last_pending_action_type пуст — ничего не трогаем.
		if kind == "confirm" and _last_pending_action_type != "":
			var changed_paths = json.get("changed_paths")
			if changed_paths is Array:
				for changed_path in changed_paths:
					_sync_open_script_with_disk(str(changed_path))
					_auto_reload_changed_scene(str(changed_path))
			else:
				_force_reload_open_script()
			if _last_pending_action_path != "":
				_auto_reload_changed_scene(_last_pending_action_path)
			if _last_pending_action_dest != "":
				_auto_reload_changed_scene(_last_pending_action_dest)
			_reopen_scenes_after_write()  # v49: вернуть сцены, закрытые перед записью, — уже в новом виде
			_last_pending_action_type = ""
			_last_pending_action_path = ""
			_last_pending_action_dest = ""
			_last_pending_action_paths = PackedStringArray()
			# Открываем изменённый файл и подсвечиваем строки, написанные агентом.
			var ch_path = json.get("changed_path")
			var ch_block = json.get("changed_block")
			if ch_path != null and ch_block != null and str(ch_block) != "":
				if _hl: _hl.apply(str(ch_path), str(ch_block))

		# Текстовый ответ ИИ (не печатаем пустые ответы)
		var has_answer: bool = json.has("answer") and json["answer"] != null and str(json["answer"]) != ""
		if has_answer:
			# history_entry_id есть только у сообщения о ПРИМЕНЁННОМ изменении
			# (ответ на подтверждение действия или шаг плана). Именно оно и
			# получает кнопку отката, и именно своё изменение откатывает.
			# Обычный ответ модели приходит без адреса — кнопки у него нет.
			_view.add_agent_message(str(json["answer"]),
				str(json.get("history_entry_id", "")))
			_request_chats("list", {})  # обновить авто-названия чатов
		var battle_choice = json.get("battle_choice")
		if battle_choice is Dictionary:
			_show_battle_choice_summary(battle_choice)

		# Промежуточное подтверждение файла из пачки на чтение:
		# сервер НЕ ходил в браузер, просто спрашивает про следующий файл.
		var nxt = json.get("next_confirmation")
		if nxt != null and action_label and pending_action_box:
			var desc = str(nxt.get("description", _t("agent_wants_file")))
			_set_pending_action(true, desc)
			_guard_confirm_buttons()
			_view.add_confirmation_card(
				desc,
				func(): _on_confirm_pressed(),
				func(): _on_reject_pressed()
			)
			await get_tree().process_frame
			return

		# WRITE-действие, требующее подтверждения
		var pending = json.get("pending_action")
		if pending != null and action_label and pending_action_box:
			var description = json.get("pending_action_description", _t("agent_wants_action"))
			if description == null: description = _t("agent_wants_action")
			# Красивый предпросмотр: сервер присылает ЧИСТЫЙ код (без JSON-обёртки)
			# и, если смог посчитать, разобранный дифф — что добавится и что удалится.
			var pcode = json.get("pending_action_code")
			var pdiff = json.get("pending_action_diff")
			var pdiffs = json.get("pending_action_diffs")
			var diff_data: Dictionary = pdiff if pdiff is Dictionary else {}
			_last_pending_action_type = str(pending.get("action", ""))
			_last_pending_action_path = str(pending.get("path", ""))
			if _last_pending_action_path.is_empty():
				_last_pending_action_path = str(pending.get("scene", ""))
			_last_pending_action_dest = str(pending.get("dest", ""))
			_last_pending_action_paths = PackedStringArray()
			var raw_paths = pending.get("paths", [])
			if raw_paths is Array and not raw_paths.is_empty():
				for raw_path in raw_paths:
					_last_pending_action_paths.append(str(raw_path))
			elif pending.has("affected_paths"):
				for raw_path in pending.get("affected_paths", []):
					_last_pending_action_paths.append(str(raw_path))
			_set_pending_action(true, str(description))
			_guard_confirm_buttons()
			if _last_pending_action_type in ["edit_scene", "create_scene"]:
				var scene_preview := _prepare_scene_action(pending, json.get("scene_prepare", {}))
				if not bool(scene_preview.get("ok", false)):
					_view.add_warning("Godot отклонил предпросмотр сцены: " + str(scene_preview.get("error", "")))
					_on_reject_pressed()
					return
				var preview_lines = scene_preview.get("changes", [])
				if preview_lines is Array and not preview_lines.is_empty():
					_view.add_system("Предпросмотр структурных изменений:\n• " + "\n• ".join(preview_lines))
			elif _last_pending_action_type == "edit_project_settings":
				var settings_preview := _prepare_project_settings_action(
					pending, json.get("project_settings_prepare", {}))
				if not bool(settings_preview.get("ok", false)):
					_view.add_warning("Godot отклонил настройки проекта: " + str(settings_preview.get("error", "")))
					_on_reject_pressed()
					return
				var settings_lines = settings_preview.get("changes", [])
				if settings_lines is Array and not settings_lines.is_empty():
					_view.add_system("Предпросмотр настроек проекта:\n• " + "\n• ".join(settings_lines))
			elif _last_pending_action_type == "edit_resource":
				var resource_preview := _prepare_resource_action(
					pending, json.get("resource_prepare", {}))
				if not bool(resource_preview.get("ok", false)):
					_view.add_warning("Godot отклонил ресурс: " + str(resource_preview.get("error", "")))
					_on_reject_pressed()
					return
				var resource_lines = resource_preview.get("changes", [])
				if resource_lines is Array and not resource_lines.is_empty():
					_view.add_system("Предпросмотр структурных изменений ресурса:\n• " +
						"\n• ".join(resource_lines))

			# Дифф сам по себе достаточен для карточки: patch_file, который
			# только УДАЛЯЕТ код, приходит с пустым replace — раньше такой
			# правке доставалась безликая карточка подтверждения.
			if pdiffs is Array and not (pdiffs as Array).is_empty():
				for raw_diff in pdiffs:
					if raw_diff is Dictionary:
						var readonly_diff := raw_diff as Dictionary
						_view.add_readonly_diff(str(readonly_diff.get("path", "")), readonly_diff)
				_view.add_confirmation_card(
					str(description),
					func(): _on_confirm_pressed(),
					func(): _on_reject_pressed()
				)
			elif (pcode != null and str(pcode) != "") or not diff_data.is_empty():
				var file_path = _last_pending_action_path if _last_pending_action_path != "" else _last_pending_action_dest
				var card = _view.add_diff_preview(file_path, str(pcode) if pcode != null else "", diff_data)
				if card:
					card.diff_applied.connect(func(_p): _on_confirm_pressed())
					card.diff_rejected.connect(func(_p): _on_reject_pressed())
			else:
				_view.add_confirmation_card(
					str(description),
					func(): _on_confirm_pressed(),
					func(): _on_reject_pressed()
				)
		elif pending_action_box:
			_set_pending_action(false)
			# Ни текста, ни действий — не молчим, чтобы ответ не "пропадал" бесследно.
			if not has_answer and (kind == "chat" or kind == "confirm"):
				_view.add_system(_t("empty_response"))

		await get_tree().process_frame
	else:
		if kind == "chat":
			_restore_chat_draft()
		if kind == "runtime_check_bind":
			_send_runtime_check_result("bridge_unavailable", {})
			return
		if kind == "runtime_check_result":
			if response_code in [400, 403, 409, 410, 413]:
				_log_error("Сервер окончательно отклонил результат локальной игровой проверки.")
				_clear_runtime_check_state()
			else:
				_log_error("Сервер временно не принял результат; отправка будет повторена.")
			return
		if kind == "runtime_result":
			_pending_runtime_request = {}
			if _runtime_timeout_timer:
				_runtime_timeout_timer.stop()
			_log_error("Runtime inspection завершён без ответа модели: " + str(response_code))
			return
		if kind == "resource_finalize":
			if response_code in [400, 403, 409, 410, 413]:
				var resource_error := str(json.get("answer", json.get("error", "Сервер отклонил завершение транзакции ресурса."))) if json else "Сервер отклонил завершение транзакции ресурса."
				_view.add_error(resource_error)
				_pending_resource_action = {}
				_pending_resource_expected_hash = ""
				_pending_resource_semantic_hash = ""
				_pending_resource_dependency_fingerprint = ""
				_pending_resource_finalize_body = {}
				_resource_finalize_retries = 0
				_resource_finalize_retrying = false
				_last_pending_action_type = ""
				_last_pending_action_paths = PackedStringArray()
			else:
				_schedule_resource_finalize_retry()
			return
		if kind == "project_settings_finalize":
			if response_code in [400, 403, 409, 410, 413]:
				var settings_error := str(json.get("answer", json.get("error", "Сервер отклонил завершение транзакции настроек."))) if json else "Сервер отклонил завершение транзакции настроек."
				_view.add_error(settings_error)
				_pending_project_settings_action = {}
				_pending_project_settings_expected_hash = ""
				_pending_project_settings_semantic_hash = ""
				_pending_project_settings_finalize_body = {}
				_project_settings_finalize_retries = 0
				_project_settings_finalize_retrying = false
				_last_pending_action_type = ""
				_last_pending_action_paths = PackedStringArray()
			else:
				_schedule_project_settings_finalize_retry()
			return
		if kind == "scene_finalize":
			if response_code in [400, 403, 409, 410, 413]:
				var scene_error := str(json.get("answer", json.get("error", "Сервер отклонил завершение транзакции сцены."))) if json else "Сервер отклонил завершение транзакции сцены."
				_view.add_error(scene_error)
				_pending_scene_action = {}
				_pending_scene_expected_hash = ""
				_pending_scene_semantic_hash = ""
				_pending_scene_finalize_body = {}
				_scene_finalize_retries = 0
				_scene_finalize_retrying = false
				_last_pending_action_type = ""
				_last_pending_action_paths = PackedStringArray()
			else:
				_schedule_scene_finalize_retry()
			return
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
		if kind in ["safe_rename_preview", "safe_rename_apply", "safe_node_rename_preview", "safe_node_rename_apply"]:
			var sr_err := str(json.get("error", "Ошибка операции переименования")) if json is Dictionary else ("Ошибка HTTP " + str(response_code))
			if kind.begins_with("safe_node_rename_"):
				if _safe_node_rename_status_label:
					_safe_node_rename_status_label.text = sr_err
			else:
				if _safe_rename_status_label:
					_safe_rename_status_label.text = sr_err
			_log_error(sr_err)
			return
		if kind == "confirm":
			if _last_pending_action_type not in ["edit_scene", "create_scene", "rename_node", "reparent_node", "delete_node", "edit_project_settings", "edit_resource", "inspect_runtime", "run_check"]:
				_reopen_scenes_after_write()  # v49: действие не выполнено — вернуть закрытые сцены
		var err_msg = _t("srv_no_reply")
		if json and json.has("error") and json["error"] != null:
			err_msg = str(json["error"])
		# Сервер просит подтвердить откат повторным нажатием кнопки.
		# v40: раньше здесь всегда выставлялся _rollback_force_next (флаг одиночного
		# отката), даже для отката всей цепочки плана (kind == "plan_rollback_chain") — а его
		# никто не читал, потому кнопка «Откатить» (одиночный откат) тут не задействована, а
		# диалог отката цепоци всё равно снова посылал force=false и молча падал снова и снова
		# (внешне выглядело как «нажал и ничего не произошло»). Теперь для plan_rollback_chain
		# ставится свой собственный флаг _plan_rollback_force_next, и диалог подтверждения показывается
		# ещё раз, чтобы следующее подтверждение ушло с force=true.
		if json != null and json.get("needs_force") == true:
			if kind == "plan_rollback_chain":
				_plan_rollback_force_next = true
				_view.add_warning(_t("plan_rb_needs_force"))
				_show_plan_rollback_dialog(_plan_rollback_chain_id, _t("plan_rb_force_desc"))
				await get_tree().process_frame
				_scroll_chat_to_end()
				return
			_rollback_force_next = true
			# Запоминаем, ДЛЯ КАКОГО адреса взведён force. Раньше флаг был
			# общим: нажатие кнопки отката у любого другого сообщения тут же
			# уходило с force=true — без предпросмотра и без подтверждения — и
			# перезаписывало ручные правки пользователя в другом файле.
			_rollback_force_entry_id = _rollback_entry_id
		_log_error((_t("srv_error") % str(response_code)) + err_msg)


func _log_error(msg: String) -> void:
	# Раньше текст уходил в chat_log — а его прячет agent_chat_view.setup(),
	# поэтому ВСЕ ошибки были невидимы пользователю. Теперь это карточка в чате.
	if _view:
		_view.flush()
		_view.add_error(_t("error_prefix") + msg)
	else:
		# Панель ещё не собрана — хотя бы не теряем текст ошибки молча.
		push_error("[Godot Agent] " + msg)


func _scroll_chat_to_end() -> void:
	# Раньше здесь дёргался chat_log.scroll_to_line(), но ChatLog скрыт —
	# прокрутка уходила в невидимый узел. Карточки прокручивает сам вид чата.
	if _view:
		_view.scroll_to_end()


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
	if not _has_pending_action():
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


func _open_pending_scene_paths() -> PackedStringArray:
	var result := PackedStringArray()
	var open_scenes := EditorInterface.get_open_scenes()
	var targets := _last_pending_action_paths.duplicate()
	targets.append(_last_pending_action_path)
	targets.append(_last_pending_action_dest)
	for raw in targets:
		var sp := str(raw)
		if sp == "" or not (sp.to_lower().ends_with(".tscn") or sp.to_lower().ends_with(".scn")):
			continue
		for opened in open_scenes:
			if str(opened).to_lower() == sp.to_lower() and not result.has(sp):
				result.append(sp)
	return result


func _reopen_scenes_after_write() -> void:
	# v49: открываем обратно сцены, закрытые перед записью. Если действие
	# не выполнилось или файл переехал/удалён — просто пропускаем.
	for sp in _scenes_to_reopen:
		if FileAccess.file_exists(str(sp)):
			EditorInterface.open_scene_from_path(str(sp))
	_scenes_to_reopen = PackedStringArray()


func _ensure_script_autoreload_setting() -> void:
	# Editor preferences belong to the user, not to the plugin.
	var es = EditorInterface.get_editor_settings()
	if es == null:
		return
	var key := "text_editor/behavior/files/auto_reload_scripts_on_external_change"
	if es.has_setting(key) and not bool(es.get_setting(key)):
		push_warning("Автоперезагрузка скриптов выключена. При необходимости включите её в Editor Settings; агент не меняет эту настройку.")


func _force_reload_open_script() -> void:
	var target_path := _last_pending_action_path
	if _last_pending_action_type == "move_file" and not _last_pending_action_dest.is_empty():
		target_path = _last_pending_action_dest
	_sync_open_script_with_disk(target_path)


func _dirty_open_scripts(target_paths: PackedStringArray) -> PackedStringArray:
	var affected := PackedStringArray()
	if target_paths.is_empty():
		return affected
	var wanted := {}
	for path in target_paths:
		wanted[path.to_lower()] = true
	var script_editor := EditorInterface.get_script_editor()
	if not script_editor:
		return affected
	for script in script_editor.get_open_scripts():
		if script and wanted.has(str(script.resource_path).to_lower()):
			affected.append(str(script.resource_path))
	if affected.is_empty():
		return affected
	# Public ScriptEditorBase has no get_edited_resource(). Do not assume that
	# two editor arrays share an order: require all open buffers to be clean.
	var editors := script_editor.get_open_script_editors()
	if editors.is_empty():
		return affected
	for editor in editors:
		var code_edit := editor.get_base_editor() as CodeEdit
		if code_edit == null or code_edit.get_version() != code_edit.get_saved_version():
			return affected
	return PackedStringArray()


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
	if not _pending_scene_finalize_body.is_empty() and not _scene_finalize_retrying and not _is_network_busy \
			and _pending_request_kind != "scene_finalize":
		_send_pending_scene_finalize()
	if _hl: _hl.watchdog()
	_reconcile_confirm_buttons()
	if not _pending_project_settings_finalize_body.is_empty() and not _project_settings_finalize_retrying and not _is_network_busy \
			and _pending_request_kind != "project_settings_finalize":
		_send_pending_project_settings_finalize()
	if not _pending_resource_finalize_body.is_empty() and not _resource_finalize_retrying and not _is_network_busy \
			and _pending_request_kind != "resource_finalize":
		_send_pending_resource_finalize()
	if not _pending_runtime_check_result_body.is_empty() and not _is_network_busy:
		_send_pending_runtime_check_result()
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
	if _has_pending_action(): return
	_auto_check = true
	_pending_log_send = false
	var headers = _json_headers()
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
	# Токен обязателен и здесь: /chat/progress — обычный GET, но сервер после
	# привязки проверяет ВСЕ запросы. Без заголовка он отвечал бы 403, а
	# _on_progress_response молча игнорирует не-200 — живая трансляция ответа
	# просто перестала бы появляться в чате, без единого сообщения об ошибке.
	var err = _progress_http.request(PROGRESS_URL, _json_headers())
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

func _request_chats(kind: String, extra: Dictionary, allow_autostart: bool = true) -> void:
	if _link == null:
		return
	if _is_network_busy and kind != "list" and kind != "sites" and kind != "status" and kind != "minilich_status" and kind != "minilich_set" and kind != "minilich_github" and not kind.begins_with("api_"):
		_log_error(_t("wait_current"))
		return
	_link.request(kind, extra, allow_autostart)


func _on_chats_payload(kind: String, json: Dictionary, extra: Dictionary) -> void:
	if kind == "minilich_github":
		if _minilich_github_label:
			if json.has("error"):
				_minilich_github_label.text = str(json.get("error", ""))
			else:
				_minilich_github_label.text = _t("github_fetch_running")
		return
	if kind == "minilich_status" or kind == "minilich_set":
		_on_minilich_payload(kind, json)
		return
	if kind == "status":
		_on_browser_status(json)
		return
	if kind == "chat_model":
		# Смена модели у ОТКРЫТОГО чата. Обрабатывается до общего хвоста: чат
		# перерисовывать нельзя — переписка сохранена, и это главное свойство
		# действия. Меняется только подпись модели и появляется системная строка.
		if json.has("error"):
			_notify(str(json.get("error", "")), "error")
			_log_error(str(json.get("error", "")))
			return
		_api_chat_model = str(json.get("model", ""))
		_api_chat_site = str(json.get("site", ""))
		_push_api_switch_target()
		if _view:
			_view.add_system(_t("chat_model_changed") % str(json.get("site", "")))
		_notify(_t("chat_model_changed_short"), "success")
		_fill_chat_list(json.get("chats", []))
		if _start_screen:
			_start_screen.set_chats(json.get("chats", []))
		return
	if kind.begins_with("api_"):
		_on_api_payload(kind, json)
		return
	if kind == "sites":
		if _start_screen:
			_start_screen.set_sites(json.get("sites", []))
			if _pending_view == "sites":
				_pending_view = ""
				_start_screen.show_sites()
		return
	if json.has("error"):
		var message := str(json.get("error", _t("srv_no_response")))
		_log_error(message)
		_notify(message, "error")
		if kind == "open" or kind == "new":
			_site_resend_envelope = {}
			_restore_chat_draft()
		return
	var cur = json.get("current_id")
	if cur != null and (kind == "open" or kind == "new"):
		_switch_chat_draft(str(cur))
	if cur != null:
		_current_chat_id = str(cur)
	if kind == "open" or kind == "new":
		_chat_navigation_generation += 1
		# Не стираем новый draft, набранный пока запрос навигации был в пути.
		# Очищаем только действительно пустое/старое визуальное состояние.
		if input_field == null or input_field.text.is_empty():
			_clear_chat_input(true)
		var keeps_resend := (kind == "open"
			and not _site_resend_envelope.is_empty()
			and bool(_site_resend_envelope.get("waiting_open", false))
			and str(_site_resend_envelope.get("chat_id", "")) == _current_chat_id
			and int(_site_resend_envelope.get("expected_generation", -1)) == _chat_navigation_generation)
		if not keeps_resend:
			if not _site_resend_envelope.is_empty():
				var source_chat := str(_site_resend_envelope.get("chat_id", ""))
				var source_prompt := str(_site_resend_envelope.get("prompt", ""))
				if source_chat != "" and source_prompt != "":
					_chat_drafts[source_chat] = source_prompt
			_site_resend_envelope = {}
			# Это завершение навигации, а не успешная отправка сообщения.
			# Не удаляем восстановленный draft нового чата.
			_pending_chat_prompt = ""
			_pending_editor_context = {}
	_fill_chat_list(json.get("chats", []))
	if _start_screen:
		_start_screen.set_chats(json.get("chats", []))
		if _pending_view == "chats":
			_pending_view = ""
			_start_screen.show_chats()
	if kind == "open" and _view:
		_clear_pending_action_state()
		_view.clear()
		# Модель запоминаем ТОЛЬКО для чата по ключу: у браузерного её нет, и
		# оставленная от прошлого чата строка предложила бы сменить то, чего не
		# существует.
		_api_chat_model = (str(json.get("model", ""))
			if str(json.get("kind", "browser")) == "api" else "")
		_api_chat_site = (str(json.get("site", ""))
			if str(json.get("kind", "browser")) == "api" else "")
		_push_api_switch_target()
		_view.set_battle_scope(str(json.get("site_id", "")) == "arena_battle")
		_render_transcript(json.get("transcript", []))
		_view.add_system(_t("chat_opened") % str(json.get("title", "")))
		var warn: String = str(json.get("warning", ""))
		if warn != "":
			_view.add_system(warn)
			_notify(warn, "error")
		var trimmed := int(json.get("transcript_trimmed", 0))
		if trimmed > 0:
			_view.add_system("Более старые сообщения этого чата не показаны: %d." % trimmed)
		_enter_chat_ui()
		# У чата по ключу API нет страницы в браузере: ждать её загрузки нечего,
		# а ожидание ещё и 40 раз опросило бы /browser/status и закончилось
		# ложным предупреждением «страница долго грузится».
		if str(json.get("kind", "browser")) != "api":
			_begin_page_wait()
		if warn != "" and not _site_resend_envelope.is_empty():
			_site_resend_envelope = {}
			_restore_chat_draft()
			return
		if (not _site_resend_envelope.is_empty()
				and bool(_site_resend_envelope.get("waiting_open", false))
				and str(_site_resend_envelope.get("chat_id", "")) == _current_chat_id
				and int(_site_resend_envelope.get("expected_generation", -1)) == _chat_navigation_generation):
			var resend := _site_resend_envelope.duplicate(true)
			_site_resend_envelope = {}
			_pending_editor_context = resend.get("editor_context", {})
			_send_chat_raw(str(resend.get("prompt", "")), true)
		elif not _site_resend_envelope.is_empty():
			_site_resend_envelope = {}
	elif kind == "new" and _view:
		_clear_pending_action_state()
		_view.clear()
		_api_chat_model = (str(json.get("model", ""))
			if str(json.get("kind", "browser")) == "api" else "")
		_api_chat_site = (str(json.get("site", ""))
			if str(json.get("kind", "browser")) == "api" else "")
		_push_api_switch_target()
		_view.set_battle_scope(str(json.get("site_id", "")) == "arena_battle")
		_view.add_system(_t("chat_created"))
		if str(json.get("kind", "browser")) == "api":
			# Модель выбрана заранее в настройках и закреплена за чатом —
			# напоминание «выберите модель на странице» здесь было бы неверным.
			_view.add_hint(_t("api_chat_hint") % [str(json.get("site", "")),
				str(json.get("model", ""))])
			_enter_chat_ui()
		else:
			_view.add_hint(_t("pick_model_hint"))  # v48/v49: напоминание выбрать модель — заметным окошком
			_enter_chat_ui()
			_begin_page_wait()
	elif kind == "delete":
		var deleted_current := str(extra.get("id", "")) == _current_chat_id
		if deleted_current:
			_current_chat_id = ""
			_api_chat_model = ""
			_api_chat_site = ""
			_push_api_switch_target()
			_clear_pending_action_state()
		_on_link_hide_loading()
		_show_start_ui()
		if bool(extra.get("return_to_list", false)) and _start_screen:
			_start_screen.show_chats()


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
	# «＋» в чате открывает выбор сайта (нейросети). Важно сначала
	# показать стартовый экран — иначе экран загрузки останется невидимым.
	_show_start_ui()
	_on_sites_tab_requested()


func _on_chat_rename_pressed() -> void:
	if _current_chat_id == "":
		_log_error(_t("select_chat_hint"))
		return
	# Вместо модального окна — правка прямо в строке чатов: OptionButton
	# на время подменяется полем ввода. Enter — сохранить, Esc — отмена.
	if _chat_select == null or not is_instance_valid(_chat_select):
		return
	if _rename_edit != null and is_instance_valid(_rename_edit):
		# Правка уже открыта — просто возвращаем фокус.
		_rename_edit.grab_focus()
		return
	var bar := _chat_select.get_parent()
	if bar == null:
		return

	_rename_edit = LineEdit.new()
	_rename_edit.name = "ChatRenameEdit"
	_rename_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_rename_edit.custom_minimum_size.x = 40.0
	if _chat_select.selected >= 0:
		_rename_edit.text = _chat_select.get_item_text(_chat_select.selected)
	_rename_edit.select_all()
	var T = _T()
	if T:
		T.style_input(_rename_edit)

	bar.add_child(_rename_edit)
	bar.move_child(_rename_edit, _chat_select.get_index())
	_chat_select.visible = false

	_rename_edit.text_submitted.connect(func(new_title: String) -> void:
		_finish_chat_rename(new_title)
	)
	# focus_exited = клик мимо: считаем это отменой, чтобы поле не зависало.
	_rename_edit.focus_exited.connect(func() -> void:
		_cancel_chat_rename()
	)
	_rename_edit.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
			_cancel_chat_rename()
	)
	_rename_edit.grab_focus()


func _finish_chat_rename(new_title: String) -> void:
	var t := new_title.strip_edges()
	_close_rename_edit()
	if t == "":
		return
	_request_chats("rename", {"id": _current_chat_id, "title": t})


func _cancel_chat_rename() -> void:
	_close_rename_edit()


func _close_rename_edit() -> void:
	# Возвращаем выпадающий список на место и убираем поле ввода.
	if _chat_select and is_instance_valid(_chat_select):
		_chat_select.visible = true
	if _rename_edit and is_instance_valid(_rename_edit):
		var edit := _rename_edit
		_rename_edit = null
		edit.queue_free()
	else:
		_rename_edit = null


func _on_chat_delete_pressed() -> void:
	if _current_chat_id == "":
		_log_error(_t("select_chat_first"))
		return
	# Защита от случайных нажатий: подтверждение карточкой в чате.
	# Удаление необратимо, поэтому тон «error», а не «warning».
	var chat_title := ""
	if _chat_select and _chat_select.selected >= 0:
		chat_title = _chat_select.get_item_text(_chat_select.selected)
	if _view:
		_view.add_question_card(
			"delete_chat",
			_t("del_title"),
			_t("del_text") % chat_title,
			_t("del_yes"),
			_t("del_no"),
			func(): _on_delete_confirmed(),
			func(): pass,
			"error"
		)


func _on_delete_confirmed() -> void:
	if _current_chat_id == "":
		return
	_request_chats("delete", {"id": _current_chat_id})


func _on_start_delete_chat(chat_id: String) -> void:
	if chat_id == "":
		return
	_request_chats("delete", {"id": chat_id, "return_to_list": true})


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
	if _view:
		_view.set_battle_scope(false)
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
	if input_field:
		input_field.call_deferred("grab_focus")
		input_field.queue_redraw()


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
	if _bar_btn_settings:
		_bar_btn_settings.tooltip_text = _t("tip_settings")


func _on_language_changed() -> void:
	# Обновляем подписи панели сразу, без перезагрузки плагина.
	name = _t("dock_title")
	if send_button and not _is_network_busy:
		send_button.text = _t("send")
	if input_field:
		input_field.placeholder_text = _t("input_placeholder")
	_refresh_chat_model_btn()
	if confirm_button:
		confirm_button.text = _t("allow")
	if reject_button:
		reject_button.text = _t("reject")
	if reinit_button:
		reinit_button.text = _t("reinit")
	if action_label and not action_label.visible:
		# Скрытая строка подтверждения тоже переводится: см. пояснение там, где
		# её прячут. Видимую не трогаем — в ней описание конкретного действия.
		action_label.text = _t("pending_default")
	if _log_errors_button:
		_log_errors_button.text = _t("log_errors")
	if _api_export_button:
		_api_export_button.text = _t("api_export_btn")
	if _safe_rename_button:
		_safe_rename_button.text = _t("safe_rename_btn")
	if _safe_node_rename_button:
		_safe_node_rename_button.text = _t("safe_node_rename_btn")
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
	_site_resend_envelope = {
		"prompt": prompt,
		"editor_context": _pending_editor_context.duplicate(true),
		"chat_id": _current_chat_id,
		"generation": _chat_navigation_generation,
		"waiting_open": false,
	}
	# Карточкой в чате вместо модального окна. ВАЖНО: «Нет» здесь не отмена —
	# запрос всё равно уходит, только без переключения страницы
	# (см. _on_site_switch_no), поэтому колбэк обязателен.
	if _view:
		_view.add_question_card(
			"site_mismatch",
			_t("site_mismatch_title"),
			_t("site_mismatch_prefix") + ((" (" + site_name + ")") if site_name != "" else "") + "?",
			_t("site_yes"),
			_t("site_no"),
			func(): _on_site_switch_yes(),
			func(): _on_site_switch_no()
		)


func _on_site_switch_yes() -> void:
	if (_site_resend_envelope.is_empty()
			or str(_site_resend_envelope.get("chat_id", "")) != _current_chat_id
			or int(_site_resend_envelope.get("generation", -1)) != _chat_navigation_generation):
		_log_error("Чат изменился; исходный запрос не был повторно отправлен.")
		_site_resend_envelope = {}
		_restore_chat_draft()
		return
	if _current_chat_id == "":
		var direct := _site_resend_envelope.duplicate(true)
		_site_resend_envelope = {}
		_pending_editor_context = direct.get("editor_context", {})
		_send_chat_raw(str(direct.get("prompt", "")), true)
		return
	_site_resend_envelope["waiting_open"] = true
	_site_resend_envelope["expected_generation"] = _chat_navigation_generation + 1
	_request_chats("open", {"id": _current_chat_id})


func _on_site_switch_no() -> void:
	if _view:
		_view.add_system(_t("stay_on_page"))
	if (_site_resend_envelope.is_empty()
			or str(_site_resend_envelope.get("chat_id", "")) != _current_chat_id
			or int(_site_resend_envelope.get("generation", -1)) != _chat_navigation_generation):
		_log_error("Чат изменился; исходный запрос не был повторно отправлен.")
		_site_resend_envelope = {}
		_restore_chat_draft()
		return
	var resend := _site_resend_envelope.duplicate(true)
	_site_resend_envelope = {}
	_pending_editor_context = resend.get("editor_context", {})
	_send_chat_raw(str(resend.get("prompt", "")), true)


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


# ---------------------------------------------------------------------------
# Работа по ключу API: настройки, список моделей, проверка подключения.
# Панель здесь только курьер: форму рисует и заполняет стартовый экран, а
# состояние настроек целиком приходит с сервера — своего представления о нём
# панель не держит, поэтому оно не может разойтись с файлом на диске.
# ---------------------------------------------------------------------------

func _on_api_tab_requested() -> void:
	_pending_view = "api"
	if _start_screen and _start_screen.has_method("show_loading"):
		_start_screen.show_loading(_t("connecting"))
	_request_chats("api_providers", {})


func _on_api_settings_save(data: Dictionary) -> void:
	_request_chats("api_set", data)


func _on_api_models_refresh(provider: String, free_only: bool) -> void:
	_request_chats("api_models", {"provider": provider, "free_only": free_only})


func _on_api_models_scan(force: bool) -> void:
	# Обход провайдеров за списками моделей. Ходит только к тем, кого можно
	# спросить без ключа или с уже сохранённым ключом, и только если их числа
	# устарели — решает это сервер (providers.autoscan_targets), потому что
	# только он знает, где лежат ключи и когда список обновлялся.
	_request_chats("api_scan", {"force": force})


func _on_api_test_requested(provider: String, model: String) -> void:
	_request_chats("api_test", {"provider": provider, "model": model})


func _on_start_new_api_chat(provider: String, model: String) -> void:
	if _start_screen and _start_screen.has_method("show_loading"):
		_start_screen.show_loading(_t("connecting"))
	_request_chats("new", {"kind": "api", "provider": provider, "model": model})


func _on_api_payload(kind: String, json: Dictionary) -> void:
	if _start_screen == null:
		return
	# Проверка подключения разбирается ПЕРВОЙ, до общей обработки ошибок.
	# Неудачная проверка — это обычный, ожидаемый ответ (ok=false + причина), и
	# уходить по ветке ошибок нельзя: строка «проверяю подключение…» так и
	# осталась бы на экране, а результат проверки не дошёл бы до неё никогда.
	if kind == "api_test":
		if _start_screen.has_method("set_api_test_result"):
			_start_screen.set_api_test_result(json)
		if json.has("error"):
			_log_error(str(json["error"]))
		return
	var failed := json.has("error")
	if failed and kind != "api_scan":
		# Ошибку показываем в статусной строке экрана настроек, а не в чате:
		# пользователь сейчас смотрит именно на форму.
		#
		# ОБХОД ЗА СПИСКАМИ МОДЕЛЕЙ — ИСКЛЮЧЕНИЕ. Его никто не просил: он идёт
		# сам при открытии раздела. Красная строка на весь экран из-за того, что
		# автоматическое действие не удалось (например, сервер старее панели и
		# отвечает 404 на новый маршрут), выглядит как поломка плагина в ответ на
		# простое открытие настроек. Про эту неудачу расскажет сам экран — и
		# только если пользователь просил обход кнопкой (set_api_scan_result).
		_notify(str(json["error"]), "error")
	# Настройки применяем ДАЖЕ при ошибке, если сервер их прислал. Отказ
	# провайдера приходит вместе с полным ответом, где уже записано, что список
	# моделей получить не удалось и почему; без этого причина не доехала бы до
	# карточки провайдера, и там осталось бы «список ещё не загружался» — то
	# есть плагин выглядел бы просто ничего не делающим.
	if json.has("providers") and _start_screen.has_method("set_api_settings"):
		_start_screen.set_api_settings(json)
	if not failed and kind == "api_models" and _start_screen.has_method("set_api_models"):
		# models_info — записи {id, free}; models — прежний список строк. Отдаём
		# оба: экран возьмёт записи, если сервер их присылает, и не сломается со
		# старым сервером, где их нет.
		_start_screen.set_api_models(str(json.get("provider", "")),
			json.get("models", []), json.get("models_info", []))
	if kind == "api_scan" and _start_screen.has_method("set_api_scan_result"):
		# Вызывается и при ошибке: экран обязан узнать, что обход закончился,
		# иначе строка «обновляю списки моделей» останется висеть навсегда.
		_start_screen.set_api_scan_result(json)
	if _pending_view == "api":
		_pending_view = ""
		if _start_screen.has_method("show_api"):
			_start_screen.show_api()
	if _chat_model_pick_wanted and kind == "api_providers":
		# Ответ на нажатие кнопки выбора нейросети в чате. Окно открываем только
		# когда настройки действительно пришли: пустое окно с одной кнопкой
		# «закрыть» — не ответ на нажатие, а причина неудачи уже показана строкой
		# выше. Подпись кнопки («спрашиваю список…») возвращает на место
		# _push_api_switch_target ниже — она вызывается в любом случае.
		_chat_model_pick_wanted = false
		if not failed and _start_screen.has_method("open_chat_provider_pick"):
			_start_screen.open_chat_provider_pick()
	# Экран сам про открытый чат не знает — сообщаем ему модель, чтобы он решил,
	# показывать ли кнопку «продолжить открытый чат на этой модели». Делается
	# здесь, потому что настройки API открываются именно этим ответом.
	_push_api_switch_target()


func _push_api_switch_target() -> void:
	# Модель ОТКРЫТОГО чата по ключу или "" — тогда продолжать нечего и кнопки
	# смены модели не будет. Пустую строку отправляем так же обязательно, как
	# непустую: иначе кнопка осталась бы от прошлого чата и предложила бы
	# сменить модель у браузерного чата, где её вообще нет.
	#
	# Здесь же обновляется подпись кнопки выбора нейросети в самом чате: обе
	# зависят от одного и того же — от модели открытого чата, и разводить их по
	# разным местам значит однажды обновить только одну.
	_refresh_chat_model_btn()
	if _start_screen == null or not _start_screen.has_method("set_api_switch_target"):
		return
	_start_screen.set_api_switch_target(_api_chat_model)


func _on_api_chat_model(provider: String, model: String) -> void:
	# Продолжить ОТКРЫТЫЙ чат на другой модели. Отдельный обработчик от
	# _on_start_new_api_chat: тот создаёт новый чат с пустой историей, этот
	# сохраняет переписку.
	_request_chats("chat_model", {"provider": provider, "model": model})


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
# ---------------------------------------------------------------------------
# v57: экспериментальные настройки — mini-lich (локальная нейросеть-помощник).
# Галочка по умолчанию выключена; состояние хранит сервер (settings.json проекта).
# ---------------------------------------------------------------------------

func _on_settings_pressed() -> void:
	var T = _T()
	if _settings_dialog == null:
		_settings_dialog = AcceptDialog.new()
		# v60: без TabContainer — с одной вкладкой он давал два одинаковых
		# заголовка (таб + внутренняя надпись) и лишнюю стрелку вкладок сверху.
		# Простой список: заголовок + подпись «ниже — экспериментальные настройки» + сами настройки.
		# Содержимое обёрнуто в панель со стилем аддона, чтобы окно выглядело
		# так же, как карточки чата, а не как голый диалог Godot.
		var wrap := PanelContainer.new()
		if T:
			wrap.add_theme_stylebox_override("panel", T.panel_style("agent"))
		var box := VBoxContainer.new()
		box.add_theme_constant_override("separation", 6)
		wrap.add_child(box)
		_settings_exp_header = Label.new()
		_settings_exp_header.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_settings_exp_header.custom_minimum_size = Vector2(360, 0)
		if T:
			_settings_exp_header.add_theme_color_override("font_color", T.color("accent"))
		box.add_child(_settings_exp_header)
		box.add_child(HSeparator.new())
		_minilich_check = CheckBox.new()
		_minilich_check.button_pressed = false
		_minilich_check.toggled.connect(_on_minilich_toggled)
		box.add_child(_minilich_check)
		_minilich_status_label = Label.new()
		_minilich_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_minilich_status_label.custom_minimum_size = Vector2(360, 0)
		if T:
			_minilich_status_label.add_theme_color_override("font_color", T.color("dim"))
		box.add_child(_minilich_status_label)
		_minilich_train_check = CheckBox.new()
		_minilich_train_check.button_pressed = false
		_minilich_train_check.toggled.connect(_on_train_mode_toggled)
		box.add_child(_minilich_train_check)
		_minilich_train_warn = Label.new()
		_minilich_train_warn.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_minilich_train_warn.custom_minimum_size = Vector2(360, 0)
		# Цвет предупреждения — из темы редактора вместо захардкоженного.
		if T:
			_minilich_train_warn.add_theme_color_override("font_color", T.color("warning"))
		_minilich_train_warn.visible = false
		box.add_child(_minilich_train_warn)
		box.add_child(HSeparator.new())
		_minilich_repos_edit = LineEdit.new()
		_minilich_repos_edit.custom_minimum_size = Vector2(360, 0)
		if T:
			T.style_input(_minilich_repos_edit)
		box.add_child(_minilich_repos_edit)
		_minilich_github_btn = Button.new()
		_minilich_github_btn.pressed.connect(_on_github_fetch_pressed)
		if T:
			T.style_button(_minilich_github_btn, "accent", false)
			_minilich_github_btn.icon = T.first_icon(["ExternalLink", "Load"])
		box.add_child(_minilich_github_btn)
		_minilich_github_label = Label.new()
		_minilich_github_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_minilich_github_label.custom_minimum_size = Vector2(360, 0)
		if T:
			_minilich_github_label.add_theme_color_override("font_color", T.color("dim"))
		box.add_child(_minilich_github_label)
		# Раздел редких инструментов. Раньше он открывался кнопкой
		# «⚙️ Дополнительно» прямо под полем ввода — то место занял выбор
		# нейросети для чата (он нужен в каждом сообщении, а эти инструменты —
		# раз в месяц). Узел ПЕРЕНОСИМ целиком, а не пересобираем: его кнопки уже
		# созданы и подключены в _ready (переинициализация, ошибки запуска,
		# справочник API, живой ввод, остановка плана), и вторая копия развела бы
		# два набора обработчиков на одни и те же действия.
		if advanced_box and advanced_box.get_parent():
			box.add_child(HSeparator.new())
			_settings_adv_header = Label.new()
			if T:
				_settings_adv_header.add_theme_color_override("font_color", T.color("accent"))
			box.add_child(_settings_adv_header)
			advanced_box.get_parent().remove_child(advanced_box)
			box.add_child(advanced_box)
			advanced_box.visible = true
		_settings_dialog.add_child(wrap)
		add_child(_settings_dialog)
	_settings_dialog.title = _t("settings_title")
	_settings_exp_header.text = _t("experimental_hdr") + ":"
	_minilich_check.text = _t("minilich_toggle")
	_minilich_train_check.text = _t("train_mode_toggle")
	_minilich_train_warn.text = _t("train_mode_warn")
	if _minilich_repos_edit:
		_minilich_repos_edit.placeholder_text = _t("github_repos_hint")
	if _minilich_github_btn:
		_minilich_github_btn.text = _t("github_fetch_btn")
	if _minilich_github_label:
		_minilich_github_label.text = ""
	if _settings_adv_header:
		_settings_adv_header.text = _t("advanced_show") + ":"
	_minilich_status_label.text = _t("minilich_loading")
	_settings_dialog.popup_centered()
	# Статус запрашиваем БЕЗ автозапуска сервера — просто открытие настроек
	# не должно поднимать сервер.
	_request_chats("minilich_status", {}, false)


func _on_train_mode_toggled(pressed: bool) -> void:
	# v69: кнопка «Обучение модели» заменена галочкой. Галочка стоит — теневой
	# режим: mini-lich учится, а сцены применяет большая модель. Снята — боевой
	# режим: mini-lich чинит сам (каждый результат обязан пройти линтер).
	if _minilich_train_warn:
		_minilich_train_warn.visible = pressed
	_minilich_set_pending = true
	# v70: шлём только training_mode — галочку mini-lich не трогаем (гонка со старым статусом могла выключить обучение)
	_request_chats("minilich_set", {"training_mode": pressed})


func _on_minilich_toggled(pressed: bool) -> void:
	if _minilich_status_label:
		_minilich_status_label.text = _t("minilich_loading")
	# Ставим флаг до ответа сервера — иначе устаревший minilich_status, ожидавший ответа в очереди, сбрасывает галочку обратно.
	_minilich_set_pending = true
	# Здесь автозапуск разрешён: пользователь явно меняет настройку.
	_request_chats("minilich_set", {"enabled": pressed})


func _on_github_fetch_pressed() -> void:
	# v81: сбор обучающих пар со сцен GitHub-репозиториев (только Godot 4, format=3).
	var repos := ""
	if _minilich_repos_edit:
		repos = _minilich_repos_edit.text.strip_edges()
	if repos == "":
		if _minilich_github_label:
			_minilich_github_label.text = _t("github_repos_empty")
		return
	if _minilich_github_label:
		_minilich_github_label.text = _t("github_fetch_started")
	_request_chats("minilich_github", {"repos": repos})


func _on_minilich_payload(kind: String, json: Dictionary) -> void:
	if kind == "minilich_set":
		_minilich_set_pending = false
	if json.has("error"):
		if _minilich_status_label:
			_minilich_status_label.text = str(json.get("error", ""))
		return
	# Статус-запрос мог уйти до ответа на ещё не завершённый minilich_set — не трогаем галочку его устаревшим значением.
	if _minilich_check and not (kind == "minilich_status" and _minilich_set_pending):
		_minilich_check.set_pressed_no_signal(bool(json.get("enabled", false)))
	if _minilich_train_check and not (kind == "minilich_status" and _minilich_set_pending):
		var _tm := bool(json.get("training_mode", true))
		_minilich_train_check.set_pressed_no_signal(_tm)
		if _minilich_train_warn:
			_minilich_train_warn.visible = _tm
	if _minilich_status_label:
		if not bool(json.get("enabled", false)):
			_minilich_status_label.text = _t("train_console_disabled")
		else:
			_minilich_status_label.text = _minilich_status_text(json)


func _minilich_status_text(json: Dictionary) -> String:
	var mb := float(json.get("disk_bytes", 0)) / 1048576.0
	var loss = json.get("last_loss")
	var loss_s := "—"
	if loss != null:
		loss_s = "%.3f" % float(loss)
	var active_s := _t("ml_yes") if bool(json.get("training_active", false)) else _t("ml_no")
	return _t("minilich_status_fmt") % [int(json.get("examples", 0)), int(json.get("train_step", 0)), loss_s, "%.1f" % mb, active_s]


# ---------------------------------------------------------------------------
# Безопасное переименование файла с обновлением ссылок в проекте.
# ---------------------------------------------------------------------------

func _on_safe_rename_pressed() -> void:
	open_safe_rename()


func open_safe_rename(prefill_path: String = "") -> void:
	_ensure_safe_rename_dialog()
	var initial_path := prefill_path
	if initial_path.is_empty():
		var se := EditorInterface.get_script_editor()
		if se and se.get_current_script():
			initial_path = se.get_current_script().resource_path
		elif EditorInterface.get_edited_scene_root():
			initial_path = EditorInterface.get_edited_scene_root().scene_file_path
	if initial_path != "" and initial_path.begins_with("res://"):
		_safe_rename_old_edit.text = initial_path
		_safe_rename_new_edit.text = initial_path
	else:
		_safe_rename_old_edit.text = ""
		_safe_rename_new_edit.text = ""
	_safe_rename_status_label.text = ""
	_safe_rename_prepared = {}
	_safe_rename_dialog.popup_centered(Vector2(600, 320))


func _ensure_safe_rename_dialog() -> void:
	if _safe_rename_dialog != null:
		return
	var T = _T()
	_safe_rename_dialog = ConfirmationDialog.new()
	_safe_rename_dialog.title = _t("safe_rename_title")
	_safe_rename_dialog.get_ok_button().text = _t("safe_rename_apply")
	_safe_rename_dialog.get_cancel_button().text = _t("back")
	_safe_rename_dialog.add_button(_t("safe_rename_preview"), true, "preview")
	_safe_rename_dialog.custom_action.connect(func(action: String):
		if action == "preview":
			_on_safe_rename_preview()
	)
	_safe_rename_dialog.confirmed.connect(_on_safe_rename_apply)

	var wrap := PanelContainer.new()
	if T:
		wrap.add_theme_stylebox_override("panel", T.panel_style("agent"))
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	wrap.add_child(box)

	var desc_lbl := Label.new()
	desc_lbl.text = _t("safe_rename_desc")
	desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	desc_lbl.custom_minimum_size = Vector2(560, 0)
	if T:
		desc_lbl.add_theme_color_override("font_color", T.color("dim"))
	box.add_child(desc_lbl)
	box.add_child(HSeparator.new())

	# Old path row
	var old_row := HBoxContainer.new()
	var old_lbl := Label.new()
	old_lbl.text = _t("safe_rename_old")
	old_lbl.custom_minimum_size = Vector2(130, 0)
	old_row.add_child(old_lbl)
	_safe_rename_old_edit = LineEdit.new()
	_safe_rename_old_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_safe_rename_old_edit.placeholder_text = "res://scripts/my_script.gd"
	if T:
		T.style_input(_safe_rename_old_edit)
	old_row.add_child(_safe_rename_old_edit)
	var browse_btn := Button.new()
	browse_btn.text = _t("safe_rename_browse")
	if T:
		T.style_button(browse_btn, "neutral")
	browse_btn.pressed.connect(_on_safe_rename_browse)
	old_row.add_child(browse_btn)
	box.add_child(old_row)

	# New path row
	var new_row := HBoxContainer.new()
	var new_lbl := Label.new()
	new_lbl.text = _t("safe_rename_new")
	new_lbl.custom_minimum_size = Vector2(130, 0)
	new_row.add_child(new_lbl)
	_safe_rename_new_edit = LineEdit.new()
	_safe_rename_new_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_safe_rename_new_edit.placeholder_text = "res://scripts/new_script.gd"
	if T:
		T.style_input(_safe_rename_new_edit)
	new_row.add_child(_safe_rename_new_edit)
	box.add_child(new_row)

	# Options
	_safe_rename_refs_check = CheckBox.new()
	_safe_rename_refs_check.text = _t("safe_rename_refs")
	_safe_rename_refs_check.button_pressed = true
	box.add_child(_safe_rename_refs_check)

	_safe_rename_addons_check = CheckBox.new()
	_safe_rename_addons_check.text = _t("safe_rename_addons")
	_safe_rename_addons_check.button_pressed = false
	box.add_child(_safe_rename_addons_check)

	# Status label
	_safe_rename_status_label = Label.new()
	_safe_rename_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_safe_rename_status_label.custom_minimum_size = Vector2(560, 0)
	if T:
		_safe_rename_status_label.add_theme_color_override("font_color", T.color("accent"))
	box.add_child(_safe_rename_status_label)

	_safe_rename_dialog.add_child(wrap)
	add_child(_safe_rename_dialog)


func _on_safe_rename_browse() -> void:
	if _safe_rename_file_dialog == null:
		_safe_rename_file_dialog = FileDialog.new()
		_safe_rename_file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		_safe_rename_file_dialog.access = FileDialog.ACCESS_RESOURCES
		_safe_rename_file_dialog.filters = PackedStringArray([
			"*.gd ; GDScript Files",
			"*.tscn ; Godot Scenes",
			"*.tres ; Godot Resources",
			"* ; All Files"
		])
		_safe_rename_file_dialog.file_selected.connect(func(path: String):
			if _safe_rename_old_edit:
				_safe_rename_old_edit.text = path
			if _safe_rename_new_edit and _safe_rename_new_edit.text.is_empty():
				_safe_rename_new_edit.text = path
		)
		add_child(_safe_rename_file_dialog)
	_safe_rename_file_dialog.popup_centered_ratio(0.7)


func _on_safe_rename_preview() -> void:
	if _is_network_busy: return
	if _safe_rename_old_edit == null or _safe_rename_new_edit == null: return
	var old_p := _safe_rename_old_edit.text.strip_edges()
	var new_p := _safe_rename_new_edit.text.strip_edges()
	if old_p.is_empty() or new_p.is_empty():
		_safe_rename_status_label.text = _t("safe_rename_no_paths")
		return
	if old_p == new_p:
		_safe_rename_status_label.text = "Старый и новый пути совпадают."
		return
	_safe_rename_status_label.text = "Анализ ссылок..."
	var body = {
		"old_path": old_p,
		"new_path": new_p,
		"update_references": _safe_rename_refs_check.button_pressed if _safe_rename_refs_check else true,
		"allow_addons": _safe_rename_addons_check.button_pressed if _safe_rename_addons_check else false,
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()),
	}
	_pending_request_kind = "safe_rename_preview"
	_set_ui_busy(true)
	http_request.set_http_proxy("", 0)
	var err = http_request.request(REFACTOR_FILE_PREVIEW_URL, _json_headers(), HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_set_ui_busy(false)
		_safe_rename_status_label.text = "Ошибка сетевого запроса."


func _on_safe_rename_apply() -> void:
	if _is_network_busy: return
	if _safe_rename_old_edit == null or _safe_rename_new_edit == null: return
	var old_p := _safe_rename_old_edit.text.strip_edges()
	var new_p := _safe_rename_new_edit.text.strip_edges()
	if old_p.is_empty() or new_p.is_empty():
		_safe_rename_status_label.text = _t("safe_rename_no_paths")
		return
	if old_p == new_p:
		_safe_rename_status_label.text = "Старый и новый пути совпадают."
		return
	var targets: Array[String] = [old_p, new_p]
	if _safe_rename_prepared.has("affected_paths"):
		for p in _safe_rename_prepared["affected_paths"]:
			if not targets.has(str(p)):
				targets.append(str(p))
	var dirty := _dirty_open_scripts(PackedStringArray(targets))
	if not dirty.is_empty():
		_safe_rename_status_label.text = "Сначала сохраните изменённые вкладки: " + ", ".join(dirty)
		return
	_safe_rename_status_label.text = "Применение переименования..."
	var body = {
		"old_path": old_p,
		"new_path": new_p,
		"update_references": _safe_rename_refs_check.button_pressed if _safe_rename_refs_check else true,
		"allow_addons": _safe_rename_addons_check.button_pressed if _safe_rename_addons_check else false,
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()),
	}
	_pending_request_kind = "safe_rename_apply"
	_set_ui_busy(true)
	http_request.set_http_proxy("", 0)
	var err = http_request.request(REFACTOR_FILE_APPLY_URL, _json_headers(), HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_set_ui_busy(false)
		_safe_rename_status_label.text = "Ошибка отправки запроса на переименование."


func _on_safe_node_rename_pressed() -> void:
	open_safe_node_rename()


func open_safe_node_rename(prefill_scene: String = "", prefill_node: String = "") -> void:
	_ensure_safe_node_rename_dialog()
	var initial_scene := prefill_scene
	if initial_scene.is_empty():
		var edited_root = EditorInterface.get_edited_scene_root()
		if edited_root and not edited_root.scene_file_path.is_empty():
			initial_scene = edited_root.scene_file_path
	if _safe_node_rename_scene_edit:
		_safe_node_rename_scene_edit.text = initial_scene
	if _safe_node_rename_node_edit:
		_safe_node_rename_node_edit.text = prefill_node
	if _safe_node_rename_new_edit:
		_safe_node_rename_new_edit.text = prefill_node
	if _safe_node_rename_status_label:
		_safe_node_rename_status_label.text = ""
	_safe_node_rename_prepared = {}
	_safe_node_rename_dialog.popup_centered(Vector2(600, 360))


func _ensure_safe_node_rename_dialog() -> void:
	if _safe_node_rename_dialog != null:
		return
	var T = _T()
	_safe_node_rename_dialog = ConfirmationDialog.new()
	_safe_node_rename_dialog.title = _t("safe_node_rename_title")
	_safe_node_rename_dialog.get_ok_button().text = _t("safe_node_rename_apply")
	_safe_node_rename_dialog.get_cancel_button().text = _t("back")
	_safe_node_rename_dialog.add_button(_t("safe_node_rename_preview"), true, "preview")
	_safe_node_rename_dialog.custom_action.connect(func(action: String):
		if action == "preview":
			_on_safe_node_rename_preview()
	)
	_safe_node_rename_dialog.confirmed.connect(_on_safe_node_rename_apply)

	var wrap := MarginContainer.new()
	wrap.add_theme_constant_override("margin_left", 12)
	wrap.add_theme_constant_override("margin_top", 12)
	wrap.add_theme_constant_override("margin_right", 12)
	wrap.add_theme_constant_override("margin_bottom", 12)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	wrap.add_child(box)

	var desc_lbl := Label.new()
	desc_lbl.text = _t("safe_node_rename_desc")
	desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	desc_lbl.custom_minimum_size = Vector2(560, 0)
	if T:
		desc_lbl.add_theme_color_override("font_color", T.color("muted"))
	box.add_child(desc_lbl)

	# Scene path row
	var scene_row := HBoxContainer.new()
	var scene_lbl := Label.new()
	scene_lbl.text = _t("safe_node_rename_scene")
	scene_lbl.custom_minimum_size = Vector2(140, 0)
	scene_row.add_child(scene_lbl)
	_safe_node_rename_scene_edit = LineEdit.new()
	_safe_node_rename_scene_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_safe_node_rename_scene_edit.placeholder_text = "res://scenes/player.tscn"
	if T:
		T.style_input(_safe_node_rename_scene_edit)
	scene_row.add_child(_safe_node_rename_scene_edit)
	var browse_btn := Button.new()
	browse_btn.text = _t("safe_node_rename_browse")
	if T:
		T.style_button(browse_btn, "neutral")
	browse_btn.pressed.connect(_on_safe_node_rename_scene_browse)
	scene_row.add_child(browse_btn)
	box.add_child(scene_row)

	# Target node row
	var node_row := HBoxContainer.new()
	var node_lbl := Label.new()
	node_lbl.text = _t("safe_node_rename_node")
	node_lbl.custom_minimum_size = Vector2(140, 0)
	node_row.add_child(node_lbl)
	_safe_node_rename_node_edit = LineEdit.new()
	_safe_node_rename_node_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_safe_node_rename_node_edit.placeholder_text = "Gun"
	if T:
		T.style_input(_safe_node_rename_node_edit)
	node_row.add_child(_safe_node_rename_node_edit)
	box.add_child(node_row)

	# New name row
	var new_row := HBoxContainer.new()
	var new_lbl := Label.new()
	new_lbl.text = _t("safe_node_rename_new")
	new_lbl.custom_minimum_size = Vector2(140, 0)
	new_row.add_child(new_lbl)
	_safe_node_rename_new_edit = LineEdit.new()
	_safe_node_rename_new_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_safe_node_rename_new_edit.placeholder_text = "Weapon"
	if T:
		T.style_input(_safe_node_rename_new_edit)
	new_row.add_child(_safe_node_rename_new_edit)
	box.add_child(new_row)

	# Options
	_safe_node_rename_addons_check = CheckBox.new()
	_safe_node_rename_addons_check.text = _t("safe_node_rename_addons")
	_safe_node_rename_addons_check.button_pressed = false
	box.add_child(_safe_node_rename_addons_check)

	# Status label
	_safe_node_rename_status_label = Label.new()
	_safe_node_rename_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_safe_node_rename_status_label.custom_minimum_size = Vector2(560, 0)
	if T:
		_safe_node_rename_status_label.add_theme_color_override("font_color", T.color("accent"))
	box.add_child(_safe_node_rename_status_label)

	_safe_node_rename_dialog.add_child(wrap)
	add_child(_safe_node_rename_dialog)


func _on_safe_node_rename_scene_browse() -> void:
	if _safe_node_rename_scene_dialog == null:
		_safe_node_rename_scene_dialog = FileDialog.new()
		_safe_node_rename_scene_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		_safe_node_rename_scene_dialog.access = FileDialog.ACCESS_RESOURCES
		_safe_node_rename_scene_dialog.filters = PackedStringArray([
			"*.tscn ; Godot Scenes",
			"* ; All Files"
		])
		_safe_node_rename_scene_dialog.file_selected.connect(func(path: String):
			if _safe_node_rename_scene_edit:
				_safe_node_rename_scene_edit.text = path
		)
		add_child(_safe_node_rename_scene_dialog)
	_safe_node_rename_scene_dialog.popup_centered_ratio(0.7)


func _on_safe_node_rename_preview() -> void:
	if _is_network_busy: return
	if _safe_node_rename_scene_edit == null or _safe_node_rename_node_edit == null or _safe_node_rename_new_edit == null: return
	var scene_p := _safe_node_rename_scene_edit.text.strip_edges()
	var node_p := _safe_node_rename_node_edit.text.strip_edges()
	var new_n := _safe_node_rename_new_edit.text.strip_edges()
	if scene_p.is_empty() or node_p.is_empty() or new_n.is_empty():
		_safe_node_rename_status_label.text = _t("safe_node_rename_no_paths")
		return
	if node_p == new_n:
		_safe_node_rename_status_label.text = "Старое и новое имя совпадают."
		return
	_safe_node_rename_status_label.text = "Анализ ссылок узла..."
	var body = {
		"scene": scene_p,
		"node_path": node_p,
		"new_name": new_n,
		"allow_addons": _safe_node_rename_addons_check.button_pressed if _safe_node_rename_addons_check else false,
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()),
	}
	_pending_request_kind = "safe_node_rename_preview"
	_set_ui_busy(true)
	http_request.set_http_proxy("", 0)
	var err = http_request.request(REFACTOR_NODE_PREVIEW_URL, _json_headers(), HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_set_ui_busy(false)
		_safe_node_rename_status_label.text = "Ошибка сетевого запроса."


func _on_safe_node_rename_apply() -> void:
	if _is_network_busy: return
	if _safe_node_rename_scene_edit == null or _safe_node_rename_node_edit == null or _safe_node_rename_new_edit == null: return
	var scene_p := _safe_node_rename_scene_edit.text.strip_edges()
	var node_p := _safe_node_rename_node_edit.text.strip_edges()
	var new_n := _safe_node_rename_new_edit.text.strip_edges()
	if scene_p.is_empty() or node_p.is_empty() or new_n.is_empty():
		_safe_node_rename_status_label.text = _t("safe_node_rename_no_paths")
		return
	if node_p == new_n:
		_safe_node_rename_status_label.text = "Старое и новое имя совпадают."
		return
	var targets: Array[String] = [scene_p]
	if _safe_node_rename_prepared.has("affected_paths"):
		for p in _safe_node_rename_prepared["affected_paths"]:
			if not targets.has(str(p)):
				targets.append(str(p))
	var dirty := _dirty_open_scripts(PackedStringArray(targets))
	if not dirty.is_empty():
		_safe_node_rename_status_label.text = "Сначала сохраните изменённые вкладки: " + ", ".join(dirty)
		return
	_safe_node_rename_status_label.text = "Применение переименования узла..."
	var body = {
		"scene": scene_p,
		"node_path": node_p,
		"new_name": new_n,
		"allow_addons": _safe_node_rename_addons_check.button_pressed if _safe_node_rename_addons_check else false,
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(get_script().resource_path.get_base_dir()),
	}
	_pending_request_kind = "safe_node_rename_apply"
	_set_ui_busy(true)
	http_request.set_http_proxy("", 0)
	var err = http_request.request(REFACTOR_NODE_APPLY_URL, _json_headers(), HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_set_ui_busy(false)
		_safe_node_rename_status_label.text = "Ошибка отправки запроса на переименование узла."
