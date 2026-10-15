@tool
extends RefCounted

# Модуль agent_panel_part1: методы вынесены «пилой» split_gd из agent_panel.gd.
# Реализация живёт ЗДЕСЬ; в доноре на месте метода — тонкая обёртка,
# поэтому connect()/call() по исходным именам продолжают работать.
# Тело работает через параметр panel: к членам донора — panel.<член>,
# к другим методам донора — panel.<метод> (через его обёртку).

# --- константы, скопированные из донора (неизменяемы) ---
# Адрес сервера, токен и заголовки живут в AgentServer — единственном месте,
# где плагин знает про локальный сервер. Здесь только имена маршрутов.
const CHAT_URL = AgentServer.URL_CHAT
const INIT_URL = AgentServer.URL_INIT
const CONFIRM_URL = AgentServer.URL_CHAT_CONFIRM_ACTION
const EDITOR_ACTION_RESULT_URL = AgentServer.URL_CHAT_EDITOR_ACTION_RESULT
const RUNTIME_RESULT_URL = AgentServer.URL_CHAT_RUNTIME_INSPECT_RESULT
const RUNTIME_CHECK_RESULT_URL = AgentServer.URL_CHAT_RUNTIME_CHECK_RESULT
const SEND_LOG_URL = AgentServer.URL_PROJECT_SEND_LOG_ERRORS
const PLAN_STEP_URL = AgentServer.URL_CHAT_PLAN_STEP
const CHAT_STOP_URL = AgentServer.URL_CHAT_STOP
const LIVE_INPUT_URL = AgentServer.URL_CHAT_LIVE_INPUT
const SAFE_RENAME_SETTING_FILE := "user://godot_agent_safe_rename.txt"
# Галочка «переименовывать недоказанные ссылки». По умолчанию СТОИТ: значит
# ссылки, которые сервер не смог доказать, тоже переименовываются, но каждая
# попадает в отчёт с причиной. Снятие возвращает прежнее строгое поведение,
# где одна недоказанная ссылка отменяет всё переименование.
# Хранится в user:// рядом с прочими переключателями, поэтому переживает
# перезапуск редактора.
const RENAME_UNVERIFIED_SETTING_FILE := "user://godot_agent_rename_unverified.txt"
# Выбор режима отказа для переименований. По умолчанию strict: он отказывает при
# любой недоказанной ссылке и при динамической ссылке по строке. probable эти
# блокировки снимает, поэтому включать его можно только осознанно — поэтому он
# НЕ входит в дефолт, даже когда галочка недоказанных ссылок стоит.
const RENAME_MODE_SETTING_FILE := "user://godot_agent_rename_mode.txt"
# Explicit access policy for project/addon edits. allow_addons is durable;
# allow_self_edit is ephemeral and resets to false on every panel load.
const POLICY_SETTING_FILE := "user://godot_agent_policy.txt"
# v88.11: живой ввод — текст из поля панели зеркалируется в поле ввода сайта
# по мере набора (тротлинг-таймер + отдельный HTTPRequest, настройка в
# «Расширенных»; сервер вставляет текст без отправки).
const LIVE_INPUT_SETTING_FILE := "user://godot_agent_live_input.txt"
## Сколько мест переименования показываем галочками в карточке. Ограничение
## только на показ: снятые места адресуются своим id, а не порядковым номером.
const RENAME_USAGE_LIST_LIMIT := 40

## Вопрос из контекстного меню: «Спросить агента» по узлу или по файлу.
##
## Вызывает точка входа через _handle_command — напрямую, без обратной
## связи: панель ничего не знает о маршрутизаторе, знает только свои узлы.
##
## Текст, который пользователь уже набрал в поле ввода, становится самим
## вопросом и не теряется. Если поле пустое, подставляется вопрос по умолчанию
## для типа выбора. Отправка идёт через обычный путь _on_send_pressed, а не
## отдельным запросом: тогда работают все её проверки (занята сеть, не
## разобрано предыдущее действие) и разметка сообщений в чате.
static func handle_context_ask(panel, what: String, paths: PackedStringArray) -> void:
	if panel.input_field == null or panel._view == null:
		push_warning("[Godot Agent] Панель не готова принять вопрос из меню.")
		return
	if paths.is_empty():
		push_warning("[Godot Agent] В контекстном меню ничего не выбрано.")
		return
	# Файл отличается от узла по виду: у сцены это путь от корня res://,
	# у узла — путь внутри сцены. По признаку решаем, о чём спрашивать.
	var is_file := false
	for p in paths:
		if str(p).begins_with("res://"):
			is_file = true
			break
	var question = panel.input_field.text.strip_edges()
	if question.is_empty():
		question = panel._t("ctx_ask_file_default") if is_file else panel._t("ctx_ask_node_default")
	var lines: Array[String] = [question, ""]
	lines.append(panel._t("ctx_ask_selection"))
	for p in paths:
		lines.append("- " + str(p))
	panel.input_field.text = "\n".join(lines)
	panel.input_field.grab_focus()
	panel._on_send_pressed()

static func set_editor_plugin(panel, plugin: EditorPlugin) -> void:
	panel._editor_plugin = plugin
	if plugin and plugin.has_method("_ensure_fs_dock_connected"):
		plugin.call("_ensure_fs_dock_connected")
	# ЗАДАЧА 1: Ctrl+S пользователя — тоже сохранение. Без этой подписки сцена,
	# которую пользователь сохранил вручную, навсегда оставалась бы «грязной».
	if plugin and not plugin.scene_saved.is_connected(panel._on_editor_scene_saved):
		plugin.scene_saved.connect(panel._on_editor_scene_saved)
	var gate_path: String = panel.get_script().resource_path.get_base_dir() + "/agent_mutation_gate.gd"
	if FileAccess.file_exists(gate_path):
		var gate_script = load(gate_path)
		if gate_script:
			panel._mutation_gate = gate_script.new()
			panel._mutation_gate.configure(plugin)
	var executor_path: String = panel.get_script().resource_path.get_base_dir() + "/agent_scene_executor.gd"
	if FileAccess.file_exists(executor_path):
		var executor_script = load(executor_path)
		if executor_script:
			panel._scene_executor = executor_script.new()
			panel._scene_executor.configure(plugin)
			if panel._mutation_gate and panel._scene_executor.has_method("set_mutation_gate"):
				panel._scene_executor.call("set_mutation_gate", panel._mutation_gate)
	var settings_executor_path: String = panel.get_script().resource_path.get_base_dir() + "/agent_project_settings_executor.gd"
	if FileAccess.file_exists(settings_executor_path):
		var settings_executor_script = load(settings_executor_path)
		if settings_executor_script:
			panel._project_settings_executor = settings_executor_script.new()
			panel._project_settings_executor.configure(plugin)
			if panel._mutation_gate and panel._project_settings_executor.has_method("set_mutation_gate"):
				panel._project_settings_executor.call("set_mutation_gate", panel._mutation_gate)
	var resource_executor_path: String = panel.get_script().resource_path.get_base_dir() + "/agent_resource_executor.gd"
	if FileAccess.file_exists(resource_executor_path):
		var resource_executor_script = load(resource_executor_path)
		if resource_executor_script:
			panel._resource_executor = resource_executor_script.new()
			panel._resource_executor.configure(plugin)
			if panel._mutation_gate and panel._resource_executor.has_method("set_mutation_gate"):
				panel._resource_executor.call("set_mutation_gate", panel._mutation_gate)

static func set_runtime_debugger(panel, debugger) -> void:
	panel._runtime_debugger = debugger
	if panel._runtime_debugger == null:
		return
	panel._runtime_status = panel._runtime_debugger.get_status()
	panel._runtime_debugger.status_changed.connect(panel._on_runtime_status_changed)
	panel._runtime_debugger.inspect_completed.connect(panel._on_runtime_inspect_completed)
	panel._runtime_debugger.check_completed.connect(panel._on_runtime_check_completed)
	panel._runtime_timeout_timer = Timer.new()
	panel._runtime_timeout_timer.one_shot = true
	panel.add_child(panel._runtime_timeout_timer)
	panel._runtime_timeout_timer.timeout.connect(panel._on_runtime_inspect_timeout)

static func _on_runtime_status_changed(panel, status: Dictionary) -> void:
	panel._runtime_status = status.duplicate(true)

static func _start_runtime_inspect(panel, envelope: Dictionary) -> void:
	panel._pending_runtime_request = (envelope.get("runtime_request", {}) as Dictionary).duplicate(true)
	var result := {"ok": false, "status": "bridge_unavailable"}
	if panel._runtime_debugger:
		result = panel._runtime_debugger.inspect(panel._pending_runtime_request)
	if not bool(result.get("ok", false)):
		panel._send_runtime_result(str(result.get("status", "bridge_unavailable")), {})
		return
	panel._runtime_timeout_timer.start(maxf(0.1, float(panel._pending_runtime_request.get("timeout_ms", 3000)) / 1000.0))
	panel._view.add_system("Получаю read-only снимок запущенной игры...")

static func _on_runtime_inspect_completed(panel, result: Dictionary) -> void:
	if panel._pending_runtime_request.is_empty():
		return
	if str(result.get("request_id", "")) != str(panel._pending_runtime_request.get("request_id", "")):
		return
	if panel._runtime_timeout_timer:
		panel._runtime_timeout_timer.stop()
	panel._send_runtime_result(str(result.get("status", "protocol_error")), result.get("snapshot", {}))

static func _on_runtime_inspect_timeout(panel) -> void:
	if not panel._pending_runtime_check.is_empty():
		if panel._runtime_debugger:
			panel._runtime_debugger.cancel_pending("timeout")
		return
	if panel._runtime_debugger:
		panel._runtime_debugger.cancel_pending("timeout")

static func _send_runtime_result(panel, status: String, snapshot) -> void:
	if panel._pending_runtime_request.is_empty():
		return
	var body = {
		"request_id": str(panel._pending_runtime_request.get("request_id", "")),
		"result_token": str(panel._pending_runtime_request.get("result_token", "")),
		"session_id": int(panel._pending_runtime_request.get("session_id", -1)),
		"run_id": str(panel._pending_runtime_request.get("run_id", "")),
		"status": status,
		"snapshot": snapshot if snapshot is Dictionary else {},
	}
	panel._pending_request_kind = "runtime_result"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(RUNTIME_RESULT_URL, panel._json_headers(), HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._log_error("Не удалось передать runtime snapshot серверу")
		panel._pending_runtime_request = {}
		if panel._runtime_timeout_timer:
			panel._runtime_timeout_timer.stop()
		panel._set_ui_busy(false)

static func _start_runtime_check(panel, envelope: Dictionary) -> void:
	panel._pending_runtime_check = (envelope.get("runtime_check_request", {}) as Dictionary).duplicate(true)
	if panel._pending_runtime_check.is_empty():
		return
	panel._runtime_check_session_id = -1
	panel._runtime_check_run_id = ""
	# Godot 4.6.1 exposes neither editor-run PIDs nor a debugger-session remote
	# PID. A sole/new session, scene name or bridge-reported PID is not proof
	# that play_custom_scene launched it. Refuse before launching or sending input.
	panel._view.add_system("run_check unavailable: Godot 4.6.1 cannot prove ownership of the launched debugger session. No scene was launched or stopped.")
	panel._send_runtime_check_result("bridge_unavailable", {})

static func _execute_bound_runtime_check(panel, _envelope: Dictionary) -> void:
	# A server bind response cannot establish local process ownership either.
	panel._send_runtime_check_result("bridge_unavailable", {})

static func _on_runtime_check_completed(panel, result: Dictionary) -> void:
	if panel._pending_runtime_check.is_empty():
		return
	if str(result.get("request_id", "")) != str(panel._pending_runtime_check.get("request_id", "")):
		return
	if panel._runtime_timeout_timer:
		panel._runtime_timeout_timer.stop()
	panel._send_runtime_check_result(str(result.get("status", "protocol_error")), result.get("result", {}))

static func _send_runtime_check_result(panel, status: String, result_value) -> void:
	if panel._pending_runtime_check.is_empty():
		return
	panel._pending_runtime_check_result_body = {
		"request_id": str(panel._pending_runtime_check.get("request_id", "")),
		"result_token": str(panel._pending_runtime_check.get("result_token", "")),
		"session_id": panel._runtime_check_session_id,
		"run_id": panel._runtime_check_run_id,
		"status": status,
		"result": result_value if result_value is Dictionary else {},
	}
	panel._send_pending_runtime_check_result()

static func _send_pending_runtime_check_result(panel) -> void:
	if panel._pending_runtime_check_result_body.is_empty() or panel._is_network_busy:
		return
	panel._pending_request_kind = "runtime_check_result"
	panel._set_ui_busy(true)
	var error = panel.http_request.request(RUNTIME_CHECK_RESULT_URL, panel._json_headers(), HTTPClient.METHOD_POST,
		panel._policy_json(panel._pending_runtime_check_result_body))
	if error != OK:
		panel._set_ui_busy(false)
		panel._log_error("Не удалось передать результат локальной игровой проверки серверу")

static func _clear_runtime_check_state(panel) -> void:
	panel._pending_runtime_check = {}
	panel._pending_runtime_check_result_body = {}
	panel._runtime_check_session_id = -1
	panel._runtime_check_run_id = ""
	if panel._runtime_timeout_timer:
		panel._runtime_timeout_timer.stop()

static func _locale(panel):
	if panel._loc == null:
		var sc = panel.get_script() as Script
		if sc:
			var lp = sc.resource_path.get_base_dir() + "/agent_locale.gd"
			if FileAccess.file_exists(lp):
				panel._loc = load(lp)
	return panel._loc

static func _t(panel, key: String) -> String:
	var l = panel._locale()
	if l:
		return l.t(key)
	return key

static func _json_headers(panel) -> PackedStringArray:
	# Сборка заголовков переехала в AgentServer. Здесь осталась тонкая
	# обёртка, потому что 27 мест в панели уже зовут _json_headers().
	#
	# require_token = false — прежнее поведение панели: токен берётся у узла
	# ServerLink, а если его нет, читается из файла, и если файла тоже нет,
	# заголовок токена НЕ отправляется. Отправлять пустое значение хуже:
	# сервер получил бы заголовок и ответил 403 на запрос, который без него
	# прошёл бы.
	var token := ""
	if panel._link != null and panel._link.has_method("project_token"):
		token = AgentServer.existing_token()
		if token.is_empty():
			token = str(panel._link.project_token())
	return AgentServer.json_headers(token != "")

static func _T(panel):
	# Единый модуль оформления (цвета/иконки/стили) — agent_theme.gd.
	if panel._theme_script == null:
		var sc = panel.get_script() as Script
		if sc:
			var p = sc.resource_path.get_base_dir() + "/agent_theme.gd"
			if FileAccess.file_exists(p):
				panel._theme_script = load(p)
	return panel._theme_script

static func _apply_panel_theme(panel) -> void:
	# Панель собирается кодом в plugin_universal.gd (agent_panel.tscn не
	# используется — см. комментарий там), поэтому оформление навешивается
	# здесь: так оно применяется при любом способе сборки дерева.
	var T = panel._T()
	if T == null:
		return

	# Поле ввода и кнопка отправки.
	T.style_input(panel.input_field)
	if panel.send_button:
		T.style_button(panel.send_button, "accent", false)
		panel.send_button.icon = T.icon(&"ArrowRight")

	# Кнопка выбора нейросети и инструменты из «Дополнительно».
	if panel.chat_model_btn:
		# Тот же вид, что у кнопки провайдера на экране настроек по ключу: это
		# одно и то же действие, открывающее одно и то же окно.
		T.style_button(panel.chat_model_btn, "neutral", false)
		panel.chat_model_btn.icon = T.first_icon(["GuiDropdown", "GuiOptionArrow", "Tools"])
	if panel.reinit_button:
		T.style_button(panel.reinit_button, "neutral")
		panel.reinit_button.icon = T.icon(&"Reload")
	if panel._log_errors_button:
		T.style_button(panel._log_errors_button, "neutral")
		panel._log_errors_button.icon = T.first_icon(["StatusError", "Debug"])
	if panel._api_export_button:
		T.style_button(panel._api_export_button, "neutral")
		panel._api_export_button.icon = T.first_icon(["Script", "File"])
	if panel._safe_rename_button:
		T.style_button(panel._safe_rename_button, "neutral")
		panel._safe_rename_button.icon = T.first_icon(["Rename", "Edit", "ActionCopy"])
	if panel._safe_node_rename_button:
		T.style_button(panel._safe_node_rename_button, "neutral")
		panel._safe_node_rename_button.icon = T.first_icon(["Rename", "Edit", "Node"])
	if panel._plan_stop_button:
		T.style_button(panel._plan_stop_button, "error")
		panel._plan_stop_button.icon = T.first_icon(["Stop", "Pause"])

	# Строка чатов: иконки редактора вместо эмодзи-символов.
	if panel._bar_btn_new:
		T.style_icon_button(panel._bar_btn_new, ["Add"], "＋", "success")
	if panel._bar_btn_ren:
		T.style_icon_button(panel._bar_btn_ren, ["Rename", "Edit"], "✏")
	if panel._bar_btn_del:
		T.style_icon_button(panel._bar_btn_del, ["Remove"], "🗑", "error")
	if panel._bar_btn_home:
		T.style_button(panel._bar_btn_home, "neutral")
		panel._bar_btn_home.icon = T.first_icon(["Home", "GuiTabMenuHl", "ArrowLeft"])
	if panel._bar_btn_settings:
		T.style_icon_button(panel._bar_btn_settings, ["Tools", "GDScript"], "⚙")

static func _set_pending_action(panel, active: bool, description: String = "") -> void:
	# Список мест живёт только пока ждём подтверждения: после ответа он больше
	# не нужен, а оставить его — значит показать старые галочки в следующем
	# действии.
	if not active:
		panel._pending_rename_usages = []
		panel._rename_excluded = {}
	# Единая точка вкл/выкл состояния «ждём ответа на подтверждение».
	# Саму панель не показываем — её роль выполняет карточка в чате.
	panel._pending_action_active = active
	if panel.action_label and description != "":
		panel.action_label.text = description
	if panel.pending_action_box:
		panel.pending_action_box.visible = false

static func _has_pending_action(panel) -> bool:
	return (panel._pending_action_active or not panel._pending_scene_finalize_body.is_empty()
		or not panel._pending_project_settings_finalize_body.is_empty()
		or not panel._pending_resource_finalize_body.is_empty()
		or not panel._pending_runtime_request.is_empty() or not panel._pending_runtime_check.is_empty()
		or not panel._pending_runtime_check_result_body.is_empty())

static func _clear_pending_action_state(panel) -> void:
	# Подтверждение относится только к чату, в котором оно было создано.
	panel._set_pending_action(false)
	panel._last_pending_action_type = ""
	panel._last_pending_action_path = ""
	panel._last_pending_action_dest = ""
	panel._last_pending_action_paths = PackedStringArray()
	panel._pending_scene_action = {}
	panel._pending_scene_expected_hash = ""
	panel._pending_scene_semantic_hash = ""
	panel._pending_project_settings_action = {}
	panel._pending_project_settings_expected_hash = ""
	panel._pending_project_settings_semantic_hash = ""
	panel._pending_resource_action = {}
	panel._pending_resource_expected_hash = ""
	panel._pending_resource_semantic_hash = ""
	panel._pending_resource_dependency_fingerprint = ""
	# Finalize envelope очищается только после терминального ответа сервера.
	# Обычная смена/очистка pending action не должна терять уже записанный ресурс.
	panel._pending_log_send = false

static func _escape_bbcode(panel, text: String) -> String:
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

static func _set_ui_busy(panel, busy: bool) -> void:
	panel._is_network_busy = busy
	panel.send_button.disabled = busy
	panel.reinit_button.disabled = busy
	if panel._log_errors_button: panel._log_errors_button.disabled = busy
	if panel._api_export_button: panel._api_export_button.disabled = busy
	panel.input_field.editable = not busy
	if panel.confirm_button: panel.confirm_button.disabled = busy
	if panel.reject_button: panel.reject_button.disabled = busy
	panel.send_button.text = panel._t("sending") if busy else panel._t("send")
	# Живая трансляция: опрашиваем статус только пока идёт запрос.
	if busy:
		if panel._view:
			panel._view.reset_live()
		if panel._progress_timer and panel._progress_timer.is_stopped():
			panel._progress_timer.start()
		panel._show_stop_button()
	else:
		if panel._progress_timer:
			panel._progress_timer.stop()
		if panel._view:
			panel._view.hide_status()
		panel._progress_inflight = false
		panel._hide_stop_button()
		if panel.input_field and panel.input_field.is_visible_in_tree():
			panel.input_field.call_deferred("grab_focus")
			panel.input_field.queue_redraw()

static func _clear_chat_input(panel, reset_live: bool = true) -> void:
	if panel.input_field == null:
		return
	panel.input_field.clear()
	panel.input_field.set_caret_line(0)
	panel.input_field.set_caret_column(0)
	if panel.input_field.has_method("deselect"):
		panel.input_field.call("deselect")
	panel.input_field.scroll_vertical = 0
	panel.input_field.scroll_horizontal = 0
	panel.input_field.queue_redraw()
	if reset_live:
		panel._live_seq += 1
		panel._live_force_send = true
		panel._live_dirty = true
	if not panel._is_network_busy and panel.input_field.is_visible_in_tree():
		panel.input_field.call_deferred("grab_focus")

static func _restore_chat_draft(panel) -> void:
	if panel.input_field == null or panel._pending_chat_prompt.is_empty():
		return
	if panel.input_field.text.is_empty():
		panel.input_field.text = panel._pending_chat_prompt
		panel.input_field.set_caret_line(max(0, panel.input_field.get_line_count() - 1))
		panel.input_field.set_caret_column(panel.input_field.get_line(panel.input_field.get_caret_line()).length())
		panel.input_field.queue_redraw()
	panel._live_dirty = true
	panel.input_field.call_deferred("grab_focus")

static func _finish_chat_send(panel) -> void:
	panel._pending_chat_prompt = ""
	panel._pending_editor_context = {}
	if panel._current_chat_id != "":
		panel._chat_drafts.erase(panel._current_chat_id)

static func _switch_chat_draft(panel, next_chat_id: String) -> void:
	if panel.input_field == null or next_chat_id == panel._current_chat_id:
		return
	var previous_draft = panel.input_field.text
	if previous_draft.is_empty() and not panel._pending_chat_prompt.is_empty():
		previous_draft = panel._pending_chat_prompt
	if panel._current_chat_id != "":
		if previous_draft.is_empty():
			panel._chat_drafts.erase(panel._current_chat_id)
		else:
			panel._chat_drafts[panel._current_chat_id] = previous_draft
	panel.input_field.text = str(panel._chat_drafts.get(next_chat_id, ""))
	panel.input_field.set_caret_line(max(0, panel.input_field.get_line_count() - 1))
	panel.input_field.set_caret_column(panel.input_field.get_line(panel.input_field.get_caret_line()).length())
	panel.input_field.queue_redraw()
	panel._live_seq += 1
	panel._live_force_send = true
	panel._live_dirty = true

static func _on_server_state_changed(panel, running: bool) -> void:
	# Кнопка ручного запуска сервера теперь живёт на стартовом экране
	# (agent_start_screen.gd), рядом с переключателем языка — видна только
	# пока сервер не отвечает. Раньше она добавлялась в $VBoxContainer, но
	# стартовый экран рисуется поверх него на весь экран и закрывал её целиком —
	# поэтому кнопку никто не видел. Автозапуск продолжает работать как раньше.
	if panel._start_screen and panel._start_screen.has_method("set_server_running"):
		panel._start_screen.set_server_running(running)

static func _on_open_server_folder_pressed(panel) -> void:
	if panel._link == null:
		return
	var exe: String = panel._link.open_server_folder()
	if exe == "":
		panel._notify("Не нашёл godot_agent_server.exe — соберите сервер (build_server_exe.bat) или укажите путь в server_path.txt", "error")
	else:
		panel._notify("Открыл папку сервера: " + exe, "info")

static func _show_stop_button(panel) -> void:
	# Кнопка «Стоп» для ОБЫЧНОЙ обработки запроса (не путать с остановкой плана).
	if panel._stop_button == null:
		panel._stop_button = Button.new()
		panel._stop_button.pressed.connect(panel._on_stop_pressed)
		if panel.send_button and panel.send_button.get_parent():
			panel.send_button.get_parent().add_child(panel._stop_button)
		else:
			panel.add_child(panel._stop_button)
		# Текст и иконка были захардкожены по-русски и не переводились.
		var T = panel._T()
		if T:
			T.style_button(panel._stop_button, "error")
			panel._stop_button.icon = T.first_icon(["Stop", "Pause"])
	panel._stop_button.text = panel._t("stop_btn")
	panel._stop_button.tooltip_text = panel._t("stop_tip")
	panel._stop_button.visible = true
	panel._stop_button.disabled = false

static func _hide_stop_button(panel) -> void:
	if panel._stop_button:
		panel._stop_button.visible = false

static func _on_stop_pressed(panel) -> void:
	# Основной http_request занят самим запросом /chat — шлём остановку
	# отдельным одноразовым HTTPRequest. Сервер прервёт ожидание ответа,
	# и текущий запрос вернётся с пометкой [Остановлено].
	if panel._stop_button:
		panel._stop_button.disabled = true
		panel._stop_button.text = panel._t("stopping")
	if panel._link == null:
		if panel._stop_button:
			panel._stop_button.disabled = false
			panel._stop_button.text = panel._t("stop_btn")
		return
	var stopped: bool = panel._link.post_now("chat_stop", CHAT_STOP_URL, panel._policy_json({}))
	if not stopped:
		if panel._stop_button:
			panel._stop_button.disabled = false
			panel._stop_button.text = panel._t("stop_btn")

static func _refresh_chat_model_btn(panel) -> void:
	# Подпись кнопки = нейросеть и провайдер ОТКРЫТОГО чата.
	if panel.chat_model_btn == null:
		return
	# У браузерного чата модель выбирают на самой странице сервиса, и сменить её
	# отсюда нечем: сервер такой запрос честно отклоняет (/chats/model). Кнопки
	# там нет вовсе — предлагать действие, которое заведомо не сработает, хуже,
	# чем не предлагать его.
	panel.chat_model_btn.visible = panel._api_chat_model != ""
	panel.chat_model_btn.text = panel._api_chat_site if panel._api_chat_site != "" else panel._t("chat_model_pick")
	panel.chat_model_btn.tooltip_text = panel._t("chat_model_pick_tip")

static func _on_chat_model_pressed(panel) -> void:
	# Выбор нейросети для ЭТОГО чата: то же окно, что и в настройках работы по
	# ключу. Своего списка моделей у чата нет намеренно — второй список стал бы
	# вторым источником правды о том, что доступно и у кого есть ключ.
	if panel._start_screen == null or not panel._start_screen.has_method("open_chat_provider_pick"):
		return
	# Список провайдеров, ключей и моделей живёт на СЕРВЕРЕ, и панель своего
	# представления о нём не держит (см. раздел «Работа по ключу API» ниже).
	# Поэтому спрашиваем его заново: за время переписки ключ мог исчерпаться, и
	# окно с прошлыми пометками предложило бы модель, которая уже не отвечает.
	# Само окно открываем в ответе (_on_api_payload) — открытое до ответа, оно
	# нарисовалось бы пустым.
	panel._chat_model_pick_wanted = true
	panel.chat_model_btn.text = panel._t("chat_model_loading")
	panel._request_chats("api_providers", {})

static func _on_input_field_gui_input(panel, event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_ENTER and event.ctrl_pressed:
			panel._on_send_pressed()
			panel.accept_event()

static func _on_live_input_changed(panel) -> void:
	if panel._live_enabled:
		panel._live_dirty = true

static func _on_live_input_tick(panel) -> void:
	if not panel._live_enabled or not panel._live_dirty or panel._live_inflight: return
	if panel._is_network_busy: return  # идёт обмен — конвейер сам вставит финальный промпт
	if panel.input_field == null or panel._link == null: return
	var txt: String = panel.input_field.text
	if txt == panel._live_last_sent and not panel._live_force_send:
		panel._live_dirty = false
		return
	panel._live_seq += 1
	var body = panel._policy_body({"text": txt, "seq": panel._live_seq})
	if not panel._link.post_now("live_input", LIVE_INPUT_URL, panel._policy_json(body)):
		return  # сервер занят/недоступен — молча попробуем на следующем тике
	panel._live_inflight = true
	panel._live_last_sent = txt
	panel._live_force_send = false
	panel._live_dirty = false

static func _on_live_input_response(panel, _result: int, _code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
	# Ошибки молча игнорируем: зеркалирование — best effort, отправке оно
	# не мешает (конвейер v88.4 сам вставляет и сверяет финальный промпт).
	panel._live_inflight = false

static func _on_live_input_toggled(panel, pressed: bool) -> void:
	panel._live_enabled = pressed
	panel._save_live_input_setting(pressed)
	if pressed:
		panel._live_dirty = true  # сразу дослать текущий текст поля

static func _load_live_input_setting(panel) -> bool:
	return true  # живой ввод всегда активен по стандарту для анонимности в браузере

static func _save_live_input_setting(panel, enabled: bool) -> void:
	var f = FileAccess.open(LIVE_INPUT_SETTING_FILE, FileAccess.WRITE)
	if f == null:
		return
	f.store_string("1" if enabled else "0")

static func _on_safe_rename_toggled(panel, pressed: bool) -> void:
	panel._safe_rename_enabled = pressed
	panel._save_safe_rename_setting(pressed)

static func _load_safe_rename_setting(panel) -> bool:
	if not FileAccess.file_exists(SAFE_RENAME_SETTING_FILE):
		return true  # по умолчанию включено
	var f = FileAccess.open(SAFE_RENAME_SETTING_FILE, FileAccess.READ)
	if f == null:
		return true
	return f.get_as_text().strip_edges() != "0"

static func _save_safe_rename_setting(panel, enabled: bool) -> void:
	var f = FileAccess.open(SAFE_RENAME_SETTING_FILE, FileAccess.WRITE)
	if f == null:
		return
	f.store_string("1" if enabled else "0")

static func _on_rename_unverified_toggled(panel, pressed: bool) -> void:
	panel._rename_unverified_enabled = pressed
	panel._save_rename_unverified_setting(pressed)

static func _load_rename_unverified_setting(panel) -> bool:
	# Нет файла — считаем включённым: «галочка стоит по стандарту». Обратное
	# поведение молча выставило бы strict при первом же открытии проекта,
	# вопреки видимому дефолту.
	if not FileAccess.file_exists(RENAME_UNVERIFIED_SETTING_FILE):
		return true
	var f = FileAccess.open(RENAME_UNVERIFIED_SETTING_FILE, FileAccess.READ)
	if f == null:
		return true
	return f.get_as_text().strip_edges() != "0"

static func _save_rename_unverified_setting(panel, enabled: bool) -> void:
	var f = FileAccess.open(RENAME_UNVERIFIED_SETTING_FILE, FileAccess.WRITE)
	if f == null:
		return
	f.store_string("1" if enabled else "0")

static func _on_rename_mode_selected(panel, index: int) -> void:
	var modes := ["strict", "probable"]
	if index < 0 or index >= modes.size():
		return
	panel._rename_mode = str(modes[index])
	panel._save_rename_mode(panel._rename_mode)

static func _load_rename_mode(panel) -> String:
	# Дефолт — strict, и отсутствие файла настроек его НЕ меняет. Иначе первое
	# же открытие проекта молча ослабило бы строгость переименования до
	# нестрогой, а пользователь об этом не узнал бы.
	if not FileAccess.file_exists(RENAME_MODE_SETTING_FILE):
		return "strict"
	var f = FileAccess.open(RENAME_MODE_SETTING_FILE, FileAccess.READ)
	if f == null:
		return "strict"
	var stored := f.get_as_text().strip_edges()
	return stored if stored == "probable" else "strict"

static func _save_rename_mode(panel, mode: String) -> void:
	var f = FileAccess.open(RENAME_MODE_SETTING_FILE, FileAccess.WRITE)
	if f == null:
		return
	f.store_string(mode if mode == "probable" else "strict")

static func _load_policy_settings(panel) -> void:
	panel._allow_addons = false
	if FileAccess.file_exists(POLICY_SETTING_FILE):
		var p = FileAccess.open(POLICY_SETTING_FILE, FileAccess.READ)
		if p:
			panel._allow_addons = p.get_as_text().strip_edges() == "1"
			p.close()
	panel._allow_self_edit = false
	if panel._policy_warning_label:
		panel._policy_warning_label.visible = false

static func _save_allow_addons_policy(panel) -> void:
	var f := FileAccess.open(POLICY_SETTING_FILE, FileAccess.WRITE)
	if f:
		f.store_string("1" if panel._allow_addons else "0")
		f.close()

static func _policy_body(panel, extra: Dictionary = {}) -> Dictionary:
	var body := extra.duplicate(true)
	body["project_root"] = ProjectSettings.globalize_path("res://")
	body["user_data_dir"] = OS.get_user_data_dir()
	body["addon_dir"] = ProjectSettings.globalize_path(panel.get_script().resource_path.get_base_dir())
	body["allow_addons"] = panel._allow_addons
	body["allow_self_edit"] = panel._allow_self_edit
	# Галочка «переименовывать недоказанные ссылки» едет тем же каналом, что и
	# остальная политика: сервер без этого поля не узнает, что пользователь
	# её снял, и продолжит вести себя по умолчанию.
	body["rename_unverified"] = panel._rename_unverified_enabled
	# Режим отказа едет тем же каналом: без него сервер не узнает, что
	# пользователь осознанно разрешил probable.
	body["rename_mode"] = panel._rename_mode
	return body

static func _policy_json(panel, value) -> String:
	var body: Dictionary = value if value is Dictionary else {}
	return JSON.stringify(panel._policy_body(body))

static func _on_allow_addons_toggled(panel, pressed: bool) -> void:
	if not pressed:
		panel._allow_addons = false
		panel._save_allow_addons_policy()
		return
	panel._policy_previous_allow_addons = panel._allow_addons
	panel._allow_addons = false
	panel._request_policy_enable("allow_addons")

static func _on_allow_self_edit_toggled(panel, pressed: bool) -> void:
	if pressed:
		panel._policy_previous_allow_self_edit = panel._allow_self_edit
		panel._allow_self_edit = false
		panel._request_policy_enable("allow_self_edit")
	else:
		panel._allow_self_edit = false
	if panel._policy_warning_label:
		panel._policy_warning_label.visible = panel._allow_self_edit

static func _request_policy_enable(panel, kind: String) -> void:
	if is_instance_valid(panel._policy_confirmation_dialog):
		return
	# Если окно настроек закрыло дочерний диалог, ссылка могла устареть.
	panel._policy_confirmation_dialog = null
	panel._policy_confirmation_pending = kind
	panel._policy_confirmation_dialog = ConfirmationDialog.new()
	panel._policy_confirmation_dialog.name = "AccessPolicyConfirmation"
	panel._policy_confirmation_dialog.transient = true
	panel._policy_confirmation_dialog.exclusive = true
	panel._policy_confirmation_dialog.title = panel._t("policy_confirm_title")
	panel._policy_confirmation_dialog.dialog_text = panel._t("policy_confirm_text")
	panel._policy_confirmation_dialog.get_ok_button().text = panel._t("policy_confirm_yes")
	panel._policy_confirmation_dialog.get_cancel_button().text = panel._t("policy_confirm_no")
	panel._policy_confirmation_dialog.confirmed.connect(func() -> void:
		if panel._policy_confirmation_pending == "allow_addons":
			panel._allow_addons = true
			panel._save_allow_addons_policy()
		else:
			panel._allow_self_edit = true
		panel._policy_confirmation_pending = ""
		if panel._allow_addons_check:
			panel._allow_addons_check.set_pressed_no_signal(panel._allow_addons)
		if panel._allow_self_edit_check:
			panel._allow_self_edit_check.set_pressed_no_signal(panel._allow_self_edit)
		if panel._policy_warning_label:
			panel._policy_warning_label.visible = panel._allow_self_edit
		panel._close_policy_confirmation()
	)
	panel._policy_confirmation_dialog.canceled.connect(func() -> void:
		panel._policy_confirmation_pending = ""
		panel._allow_addons = panel._policy_previous_allow_addons
		panel._allow_self_edit = panel._policy_previous_allow_self_edit
		if panel._allow_addons_check:
			panel._allow_addons_check.set_pressed_no_signal(panel._allow_addons)
		if panel._allow_self_edit_check:
			panel._allow_self_edit_check.set_pressed_no_signal(panel._allow_self_edit)
		if panel._policy_warning_label:
			panel._policy_warning_label.visible = panel._allow_self_edit
		panel._close_policy_confirmation()
	)
	# Подтверждение принадлежит окну настроек. После его закрытия Godot
	# возвращает верхний нативный статус родительскому окну, а не соседнему окну
	# редактора, поэтому настройки больше не исчезают за слоем Godot.
	panel._settings_dialog.add_child(panel._policy_confirmation_dialog)
	panel._policy_confirmation_dialog.popup_centered()

static func _close_policy_confirmation(panel) -> void:
	var dialog = panel._policy_confirmation_dialog
	panel._policy_confirmation_dialog = null
	if not is_instance_valid(dialog):
		return
	dialog.tree_exited.connect(panel._restore_settings_window, CONNECT_ONE_SHOT)
	dialog.queue_free()

static func _restore_settings_window(panel) -> void:
	if is_instance_valid(panel._settings_dialog) and panel._settings_dialog.visible:
		panel._settings_dialog.move_to_front()

static func _on_reinit_pressed(panel) -> void:
	if panel._is_network_busy: return
	panel._view.add_system(panel._t("tree_refresh"))
	panel._rollback_force_next = false
	var body = panel._policy_body({
		"godot_version": Engine.get_version_info().get("string", ""),
		"godot_executable": OS.get_executable_path(),
		"runtime_status": panel._runtime_status,
		"reinit": true,
	})
	var headers = panel._json_headers()
	panel.http_request.set_http_proxy("", 0)
	panel._pending_request_kind = "init"
	panel._set_ui_busy(true)
	panel.http_request.request(INIT_URL, headers, HTTPClient.METHOD_POST, panel._policy_json(body))

static func _on_send_pressed(panel) -> void:
	if panel._is_network_busy: return
	if panel._has_pending_action():
		panel._log_error(panel._t("resolve_action_first"))
		return
	var user_text = panel.input_field.text
	if user_text.strip_edges().is_empty(): return
	panel._clear_chat_input(true)
	panel._rollback_force_next = false
	panel._view.add_user_message(panel._escape_bbcode(user_text))
	panel._view.add_system(panel._t("analyzing"))
	panel._send_chat_raw(user_text, false)

static func _send_chat_raw(panel, prompt: String, ignore_mismatch: bool) -> void:
	panel._pending_chat_prompt = prompt
	if not ignore_mismatch or panel._pending_editor_context.is_empty():
		panel._pending_editor_context = panel._capture_editor_context()
	var body = panel._policy_body({
		"prompt": prompt,
		"chat_id": panel._current_chat_id,
		"godot_executable": OS.get_executable_path(),
		"runtime_status": panel._runtime_status,
	})
	var headers = panel._json_headers()
	if not panel._pending_editor_context.is_empty():
		body["editor_context"] = panel._pending_editor_context
	if ignore_mismatch:
		body["ignore_site_mismatch"] = true
	panel.http_request.set_http_proxy("", 0)
	panel._pending_request_kind = "chat"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(CHAT_URL, headers, HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._log_error(panel._t("err_send"))
		panel._set_ui_busy(false)
		panel._restore_chat_draft()

static func _capture_editor_context(panel) -> Dictionary:
	if panel._editor_context_script == null:
		var script_path: String = panel.get_script().resource_path.get_base_dir() + "/agent_editor_context.gd"
		if FileAccess.file_exists(script_path):
			panel._editor_context_script = load(script_path)
	if panel._editor_context_script != null:
		var snapshot = panel._editor_context_script.capture()
		if snapshot is Dictionary:
			return snapshot
	return {}

static func _on_confirm_pressed(panel) -> void:
	panel._send_confirm_request(true)

static func _on_reject_pressed(panel) -> void:
	panel._send_confirm_request(false)

## Карточка подтверждения — PanelContainer с одним VBoxContainer внутри
## (agent_chat_view.add_confirmation_card). Свой список дописываем ИМЕННО в
## него: второй ребёнок PanelContainer наложился бы на первый.
static func _rename_usage_card_box(panel, card) -> VBoxContainer:
	if card == null or not (card is PanelContainer):
		return null
	for child in (card as PanelContainer).get_children():
		if child is VBoxContainer:
			return child as VBoxContainer
	return null

## Список мест переименования с галочками (Этап 4.3). Галочка означает «это
## место будет переименовано» — ровно как в чеклисте сервера. Снятая позиция
## уходит в confirm_action полем exclude ровно тем же id, который показан
## пользователю, поэтому панель и приёмник адресуют одно и то же место
## (main.py: _with_exclude/_usage_id_to_place -> symbol_refactor._usage_excluded),
## а не считают строку каждый по-своему.
static func _attach_rename_usage_checklist(panel, card) -> void:
	if panel._last_pending_action_type != "rename_symbol" or panel._pending_rename_usages.is_empty():
		return
	var box = panel._rename_usage_card_box(card)
	if box == null:
		return
	panel._rename_excluded = {}
	var caption := Label.new()
	caption.text = "Места переименования (снимите галочку, чтобы не менять это место):"
	caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(caption)
	var list := VBoxContainer.new()
	list.add_theme_constant_override("separation", 2)
	box.add_child(list)
	var shown := 0
	for place in panel._pending_rename_usages:
		if not (place is Dictionary):
			continue
		var usage := place as Dictionary
		var place_id := str(usage.get("id", ""))
		# Место без id нельзя адресовать в exclude: показать его галочкой
		# означало бы обещать выбор, которого нет.
		if place_id.is_empty():
			continue
		if shown >= RENAME_USAGE_LIST_LIMIT:
			var rest := Label.new()
			rest.text = "... ещё %d мест" % (panel._pending_rename_usages.size() - shown)
			list.add_child(rest)
			break
		shown += 1
		var check := CheckBox.new()
		var note := str(usage.get("note", ""))
		check.text = "%s:%s [%s]%s" % [usage.get("path", ""), usage.get("line", ""),
			usage.get("confidence", ""), (" — " + note) if note != "" else ""]
		check.button_pressed = bool(usage.get("checked", true))
		check.tooltip_text = place_id
		# Снятая галочка запоминается по id, а не по строке списка: id —
		# единственный устойчивый адрес места.
		var handler := func(pressed: bool, pid: String) -> void:
			if pressed:
				panel._rename_excluded.erase(pid)
			else:
				panel._rename_excluded[pid] = true
		check.toggled.connect(handler.bind(place_id))
		list.add_child(check)

static func _send_confirm_request(panel, approved: bool) -> void:
	if panel._is_network_busy: return
	# Снятые места (снятые галочки в карточке) читаем ДО _set_pending_action(false):
	# он очищает _rename_excluded, и exclude уехал бы в приёмник пустым — то есть
	# снятая позиция применилась бы вместе с остальными.
	var excluded_places: Array = []
	if panel._last_pending_action_type == "rename_symbol":
		excluded_places = panel._rename_excluded.keys()
	if approved and panel._last_pending_action_type in ["rename_symbol", "rename_file", "rename_node", "reparent_node", "delete_node", "transaction", "create_file", "patch_file", "move_file"]:
		var targets = panel._last_pending_action_paths.duplicate()
		for path in [panel._last_pending_action_path, panel._last_pending_action_dest]:
			if not str(path).is_empty() and not targets.has(str(path)):
				targets.append(str(path))
		var dirty_paths = panel._dirty_open_scripts(targets)
		if not dirty_paths.is_empty():
			panel._view.add_warning("Сначала сохраните изменённые вкладки: " + ", ".join(dirty_paths))
			return
	# Подтверждение отправки отчёта об ошибках запуска — отдельная ветка:
	# при отказе сервер вообще не трогаем (и браузер тоже).
	if panel._pending_log_send:
		panel._set_pending_action(false)
		panel._pending_log_send = false
		if not approved:
			panel._view.add_system(panel._t("errs_cancelled"))
			return
		panel._view.add_system(panel._t("errs_sending"))
		var log_headers = panel._json_headers()
		panel.http_request.set_http_proxy("", 0)
		panel._pending_request_kind = "chat"
		panel._set_ui_busy(true)
		var log_err = panel.http_request.request(SEND_LOG_URL, log_headers, HTTPClient.METHOD_POST, panel._policy_json({}))
		if log_err != OK:
			panel._log_error(panel._t("err_send_report"))
			panel._set_ui_busy(false)
		return
	if approved and panel._last_pending_action_type not in ["edit_scene", "create_scene", "rename_node", "reparent_node", "delete_node", "edit_project_settings", "edit_resource", "inspect_runtime", "run_check"]:
		panel._close_scenes_before_write()
	panel._set_pending_action(false)
	var label = panel._t("approved_action") if approved else panel._t("rejected_action")
	panel._view.add_system(label + panel._t("waiting_reply"))
	var headers = panel._json_headers()
	var body = panel._policy_body({"approved": approved})
	if approved and not excluded_places.is_empty():
		# Адреса мест — ровно те же id, что показаны галочками в карточке
		# (main.py: _usage_id_to_place -> symbol_refactor._usage_excluded).
		# Один источник адреса: панель и приёмник не считают строку каждый
		# по-своему, поэтому снимается ровно выбранное место.
		body["exclude"] = excluded_places
	if approved and panel._last_pending_action_type in ["edit_scene", "create_scene"]:
		body["editor_semantic_hash"] = panel._pending_scene_semantic_hash
	elif approved and panel._last_pending_action_type == "edit_project_settings":
		body["editor_semantic_hash"] = panel._pending_project_settings_semantic_hash
	elif approved and panel._last_pending_action_type == "edit_resource":
		body["editor_semantic_hash"] = panel._pending_resource_semantic_hash
		body["dependency_fingerprint"] = panel._pending_resource_dependency_fingerprint
	panel.http_request.set_http_proxy("", 0)
	panel._pending_request_kind = "confirm"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(CONFIRM_URL, headers, HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._log_error(panel._t("err_send_confirm"))
		panel._set_ui_busy(false)
		panel._reopen_scenes_after_write()  # v49: запрос не ушёл — вернуть закрытые сцены

static func _send_scene_result(panel, execution: Dictionary, envelope: Dictionary) -> void:
	panel._pending_scene_finalize_body = {
		"action_id": str(envelope.get("action_id", "")),
		"execution_token": str(envelope.get("execution_token", "")),
		"success": bool(execution.get("ok", false)),
		"scene_hash": str(execution.get("scene_hash", "")),
		"target_written": bool(execution.get("target_written", false)),
		"staged_hash": str(execution.get("staged_hash", "")),
		"error_code": str(execution.get("code", "")),
		"error": str(execution.get("error", "")),
	}
	panel._finalize_retries["scene"] = 0
	panel._send_pending_finalize("scene")

## Тело отчёта по виду транзакции kind. Ссылка на словарь, а не копия:
## вызывающая сторона заполняет его через finalize_body(kind), иначе правка
## тела потерялась бы на копии.
static func _finalize_body(panel, kind: String) -> Dictionary:
	match kind:
		"scene":
			return panel._pending_scene_finalize_body
		"project_settings":
			return panel._pending_project_settings_finalize_body
		"resource":
			return panel._pending_resource_finalize_body
	return {}

## Отчёт об исходе транзакции kind. Сцена, настройки проекта и ресурс раньше
## отправляли его тремя копиями этой функции; различались только вид и тело,
## а правила повтора разошлись (см. FINALIZE_TERMINAL_CODES).
static func _send_pending_finalize(panel, kind: String) -> void:
	if panel._finalize_body(kind).is_empty():
		return
	if panel._is_network_busy:
		panel._schedule_finalize_retry(kind)
		return
	panel._pending_request_kind = kind + "_finalize"
	panel._set_ui_busy(true)
	panel._finalize_retries[kind] = int(panel._finalize_retries.get(kind, 0)) + 1
	var err = panel.http_request.request(
		EDITOR_ACTION_RESULT_URL, panel._json_headers(), HTTPClient.METHOD_POST,
		panel._policy_json(panel._finalize_body(kind)))
	if err != OK:
		panel._set_ui_busy(false)
		panel._schedule_finalize_retry(kind)

## Повтор отчёта kind, если сеть была занята или запрос не ушёл.
## Рекурсия с задержкой — единственный способ дождаться свободного канала:
## таймер живёт, пока панель в дереве.
static func _schedule_finalize_retry(panel, kind: String) -> void:
	if bool(panel._finalize_retrying.get(kind, false)) or panel._finalize_body(kind).is_empty():
		return
	panel._finalize_retrying[kind] = true
	await panel.get_tree().create_timer(float(mini(int(panel._finalize_retries.get(kind, 0)) + 1, 5))).timeout
	panel._finalize_retrying[kind] = false
	if not panel._is_network_busy:
		panel._send_pending_finalize(kind)
	else:
		panel._schedule_finalize_retry(kind)

## Забыть отчёт по виду kind: сервер ответил окончательно либо транзакция
## завершена. Без этого панель повторяла бы отказ бесконечно.
static func _discard_pending_finalize(panel, kind: String) -> void:
	match kind:
		"scene":
			panel._pending_scene_finalize_body = {}
		"project_settings":
			panel._pending_project_settings_finalize_body = {}
		"resource":
			panel._pending_resource_finalize_body = {}
	panel._finalize_retries[kind] = 0
	panel._finalize_retrying[kind] = false

static func _prepare_scene_action(panel, pending: Dictionary, prepare_data: Dictionary) -> Dictionary:
	if panel._scene_executor == null:
		return {"ok": false, "error": "Исполнитель структурных сцен недоступен"}
	panel._pending_scene_action = pending.duplicate(true)
	panel._pending_scene_expected_hash = str(prepare_data.get("expected_scene_hash", ""))
	var result: Dictionary = panel._scene_executor.prepare(panel._pending_scene_action, panel._pending_scene_expected_hash)
	panel._pending_scene_semantic_hash = str(result.get("semantic_hash", "")) if bool(result.get("ok", false)) else ""
	return result

static func _execute_scene_action(panel, envelope: Dictionary) -> void:
	var execution: Dictionary
	if panel._scene_executor == null:
		execution = {"ok": false, "error": "Исполнитель структурных сцен недоступен", "scene_hash": ""}
	else:
		var action: Dictionary = envelope.get("editor_action", {}).duplicate(true)
		if str(action.get("action", "")) == "create_scene":
			action["_create_action_id"] = str(envelope.get("action_id", ""))
		if panel._pending_scene_semantic_hash != "":
			action["_expected_semantic_hash"] = panel._pending_scene_semantic_hash
		execution = panel._scene_executor.execute(action, str(envelope.get("expected_scene_hash", "")))
	panel._send_scene_result(execution, envelope)

static func _prepare_project_settings_action(panel, pending: Dictionary, prepare_data: Dictionary) -> Dictionary:
	if panel._project_settings_executor == null:
		return {"ok": false, "error": "Исполнитель настроек проекта недоступен"}
	panel._pending_project_settings_action = pending.duplicate(true)
	panel._pending_project_settings_expected_hash = str(prepare_data.get("expected_project_hash", ""))
	var result: Dictionary = panel._project_settings_executor.prepare(
		panel._pending_project_settings_action, panel._pending_project_settings_expected_hash)
	panel._pending_project_settings_semantic_hash = str(result.get("semantic_hash", "")) if bool(result.get("ok", false)) else ""
	return result

static func _execute_project_settings_action(panel, envelope: Dictionary) -> void:
	var execution: Dictionary
	if panel._project_settings_executor == null:
		execution = {"ok": false, "error": "Исполнитель настроек проекта недоступен", "project_hash": ""}
	else:
		var action: Dictionary = envelope.get("editor_action", {}).duplicate(true)
		if panel._pending_project_settings_semantic_hash != "":
			action["_expected_semantic_hash"] = panel._pending_project_settings_semantic_hash
		execution = panel._project_settings_executor.execute(
			action, str(envelope.get("expected_project_hash", "")))
	panel._pending_project_settings_finalize_body = {
		"action_id": str(envelope.get("action_id", "")),
		"execution_token": str(envelope.get("execution_token", "")),
		"editor_action_kind": "project_settings",
		"success": bool(execution.get("ok", false)),
		"project_hash": str(execution.get("project_hash", "")),
		"already_satisfied": bool(execution.get("already_satisfied", false)),
		"error_code": str(execution.get("code", "")),
		"error": str(execution.get("error", "")),
	}
	panel._finalize_retries["project_settings"] = 0
	panel._send_pending_finalize("project_settings")

static func _prepare_resource_action(panel, pending: Dictionary, prepare_data: Dictionary) -> Dictionary:
	if panel._resource_executor == null:
		return {"ok": false, "error": "Исполнитель ресурсов недоступен"}
	panel._pending_resource_action = pending.duplicate(true)
	panel._pending_resource_expected_hash = str(prepare_data.get("expected_resource_hash", ""))
	var result: Dictionary = panel._resource_executor.prepare(
		panel._pending_resource_action, panel._pending_resource_expected_hash)
	if bool(result.get("ok", false)):
		panel._pending_resource_semantic_hash = str(result.get("semantic_hash", ""))
		panel._pending_resource_dependency_fingerprint = str(result.get("dependency_fingerprint", ""))
	else:
		panel._pending_resource_semantic_hash = ""
		panel._pending_resource_dependency_fingerprint = ""
	return result

static func _execute_resource_action(panel, envelope: Dictionary) -> void:
	var execution: Dictionary
	if panel._resource_executor == null:
		execution = {"ok": false, "error": "Исполнитель ресурсов недоступен", "resource_hash": ""}
	else:
		var action: Dictionary = envelope.get("editor_action", {}).duplicate(true)
		action["_expected_semantic_hash"] = panel._pending_resource_semantic_hash
		action["_expected_dependency_fingerprint"] = str(
			envelope.get("expected_dependency_fingerprint", panel._pending_resource_dependency_fingerprint))
		execution = panel._resource_executor.execute(
			action, str(envelope.get("expected_resource_hash", "")))
	panel._pending_resource_finalize_body = {
		"action_id": str(envelope.get("action_id", "")),
		"execution_token": str(envelope.get("execution_token", "")),
		"editor_action_kind": "resource",
		"success": bool(execution.get("ok", false)),
		"resource_hash": str(execution.get("resource_hash", "")),
		"error_code": str(execution.get("code", "")),
		"error": str(execution.get("error", "")),
	}
	panel._finalize_retries["resource"] = 0
	panel._send_pending_finalize("resource")

static func _start_plan_execution(panel, total: int) -> void:
	panel._plan_active = true
	panel._plan_total = total
	panel._plan_index = 0
	# Карточка-чеклист плана прямо в чате (чистый визуал, логика не меняется).
	var step_descs := []
	for i in range(total):
		step_descs.append(panel._t("plan_step_n") % (i + 1))
	panel._active_plan_card = panel._view.add_plan_checklist(panel._t("plan_started") % total, step_descs)
	if panel._active_plan_card:
		# Кнопка «Пауза» на карточке = обычная остановка плана (та же логика).
		panel._active_plan_card.plan_paused.connect(panel._on_plan_stop_pressed)
	panel._show_plan_stop_button()
	panel._request_plan_step()

static func _request_plan_step(panel) -> void:
	if panel._is_network_busy: return
	var headers = panel._json_headers()
	panel.http_request.set_http_proxy("", 0)
	panel._pending_request_kind = "plan_step"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(PLAN_STEP_URL, headers, HTTPClient.METHOD_POST, panel._policy_json({}))
	if err != OK:
		panel._log_error(panel._t("err_plan_step"))
		panel._set_ui_busy(false)
		panel._end_plan_execution()

static func _end_plan_execution(panel) -> void:
	panel._plan_active = false
	panel._hide_plan_stop_button()
	if panel._active_plan_card:
		panel._active_plan_card.queue_free()
		panel._active_plan_card = null

static func _show_plan_stop_button(panel) -> void:
	if panel._plan_stop_button == null:
		panel._plan_stop_button = Button.new()
		panel._plan_stop_button.pressed.connect(panel._on_plan_stop_pressed)
		if panel.advanced_box:
			panel.advanced_box.add_child(panel._plan_stop_button)
		else:
			panel.add_child(panel._plan_stop_button)
	panel._plan_stop_button.text = panel._t("plan_stop_btn")
	panel._plan_stop_button.visible = true
	panel._plan_stop_button.disabled = false
