@tool
extends RefCounted

# Модуль agent_panel_part2: методы вынесены «пилой» split_gd из agent_panel.gd.
# Реализация живёт ЗДЕСЬ; в доноре на месте метода — тонкая обёртка,
# поэтому connect()/call() по исходным именам продолжают работать.
# Тело работает через параметр panel: к членам донора — panel.<член>,
# к другим методам донора — panel.<метод> (через его обёртку).

# --- константы, скопированные из донора (неизменяемы) ---
const ROLLBACK_URL = AgentServer.URL_CHAT_ROLLBACK
const ROLLBACK_PREVIEW_URL = AgentServer.URL_CHAT_ROLLBACK_PREVIEW
const CHECK_LOG_URL = AgentServer.URL_PROJECT_CHECK_LOG
const API_EXPORT_URL = AgentServer.URL_PROJECT_UPDATE_API_CACHE
const API_CACHE_STATUS_URL = AgentServer.URL_PROJECT_API_CACHE_STATUS
const PLAN_STOP_URL = AgentServer.URL_CHAT_PLAN_STOP
const PLAN_ROLLBACK_CHAIN_URL = AgentServer.URL_CHAT_PLAN_ROLLBACK_CHAIN
# Коды, после которых повтор бессмысленен: сервер отклонил запрос окончательно.
# Проверяется ОДИН раз для всех видов, а не в каждой копии отдельно.
const FINALIZE_TERMINAL_CODES := [400, 403, 409, 410, 413]

static func _hide_plan_stop_button(panel) -> void:
	if panel._plan_stop_button:
		panel._plan_stop_button.visible = false

static func _on_plan_stop_pressed(panel) -> void:
	if panel._is_network_busy or not panel._plan_active: return
	if panel._plan_stop_button: panel._plan_stop_button.disabled = true
	var headers = panel._json_headers()
	panel.http_request.set_http_proxy("", 0)
	panel._pending_request_kind = "plan_stop"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(PLAN_STOP_URL, headers, HTTPClient.METHOD_POST, panel._policy_json({}))
	if err != OK:
		panel._log_error(panel._t("err_plan_step"))
		panel._set_ui_busy(false)
		panel._end_plan_execution()

static func _note_autoload_removed(panel, json) -> void:
	# Откат мог оставить в project.godot висячую запись автозагрузки на файл,
	# которого больше нет (см. clean_dangling_autoloads на сервере) — сообщаем,
	# что она уже убрана, чтобы пользователь не искал причину ошибок автозагрузки сам.
	var removed = json.get("autoload_removed")
	if removed is Array and removed.size() > 0:
		panel._view.add_system(panel._t("autoload_cleaned") % ", ".join(removed))

static func _maybe_prompt_project_reload(panel, json) -> void:
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
	if panel._view:
		panel._view.add_question_card(
			"reload_project",
			panel._t("reload_project_title"),
			panel._t("reload_project_text"),
			panel._t("reload_project_yes"),
			panel._t("reload_project_no"),
			func(): panel._on_reload_project_confirmed(),
			func(): pass
		)

static func _on_reload_project_confirmed(panel) -> void:
	panel._view.add_system(panel._t("reload_project_doing"))
	if panel._view: panel._view.flush()
	# true = перезапустить движок на том же проекте (Godot 4.3+); подхватывает
	# свежий project.godot (автозагрузки, main scene и т.п.) без ручных действий.
	EditorInterface.restart_editor(true)

static func _show_plan_rollback_dialog(panel, chain_id: String, desc: String) -> void:
	panel._plan_rollback_chain_id = chain_id
	# Вопрос показывается карточкой в чате вместо модального окна.
	# Тон "ask": это обычное подтверждение, а не предупреждение об аварии.
	if panel._view:
		panel._view.add_question_card(
			"plan_rollback",
			panel._t("plan_rb_title"),
			panel._t("plan_rb_text") % desc,
			panel._t("rb_yes"),
			panel._t("rb_no"),
			func(): panel._on_plan_rollback_confirmed(),
			func(): pass,
			"ask",
			["UndoRedo", "Undo", "Reload"]
		)

static func _on_plan_rollback_confirmed(panel) -> void:
	# v40: если сервер ранее ответил needs_force (файл менялся не из этой цепочки),
	# это повторное подтверждение уже означает согласие откатить принудительно —
	# раньше сюда всегда уходил force=false, и повторное нажатие «Да» просто
	# бесконечно повторяло тот же отказ (внешне выглядело так, будто кнопка не работает).
	if panel._plan_rollback_force_next:
		panel._view.add_warning(panel._t("force_rollback"))
		panel._send_plan_rollback_chain_request(true)
		return
	panel._send_plan_rollback_chain_request(false)

static func _send_plan_rollback_chain_request(panel, force: bool) -> void:
	if panel._is_network_busy: return
	var headers = panel._json_headers()
	var body = {"chain_id": panel._plan_rollback_chain_id, "force": force}
	panel._plan_rollback_force_next = false
	panel.http_request.set_http_proxy("", 0)
	panel._pending_request_kind = "plan_rollback_chain"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(PLAN_ROLLBACK_CHAIN_URL, headers, HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._log_error(panel._t("err_rollback"))
		panel._set_ui_busy(false)

static func _on_message_rollback_requested(panel, entry_id: String) -> void:
	# Откат по клику на карточке ответа агента.
	# Карточка присылает АДРЕС своей записи в журнале изменений, поэтому
	# откатывается именно это изменение. Раньше адреса не было: сервер получал
	# просьбу «откатить последнее» и отменял самое свежее изменение проекта —
	# из другого сообщения, а иногда и из другого чата.
	# Сначала спрашиваем сервер, что именно будет отменено, и показываем это
	# в карточке подтверждения — вслепую ничего не откатывается.
	if panel._is_network_busy:
		# Молча игнорировать клик нельзя: пользователь решит, что кнопка сломана.
		panel._log_error(panel._t("wait_current"))
		return
	if entry_id == "":
		# Кнопки на таких карточках быть не должно (см. _wire_card_rollback),
		# но если она как-то появилась — лучше сказать честно, чем откатить
		# наугад чужое изменение.
		panel._log_error(panel._t("rb_no_target"))
		return
	panel._on_rollback_pressed(entry_id)

static func _show_battle_choice_summary(panel, data: Dictionary) -> void:
	if panel._view == null:
		return
	var selected := str(data.get("selected", "A"))
	var message = panel._t("battle_choice_scores") % [
		selected,
		int(data.get("score_a", 0)),
		int(data.get("score_b", 0)),
	]
	match str(data.get("reason", "")):
		"other_continues":
			message += " " + (panel._t("battle_choice_continues") % str(data.get("other", "")))
		"equal":
			message += " " + (panel._t("battle_choice_equal") % selected)
		"only_acceptable":
			message += " " + panel._t("battle_choice_only")
		"only_verifiable":
			message += " " + panel._t("battle_choice_verifiable")
		"not_verifiable":
			message += " " + (panel._t("battle_choice_unverifiable") % selected)
		_:
			message += " " + panel._t("battle_choice_higher")
	panel._view.add_hint(message)

static func _on_rollback_pressed(panel, entry_id: String = "") -> void:
	if panel._is_network_busy: return
	# Адрес отката запоминаем до ответа на предпросмотр: подтверждение придёт
	# позже, а откатить надо ровно то, на что нажали.
	panel._rollback_entry_id = entry_id
	if panel._rollback_force_next and panel._rollback_force_entry_id == entry_id:
		# Повторное нажатие после needs_force — откатываем без лишних вопросов.
		# Сравнение адреса обязательно: раньше «взведённый» force срабатывал на
		# нажатие у ЛЮБОГО другого сообщения и молча, без подтверждения,
		# перезаписывал правки пользователя.
		panel._view.add_warning(panel._t("force_rollback"))
		panel._send_rollback_request(true)
		return
	panel._rollback_force_next = false
	# Сначала спрашиваем сервер, ЧТО именно будет отменено (и из какого
	# чата было это изменение), чтобы не откатить вслепую чужую работу.
	var headers = panel._json_headers()
	panel.http_request.set_http_proxy("", 0)
	panel._pending_request_kind = "rollback_preview"
	panel._set_ui_busy(true)
	var body := {}
	if entry_id != "":
		body["entry_id"] = entry_id
	var err = panel.http_request.request(ROLLBACK_PREVIEW_URL, headers, HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._log_error(panel._t("err_rollback"))
		panel._set_ui_busy(false)

static func _send_rollback_request(panel, force: bool) -> void:
	var headers = panel._json_headers()
	var body = {"force": force}
	if panel._rollback_entry_id != "":
		body["entry_id"] = panel._rollback_entry_id
	panel._rollback_force_next = false
	panel.http_request.set_http_proxy("", 0)
	panel._pending_request_kind = "rollback"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(ROLLBACK_URL, headers, HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._log_error(panel._t("err_rollback"))
		panel._set_ui_busy(false)

static func _show_rollback_dialog(panel, desc: String) -> void:
	# Вопрос об откате — карточкой в чате, а не модальным окном: так он
	# остаётся в истории рядом с изменением, которое откатывается.
	# Тон "ask": откат — обычное действие, а не авария. Раньше карточка была
	# жёлтой, со знаком «внимание», и рутинный откат выглядел как проблема.
	if panel._view:
		panel._view.add_question_card(
			"rollback",
			panel._t("rb_title"),
			desc,
			panel._t("rb_yes"),
			panel._t("rb_no"),
			func(): panel._on_rollback_confirmed(),
			func(): pass,
			"ask",
			["UndoRedo", "Undo", "Reload"]
		)

static func _on_rollback_confirmed(panel) -> void:
	panel._view.add_system(panel._t("rollback_msg"))
	panel._send_rollback_request(false)

static func _ensure_file_logging_enabled(panel) -> void:
	# Read-only inspection must never alter project.godot automatically.
	var base_on := bool(ProjectSettings.get_setting("debug/file_logging/enable_file_logging", false))
	var pc_on := bool(ProjectSettings.get_setting("debug/file_logging/enable_file_logging.pc", true))
	if not base_on and not pc_on:
		print("Godot Agent: файловое логирование выключено; включите его вручную для встроенных runtime errors.")

static func _on_check_log_pressed(panel) -> void:
	if panel._is_network_busy: return
	if panel._has_pending_action():
		panel._log_error(panel._t("resolve_action_first"))
		return
	panel._view.add_system(panel._t("reading_log"))
	panel._pending_log_send = false
	panel._auto_check = false
	panel._rollback_force_next = false
	var headers = panel._json_headers()
	var body = {
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(panel.get_script().resource_path.get_base_dir()),
	}
	panel.http_request.set_http_proxy("", 0)
	panel._pending_request_kind = "check_log"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(CHECK_LOG_URL, headers, HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._log_error(panel._t("err_log_req"))
		panel._set_ui_busy(false)

static func _check_api_cache_freshness(panel) -> void:
	if panel._is_network_busy:
		panel._schedule_api_cache_check_retry()
		return
	var headers = panel._json_headers()
	var body = {
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(panel.get_script().resource_path.get_base_dir()),
		"godot_version": Engine.get_version_info().get("string", ""),
	}
	panel._pending_request_kind = "api_cache_status"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(API_CACHE_STATUS_URL, headers, HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._set_ui_busy(false)
		panel._schedule_api_cache_check_retry()

static func _schedule_api_cache_check_retry(panel) -> void:
	panel._api_cache_check_attempts += 1
	if panel._api_cache_check_attempts > 8:
		return
	if panel._api_cache_check_timer == null:
		panel._api_cache_check_timer = Timer.new()
		panel._api_cache_check_timer.one_shot = true
		panel.add_child(panel._api_cache_check_timer)
		panel._api_cache_check_timer.timeout.connect(panel._check_api_cache_freshness)
	panel._api_cache_check_timer.wait_time = min(2.0 * panel._api_cache_check_attempts, 15.0)
	panel._api_cache_check_timer.start()

static func _on_export_api_pressed(panel) -> void:
	if panel._is_network_busy: return
	if panel._has_pending_action():
		panel._log_error(panel._t("resolve_action_first"))
		return
	panel._export_api_to_server(false)

# silent = true — тихий автоматический запуск при старте плагина (не блокирует сеть для пользователя,
# просто показывает одно сообщение, если реально пришлось пересобирать).
static func _export_api_to_server(panel, silent: bool) -> void:
	if not silent:
		panel._view.add_system(panel._t("api_export_sending"))
	var export_script = load(panel.get_script().resource_path.get_base_dir() + "/agent_api_export.gd")
	var classes: Dictionary = export_script.export_classes()
	var headers = panel._json_headers()
	var body = {
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(panel.get_script().resource_path.get_base_dir()),
		"classes": classes,
		"godot_version": Engine.get_version_info().get("string", ""),
	}
	panel._pending_request_kind = "api_export"
	panel._set_ui_busy(true)
	var err = panel.http_request.request(API_EXPORT_URL, headers, HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._log_error(panel._t("api_export_err"))
		panel._set_ui_busy(false)

static func _on_request_completed(panel, result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	panel._set_ui_busy(false)
	var kind = panel._pending_request_kind
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
		# ЗАДАЧА 3: единственный полный scan() во всём плагине, и он остаётся
		# именно здесь. Причина — пути здесь неизвестны, а не лень: это общий
		# вход для ответа на ЛЮБОЙ из трёх десятков запросов, и для большинства
		# из них панель не знает, что сервер записал на диск (обычный ответ
		# чата может прийти с молчаливой правкой). Перечисления изменённых
		# файлов здесь нет, взять его неоткуда, поэтому единственный честный
		# вариант — пересчитать проект. Везде, где сервер отдаёт changed_paths,
		# полный скан заменён точечным обновлением (см. _refresh_changed_paths).
		EditorInterface.get_resource_filesystem().scan()

		if json.has("site_mismatch") and bool(json.get("site_mismatch", false)):
			panel._handle_site_mismatch(str(json.get("site", "")), str(json.get("prompt", "")))
			return
		if kind == "chat":
			panel._finish_chat_send()
			var transcript_warning := str(json.get("transcript_warning", ""))
			if transcript_warning != "":
				if panel._view:
					panel._view.add_system(transcript_warning)
				panel._notify(transcript_warning, "error")

		if kind == "init":
			panel._view.add_success(panel._t("reinit_done"))
			return

		if kind == "confirm" and bool(json.get("plan_started", false)):
			panel._reopen_scenes_after_write()  # v49: подтверждение запустило план — вернуть сцены
			panel._last_pending_action_type = ""
			panel._last_pending_action_path = ""
			panel._last_pending_action_dest = ""
			var has_answer_plan: bool = json.has("answer") and json["answer"] != null and str(json["answer"]) != ""
			if has_answer_plan:
				panel._view.add_agent_message(str(json["answer"]))
			panel._start_plan_execution(int(json.get("plan_total", 0)))
			await panel.get_tree().process_frame
			panel._scroll_chat_to_end()
			return

		if kind == "plan_step":
			var p_index := int(json.get("index", 0))
			var p_total = int(json.get("total", panel._plan_total))
			var p_chain = str(json.get("chain_id", panel._plan_chain_id))
			panel._plan_chain_id = p_chain
			panel._plan_index = p_index
			var p_msg := str(json.get("message", ""))
			var p_ok := bool(json.get("ok", false))
			var p_done := bool(json.get("done", false))
			var p_stopped := bool(json.get("stopped", false))
			# Обновляем карточку-чеклист плана (чистый визуал, логика не меняется).
			if panel._active_plan_card and panel._active_plan_card.steps_container.get_child_count() > p_index:
				var step_item = panel._active_plan_card.steps_container.get_child(p_index) as PlanStepItem
				if step_item:
					step_item.description_label.text = p_msg
				if p_done:
					panel._active_plan_card.update_step(p_index, "done")
				elif p_ok:
					panel._active_plan_card.update_step(p_index, "active")
				else:
					panel._active_plan_card.update_step(p_index, "error")
			if p_ok:
				panel._view.add_system(p_msg)
			else:
				panel._view.add_warning(p_msg)
			# Шаг уже записан на диск, поэтому карточка идёт без кнопок —
			# только «файл +N -M» с возможностью развернуть код.
			var p_diff = json.get("step_diff")
			if p_ok and p_diff is Dictionary:
				var p_diff_path := str((p_diff as Dictionary).get("path", ""))
				if p_diff_path == "":
					p_diff_path = str(json.get("changed_path", ""))
				panel._view.add_applied_diff(p_diff_path, p_diff)
			var p_ch_path = json.get("changed_path")
			var p_ch_block = json.get("changed_block")
			if p_ch_path != null and p_ch_block != null and str(p_ch_block) != "":
				if panel._hl: panel._hl.apply(str(p_ch_path), str(p_ch_block))
			panel._force_reload_open_script()
			if p_ch_path != null:
				panel._auto_reload_changed_scene(str(p_ch_path))
			if p_done:
				panel._end_plan_execution()
				if panel._active_plan_card:
					panel._active_plan_card.queue_free()
					panel._active_plan_card = null
				panel._view.add_success(panel._t("plan_done"))
			elif p_stopped:
				panel._end_plan_execution()
				if panel._active_plan_card:
					panel._active_plan_card.queue_free()
					panel._active_plan_card = null
				panel._view.add_warning(panel._t("plan_stopped_desc") % [p_index, p_total])
				panel._show_plan_rollback_dialog(p_chain, panel._t("plan_rb_step_desc") % [p_index, p_total])
			else:
				panel._request_plan_step()
			await panel.get_tree().process_frame
			return

		if kind == "plan_stop":
			var s_index = int(json.get("index", panel._plan_index))
			var s_total = int(json.get("total", panel._plan_total))
			var s_chain = str(json.get("chain_id", panel._plan_chain_id))
			panel._end_plan_execution()
			if panel._active_plan_card:
				panel._active_plan_card.queue_free()
				panel._active_plan_card = null
			panel._view.add_warning(panel._t("plan_stopped_manual") % [s_index, s_total])
			if s_index > 0:
				panel._show_plan_rollback_dialog(s_chain, panel._t("plan_rb_step_desc") % [s_index, s_total])
			await panel.get_tree().process_frame
			panel._scroll_chat_to_end()
			return

		if kind == "plan_rollback_chain":
			var pr_msg = str(json.get("message", panel._t("rollback_done")))
			panel._view.add_success(panel._t("success_prefix") + pr_msg)
			panel._note_autoload_removed(json)
			if bool(json.get("requires_editor_restart", false)):
				panel._view.add_warning("Перезапустите редактор Godot, чтобы восстановленные настройки проекта полностью применились.")
			var pr_paths = json.get("paths")
			if pr_paths is Array:
				for pp in pr_paths:
					if FileAccess.file_exists(str(pp)):
						panel._sync_open_script_with_disk(str(pp))
						panel._auto_reload_changed_scene(str(pp))
					else:
						panel._close_ghost_script_tab(str(pp))
			if panel._hl: panel._hl.clear()
			panel._maybe_prompt_project_reload(json)
			await panel.get_tree().process_frame
			panel._scroll_chat_to_end()
			return

		if kind == "api_export":
			var cnt := int(json.get("classes_count", 0))
			panel._view.add_success(panel._t("api_export_done") % cnt)
			return

		if kind == "api_cache_status":
			panel._api_cache_check_attempts = 0
			var has_cache = bool(json.get("has_cache", false))
			var cached_version = str(json.get("cached_version", ""))
			var current_version = Engine.get_version_info().get("string", "")
			if not has_cache or cached_version != current_version:
				panel._export_api_to_server(true)
			return

		if kind == "confirm" and bool(json.get("execute_in_editor", false)):
			var editor_action_kind := str(json.get("editor_action_kind", "scene"))
			if editor_action_kind == "project_settings":
				panel._execute_project_settings_action(json)
			elif editor_action_kind == "resource":
				panel._execute_resource_action(json)
			elif editor_action_kind == "scene":
				panel._execute_scene_action(json)
			else:
				panel._log_error("Неизвестный тип editor-транзакции: " + editor_action_kind)
			return

		if kind == "confirm" and json.get("runtime_request") is Dictionary:
			panel._start_runtime_inspect(json)
			return

		if kind == "confirm" and json.get("runtime_check_request") is Dictionary:
			panel._start_runtime_check(json)
			return

		if kind == "runtime_check_bind":
			panel._execute_bound_runtime_check(json)
			return

		if kind == "runtime_result":
			panel._pending_runtime_request = {}
			if panel._runtime_timeout_timer:
				panel._runtime_timeout_timer.stop()

		if kind == "runtime_check_result":
			panel._clear_runtime_check_state()

		if kind == "resource_finalize":
			var resource_path = str(panel._pending_resource_action.get("resource", ""))
			if bool(json.get("success", false)):
				panel._view.add_agent_message(str(json.get("answer", "Структурные изменения ресурса применены.")),
					str(json.get("history_entry_id", "")))
			elif bool(json.get("restored", false)):
				panel._view.add_warning(str(json.get("answer", "Исходный ресурс восстановлен.")))
				if panel._resource_executor:
					panel._resource_executor.reload_after_recovery(resource_path)
			else:
				panel._view.add_error(str(json.get("answer", "Не удалось безопасно завершить транзакцию ресурса.")))
			panel._pending_resource_action = {}
			panel._pending_resource_expected_hash = ""
			panel._pending_resource_semantic_hash = ""
			panel._pending_resource_dependency_fingerprint = ""
			panel._discard_pending_finalize("resource")
			panel._last_pending_action_type = ""
			panel._last_pending_action_paths = PackedStringArray()
			return

		if kind == "project_settings_finalize":
			if bool(json.get("success", false)):
				panel._view.add_agent_message(str(json.get("answer", "Настройки проекта применены.")),
					str(json.get("history_entry_id", "")))
				panel._view.add_warning("Перезапустите редактор Godot, чтобы все настройки и autoload гарантированно обновились.")
			elif bool(json.get("restored", false)):
				panel._view.add_warning(str(json.get("answer", "Исходный project.godot восстановлен. Перезапустите редактор.")))
			else:
				panel._view.add_error(str(json.get("answer", "Не удалось безопасно завершить транзакцию настроек.")))
			panel._pending_project_settings_action = {}
			panel._pending_project_settings_expected_hash = ""
			panel._pending_project_settings_semantic_hash = ""
			panel._discard_pending_finalize("project_settings")
			panel._last_pending_action_type = ""
			panel._last_pending_action_paths = PackedStringArray()
			return

		if kind == "scene_finalize":
			var scene_path = str(panel._pending_scene_action.get("scene", ""))
			if bool(json.get("success", false)):
				panel._view.add_agent_message(str(json.get("answer", "Структурные изменения сцены применены.")),
					str(json.get("history_entry_id", "")))
			elif bool(json.get("restored", false)):
				panel._view.add_warning(str(json.get("answer", "Исходная сцена восстановлена.")))
				if panel._scene_executor:
					panel._scene_executor.reload_after_recovery(scene_path)
			else:
				panel._view.add_error(str(json.get("answer", "Не удалось безопасно завершить транзакцию сцены.")))
			panel._pending_scene_action = {}
			panel._pending_scene_expected_hash = ""
			panel._pending_scene_semantic_hash = ""
			panel._discard_pending_finalize("scene")
			panel._last_pending_action_type = ""
			panel._last_pending_action_paths = PackedStringArray()
			return

		if kind == "rollback_preview":
			if bool(json.get("found", false)):
				if bool(json.get("blocked", false)):
					# Тот же файл агент правил позже. Откатывать через эти
					# правки нельзя — потерялась бы их работа. Объясняем и
					# НЕ предлагаем подтверждение: тут нечего подтверждать.
					panel._view.add_warning(str(json.get("description", "")))
					panel._view.scroll_to_end(true)
					panel._rollback_entry_id = ""
					return
				# Расширение одиночного отката до ВСЕЙ цепочки плана возможно
				# ТОЛЬКО когда адрес не указан (кнопка «откатить последнее» в
				# дополнительных настройках). При клике по карточке сообщения
				# адрес есть, и пользователь ждёт отката именно этого шага —
				# раньше здесь молча откатывался весь план целиком.
				var pv_chain := str(json.get("chain_id", ""))
				var pv_chain_total := int(json.get("chain_total", 0))
				if panel._rollback_entry_id == "" and pv_chain != "" and pv_chain_total > 1:
					panel._show_plan_rollback_dialog(pv_chain, panel._t("plan_rb_step_desc") % [pv_chain_total, pv_chain_total])
				else:
					panel._show_rollback_dialog(str(json.get("description", "")))
			else:
				# Откатывать нечего — это ответ на нажатие кнопки, поэтому
				# прокручиваем принудительно: иначе человек, читавший историю
				# выше, решит, что кнопка отката просто не сработала.
				panel._view.add_system(panel._t("rb_gone") if bool(json.get("gone", false)) else panel._t("rb_nothing"))
				panel._view.scroll_to_end(true)
				panel._rollback_entry_id = ""
			return

		if kind == "rollback":
			var msg = str(json.get("message", panel._t("rollback_done")))
			panel._view.add_success(panel._t("success_prefix") + msg)
			panel._note_autoload_removed(json)
			if bool(json.get("requires_editor_restart", false)):
				panel._view.add_warning("Перезапустите редактор Godot, чтобы восстановленные настройки проекта полностью применились.")
			# Синхронизируем откаченные файлы с открытыми вкладками. Иначе
			# вкладка показывает ДО-откатный текст, и Godot может позже
			# молча пересохранить его ПОВЕРХ результата отката.
			var paths = json.get("paths")
			if paths is Array:
				for p in paths:
					if FileAccess.file_exists(str(p)):
						panel._sync_open_script_with_disk(str(p))
						panel._auto_reload_changed_scene(str(p))
					else:
						# Откат удалил созданный файл — закрываем его вкладку,
						# иначе Godot держит «призрака» и может пересохранить файл обратно.
						panel._close_ghost_script_tab(str(p))
			# Подсвечиваем восстановленный после отката блок (или гасим старое).
			var rb_path = json.get("changed_path")
			var rb_block = json.get("changed_block")
			if rb_path != null and rb_block != null and str(rb_block) != "":
				if panel._hl: panel._hl.apply(str(rb_path), str(rb_block))
			else:
				if panel._hl: panel._hl.clear()
			panel._maybe_prompt_project_reload(json)
			await panel.get_tree().process_frame
			panel._scroll_chat_to_end()
			return

		if kind == "check_log":
			var was_auto = panel._auto_check
			panel._auto_check = false
			var found := int(json.get("found", 0))
			var log_info := str(json.get("log_time", "?"))
			if found == 0:
				if was_auto:
					panel._view.add_system(panel._t("log_auto_ok") % log_info)
				else:
					panel._view.add_success(panel._t("log_ok") % log_info)
			else:
				var head = panel._t("log_errs_auto") if was_auto else panel._t("log_errs")
				panel._view.add_system(head + str(found) + " (" + panel._t("log_from") + " " + log_info + ")\n" + str(json.get("summary", "")))
				if panel.action_label and panel.pending_action_box:
					var desc_text = panel._t("send_errors_q") % str(found)
					panel._set_pending_action(true, desc_text)
					panel._pending_log_send = true
					panel._guard_confirm_buttons()
					panel._view.add_confirmation_card(
						desc_text,
						func(): panel._on_confirm_pressed(),
						func(): panel._on_reject_pressed()
					)
			await panel.get_tree().process_frame
			return

		if kind == "safe_rename_preview":
			var prep = json.get("prepared", {})
			panel._safe_rename_prepared = prep
			var ref_count := int(prep.get("reference_count", 0))
			var file_count := int(prep.get("file_count", 0))
			var aff_count := (prep.get("affected_paths", []) as Array).size()
			if panel._safe_rename_status_label:
				panel._safe_rename_status_label.text = panel._t("safe_rename_preview_found") % [ref_count, file_count, aff_count]
			var diffs = prep.get("diffs", [])
			if diffs is Array and not diffs.is_empty() and panel._view:
				var head_msg := "Предпросмотр безопасного переименования: %s -> %s" % [prep.get("old_path"), prep.get("new_path")]
				var comp_scr := str(prep.get("companion_script", ""))
				if comp_scr != "":
					head_msg += "\n(Прикреплённый скрипт сцены: %s)" % comp_scr
				panel._view.add_system(head_msg)
				for d in diffs:
					if d is Dictionary:
						panel._view.add_readonly_diff(str(d.get("path", "")), d)
			return

		if kind == "safe_rename_apply":
			if bool(json.get("ok", false)):
				var old_p := str(json.get("old_path", ""))
				var new_p := str(json.get("new_path", ""))
				panel._sync_resource_uid(old_p, new_p)
				var ref_cnt := int(json.get("reference_count", 0))
				var file_cnt := int(json.get("file_count", 0))
				var changed_paths = json.get("changed_paths", [])
				# ЗАДАЧА 3: сервер перечислил изменённые файлы — обновляем их
				# поимённо вместо полного пересчёта проекта.
				panel._refresh_changed_paths([old_p, new_p, changed_paths])
				if changed_paths is Array:
					for cp in changed_paths:
						panel._sync_open_script_with_disk(str(cp))
						panel._auto_reload_changed_scene(str(cp))
				panel._close_ghost_script_tab(old_p)
				if FileAccess.file_exists(new_p) and new_p.ends_with(".gd"):
					var scr = ResourceLoader.load(new_p, "", ResourceLoader.CACHE_MODE_REPLACE)
					if scr is Script:
						scr.reload(true)
						EditorInterface.edit_script(scr, -1, 0, false)
				panel._remap_scenes_to_reopen(old_p, new_p)
				panel._reopen_scenes_after_write()
				var msg = panel._t("safe_rename_success") % [old_p, new_p, ref_cnt, file_cnt]
				if panel._view:
					panel._view.add_agent_message(msg, str(json.get("entry_id", "")))
				if panel._safe_rename_dialog:
					panel._safe_rename_dialog.hide()
				panel._maybe_prompt_project_reload(json)
			else:
				var err_msg = str(json.get("error", "Ошибка применения переименования"))
				if panel._safe_rename_status_label:
					panel._safe_rename_status_label.text = err_msg
				panel._log_error(err_msg)
			return

		if kind == "safe_node_rename_preview":
			var prep = json.get("prepared", {})
			panel._safe_node_rename_prepared = prep
			var ref_count := int(prep.get("reference_count", 0))
			var file_count := int(prep.get("file_count", 0))
			var aff_count := (prep.get("affected_paths", []) as Array).size()
			if panel._safe_node_rename_status_label:
				panel._safe_node_rename_status_label.text = panel._t("safe_node_rename_preview_found") % [ref_count, file_count, aff_count]
			var diffs = prep.get("diffs", [])
			if diffs is Array and not diffs.is_empty() and panel._view:
				panel._view.add_system("Предпросмотр безопасного переименования узла: %s -> %s в %s" % [prep.get("node_path"), prep.get("new_name"), prep.get("scene")])
				for d in diffs:
					if d is Dictionary:
						panel._view.add_readonly_diff(str(d.get("path", "")), d)
			return

		if kind == "safe_node_rename_apply":
			if bool(json.get("ok", false)):
				var scene_p := str(json.get("scene", ""))
				var old_p := str(json.get("node_path", ""))
				var new_p := str(json.get("new_name", ""))
				var ref_cnt := int(json.get("reference_count", 0))
				var file_cnt := int(json.get("file_count", 0))
				var changed_paths = json.get("changed_paths", [])
				# ЗАДАЧА 3: список изменённых файлов известен — точечное обновление.
				panel._refresh_changed_paths([scene_p, changed_paths])
				if changed_paths is Array:
					for cp in changed_paths:
						panel._sync_open_script_with_disk(str(cp))
						panel._auto_reload_changed_scene(str(cp))
				var msg = panel._t("safe_node_rename_success") % [old_p, new_p, scene_p, ref_cnt, file_cnt]
				if panel._view:
					panel._view.add_agent_message(msg, str(json.get("entry_id", "")))
				if panel._safe_node_rename_dialog:
					panel._safe_node_rename_dialog.hide()
			else:
				var err_msg = str(json.get("error", "Ошибка применения переименования узла"))
				if panel._safe_node_rename_status_label:
					panel._safe_node_rename_status_label.text = err_msg
				panel._log_error(err_msg)
			# ЗАДАЧА 3: собственное переименование завершено (успех или
			# отказ) — перехват снова активен.
			panel._node_rename_suppress = maxi(0, panel._node_rename_suppress - 1)
			return

		# После подтверждённого WRITE-действия — синхронизируем открытую вкладку.
		# При пакетном чтении файлов _last_pending_action_type пуст — ничего не трогаем.
		if kind == "confirm" and panel._last_pending_action_type != "":
			var changed_paths = json.get("changed_paths")
			if changed_paths is Array:
				for changed_path in changed_paths:
					panel._sync_open_script_with_disk(str(changed_path))
					panel._auto_reload_changed_scene(str(changed_path))
			else:
				panel._force_reload_open_script()
			if panel._last_pending_action_path != "":
				panel._auto_reload_changed_scene(panel._last_pending_action_path)
			if panel._last_pending_action_dest != "":
				panel._auto_reload_changed_scene(panel._last_pending_action_dest)
			panel._reopen_scenes_after_write()  # v49: вернуть сцены, закрытые перед записью, — уже в новом виде
			panel._last_pending_action_type = ""
			panel._last_pending_action_path = ""
			panel._last_pending_action_dest = ""
			panel._last_pending_action_paths = PackedStringArray()
			# Открываем изменённый файл и подсвечиваем строки, написанные агентом.
			var ch_path = json.get("changed_path")
			var ch_block = json.get("changed_block")
			if ch_path != null and ch_block != null and str(ch_block) != "":
				if panel._hl: panel._hl.apply(str(ch_path), str(ch_block))

		# Текстовый ответ ИИ (не печатаем пустые ответы)
		var has_answer: bool = json.has("answer") and json["answer"] != null and str(json["answer"]) != ""
		if has_answer:
			# history_entry_id есть только у сообщения о ПРИМЕНЁННОМ изменении
			# (ответ на подтверждение действия или шаг плана). Именно оно и
			# получает кнопку отката, и именно своё изменение откатывает.
			# Обычный ответ модели приходит без адреса — кнопки у него нет.
			panel._view.add_agent_message(str(json["answer"]),
				str(json.get("history_entry_id", "")))
			panel._request_chats("list", {})  # обновить авто-названия чатов
		var battle_choice = json.get("battle_choice")
		if battle_choice is Dictionary:
			panel._show_battle_choice_summary(battle_choice)

		# Промежуточное подтверждение файла из пачки на чтение:
		# сервер НЕ ходил в браузер, просто спрашивает про следующий файл.
		var nxt = json.get("next_confirmation")
		if nxt != null and panel.action_label and panel.pending_action_box:
			var desc = str(nxt.get("description", panel._t("agent_wants_file")))
			panel._set_pending_action(true, desc)
			panel._guard_confirm_buttons()
			panel._view.add_confirmation_card(
				desc,
				func(): panel._on_confirm_pressed(),
				func(): panel._on_reject_pressed()
			)
			await panel.get_tree().process_frame
			return

		# WRITE-действие, требующее подтверждения
		var pending = json.get("pending_action")
		if pending != null and panel.action_label and panel.pending_action_box:
			var description = json.get("pending_action_description", panel._t("agent_wants_action"))
			if description == null: description = panel._t("agent_wants_action")
			# Красивый предпросмотр: сервер присылает ЧИСТЫЙ код (без JSON-обёртки)
			# и, если смог посчитать, разобранный дифф — что добавится и что удалится.
			var pcode = json.get("pending_action_code")
			var pdiff = json.get("pending_action_diff")
			var pdiffs = json.get("pending_action_diffs")
			var diff_data: Dictionary = pdiff if pdiff is Dictionary else {}
			panel._last_pending_action_type = str(pending.get("action", ""))
			panel._last_pending_action_path = str(pending.get("path", ""))
			if panel._last_pending_action_path.is_empty():
				panel._last_pending_action_path = str(pending.get("scene", ""))
			panel._last_pending_action_dest = str(pending.get("dest", ""))
			# Список мест с галочками (Этап 4.3): показываем в карточке ДО
			# подтверждения, чтобы снятые места были видны пользователю.
			panel._pending_rename_usages = []
			var raw_usages = json.get("pending_action_usages", json.get("suggested_usages", []))
			if raw_usages is Array:
				panel._pending_rename_usages = raw_usages
			panel._last_pending_action_paths = PackedStringArray()
			var raw_paths = pending.get("paths", [])
			if raw_paths is Array and not raw_paths.is_empty():
				for raw_path in raw_paths:
					panel._last_pending_action_paths.append(str(raw_path))
			elif pending.has("affected_paths"):
				for raw_path in pending.get("affected_paths", []):
					panel._last_pending_action_paths.append(str(raw_path))
			panel._set_pending_action(true, str(description))
			panel._guard_confirm_buttons()
			if panel._last_pending_action_type in ["edit_scene", "create_scene"]:
				var scene_preview = panel._prepare_scene_action(pending, json.get("scene_prepare", {}))
				if not bool(scene_preview.get("ok", false)):
					panel._view.add_warning("Godot отклонил предпросмотр сцены: " + str(scene_preview.get("error", "")))
					panel._on_reject_pressed()
					return
				var preview_lines = scene_preview.get("changes", [])
				if preview_lines is Array and not preview_lines.is_empty():
					panel._view.add_system("Предпросмотр структурных изменений:\n• " + "\n• ".join(preview_lines))
			elif panel._last_pending_action_type == "edit_project_settings":
				var settings_preview = panel._prepare_project_settings_action(
					pending, json.get("project_settings_prepare", {}))
				if not bool(settings_preview.get("ok", false)):
					panel._view.add_warning("Godot отклонил настройки проекта: " + str(settings_preview.get("error", "")))
					panel._on_reject_pressed()
					return
				var settings_lines = settings_preview.get("changes", [])
				if settings_lines is Array and not settings_lines.is_empty():
					panel._view.add_system("Предпросмотр настроек проекта:\n• " + "\n• ".join(settings_lines))
			elif panel._last_pending_action_type == "edit_resource":
				var resource_preview = panel._prepare_resource_action(
					pending, json.get("resource_prepare", {}))
				if not bool(resource_preview.get("ok", false)):
					panel._view.add_warning("Godot отклонил ресурс: " + str(resource_preview.get("error", "")))
					panel._on_reject_pressed()
					return
				var resource_lines = resource_preview.get("changes", [])
				if resource_lines is Array and not resource_lines.is_empty():
					panel._view.add_system("Предпросмотр структурных изменений ресурса:\n• " +
						"\n• ".join(resource_lines))

			# Дифф сам по себе достаточен для карточки: patch_file, который
			# только УДАЛЯЕТ код, приходит с пустым replace — раньше такой
			# правке доставалась безликая карточка подтверждения.
			if pdiffs is Array and not (pdiffs as Array).is_empty():
				for raw_diff in pdiffs:
					if raw_diff is Dictionary:
						var readonly_diff := raw_diff as Dictionary
						panel._view.add_readonly_diff(str(readonly_diff.get("path", "")), readonly_diff)
				var usage_card: PanelContainer = panel._view.add_confirmation_card(
					str(description),
					func(): panel._on_confirm_pressed(),
					func(): panel._on_reject_pressed()
				)
				panel._attach_rename_usage_checklist(usage_card)
			elif (pcode != null and str(pcode) != "") or not diff_data.is_empty():
				var file_path = panel._last_pending_action_path if panel._last_pending_action_path != "" else panel._last_pending_action_dest
				var card = panel._view.add_diff_preview(file_path, str(pcode) if pcode != null else "", diff_data)
				if card:
					card.diff_applied.connect(func(_p): panel._on_confirm_pressed())
					card.diff_rejected.connect(func(_p): panel._on_reject_pressed())
			else:
				var fallback_card: PanelContainer = panel._view.add_confirmation_card(
					str(description),
					func(): panel._on_confirm_pressed(),
					func(): panel._on_reject_pressed()
				)
				panel._attach_rename_usage_checklist(fallback_card)
		elif panel.pending_action_box:
			panel._set_pending_action(false)
			# Ни текста, ни действий — не молчим, чтобы ответ не "пропадал" бесследно.
			if not has_answer and (kind == "chat" or kind == "confirm"):
				panel._view.add_system(panel._t("empty_response"))

		await panel.get_tree().process_frame
	else:
		if kind == "chat":
			panel._restore_chat_draft()
		if kind == "runtime_check_bind":
			panel._send_runtime_check_result("bridge_unavailable", {})
			return
		if kind == "runtime_check_result":
			if response_code in [400, 403, 409, 410, 413]:
				panel._log_error("Сервер окончательно отклонил результат локальной игровой проверки.")
				panel._clear_runtime_check_state()
			else:
				panel._log_error("Сервер временно не принял результат; отправка будет повторена.")
			return
		if kind == "runtime_result":
			panel._pending_runtime_request = {}
			if panel._runtime_timeout_timer:
				panel._runtime_timeout_timer.stop()
			panel._log_error("Runtime inspection завершён без ответа модели: " + str(response_code))
			return
		# Отказ сервера на отчёте о транзакции. ЗАДАЧА 2: правило «после
		# терминального кода не повторяемся вечно» было написано трижды и
		# разошлось; теперь оно одно, а вид транзакции выбирает, что забыть.
		if kind in ["scene_finalize", "project_settings_finalize", "resource_finalize"]:
			var finalize_kind = kind.trim_suffix("_finalize")
			if not (response_code in FINALIZE_TERMINAL_CODES):
				panel._schedule_finalize_retry(finalize_kind)
				return
			var fallback := "Сервер отклонил завершение транзакции."
			if json:
				fallback = str(json.get("answer", json.get("error", fallback)))
			panel._view.add_error(fallback)
			match finalize_kind:
				"scene":
					panel._pending_scene_action = {}
					panel._pending_scene_expected_hash = ""
					panel._pending_scene_semantic_hash = ""
				"project_settings":
					panel._pending_project_settings_action = {}
					panel._pending_project_settings_expected_hash = ""
					panel._pending_project_settings_semantic_hash = ""
				"resource":
					panel._pending_resource_action = {}
					panel._pending_resource_expected_hash = ""
					panel._pending_resource_semantic_hash = ""
					panel._pending_resource_dependency_fingerprint = ""
			panel._discard_pending_finalize(finalize_kind)
			panel._last_pending_action_type = ""
			panel._last_pending_action_paths = PackedStringArray()
			return
			return
		if kind == "check_log" and panel._auto_check:
			# Авто-проверка не спамит в чат: нет лога, лог уже отправлялся,
			# сервер занят или выключен — просто тихо пропускаем.
			panel._auto_check = false
			if json and json.has("error"):
				print("Авто-проверка лога пропущена: ", str(json["error"]))
			return
		if kind == "api_cache_status":
			panel._schedule_api_cache_check_retry()
			return
		if kind in ["safe_rename_preview", "safe_rename_apply", "safe_node_rename_preview", "safe_node_rename_apply"]:
			var sr_err := str(json.get("error", "Ошибка операции переименования")) if json is Dictionary else ("Ошибка HTTP " + str(response_code))
			if kind.begins_with("safe_node_rename_"):
				if panel._safe_node_rename_status_label:
					panel._safe_node_rename_status_label.text = sr_err
				if kind == "safe_node_rename_apply":
					panel._node_rename_suppress = maxi(0, panel._node_rename_suppress - 1)
			else:
				if panel._safe_rename_status_label:
					panel._safe_rename_status_label.text = sr_err
			panel._log_error(sr_err)
			return
		if kind == "confirm":
			if panel._last_pending_action_type not in ["edit_scene", "create_scene", "rename_node", "reparent_node", "delete_node", "edit_project_settings", "edit_resource", "inspect_runtime", "run_check"]:
				panel._reopen_scenes_after_write()  # v49: действие не выполнено — вернуть закрытые сцены
		var err_msg = panel._t("srv_no_reply")
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
				panel._plan_rollback_force_next = true
				panel._view.add_warning(panel._t("plan_rb_needs_force"))
				panel._show_plan_rollback_dialog(panel._plan_rollback_chain_id, panel._t("plan_rb_force_desc"))
				await panel.get_tree().process_frame
				panel._scroll_chat_to_end()
				return
			panel._rollback_force_next = true
			# Запоминаем, ДЛЯ КАКОГО адреса взведён force. Раньше флаг был
			# общим: нажатие кнопки отката у любого другого сообщения тут же
			# уходило с force=true — без предпросмотра и без подтверждения — и
			# перезаписывало ручные правки пользователя в другом файле.
			panel._rollback_force_entry_id = panel._rollback_entry_id
		panel._log_error((panel._t("srv_error") % str(response_code)) + err_msg)

static func _log_error(panel, msg: String) -> void:
	# Раньше текст уходил в chat_log — а его прячет agent_chat_view.setup(),
	# поэтому ВСЕ ошибки были невидимы пользователю. Теперь это карточка в чате.
	if panel._view:
		panel._view.flush()
		panel._view.add_error(panel._t("error_prefix") + msg)
	else:
		# Панель ещё не собрана — хотя бы не теряем текст ошибки молча.
		push_error("[Godot Agent] " + msg)

static func _scroll_chat_to_end(panel) -> void:
	# Раньше здесь дёргался chat_log.scroll_to_line(), но ChatLog скрыт —
	# прокрутка уходила в невидимый узел. Карточки прокручивает сам вид чата.
	if panel._view:
		panel._view.scroll_to_end()

static func _guard_confirm_buttons(panel) -> void:
	# Защита от случайных быстрых/двойных кликов: когда появляется НОВОЕ
	# подтверждение, кнопки ненадолго блокируются, чтобы второй клик по
	# инерции не одобрил следующее действие мгновенно.
	# ВАЖНО: без await/корутин. При перезагрузке плагина Godot отменял
	# приостановленный await — и кнопки навсегда оставались серыми.
	if not panel.confirm_button or not panel.reject_button:
		return
	panel.confirm_button.disabled = true
	panel.reject_button.disabled = true
	panel._guard_until_msec = Time.get_ticks_msec() + 700
	if panel._guard_timer:
		panel._guard_timer.stop()
		panel._guard_timer.wait_time = 0.7
		panel._guard_timer.start()

static func _on_guard_timeout(panel) -> void:
	if not panel._is_network_busy and panel.confirm_button and panel.reject_button:
		panel.confirm_button.disabled = false
		panel.reject_button.disabled = false

static func _reconcile_confirm_buttons(panel) -> void:
	# Страховка на случай, если таймер-охранник не сработал из-за
	# перезагрузки скрипта: раз в секунду проверяем и возвращаем кнопки,
	# если окно подтверждения открыто, сеть свободна и время охраны прошло.
	if not panel.confirm_button or not panel.reject_button:
		return
	if not panel._has_pending_action():
		return
	if panel._is_network_busy:
		return
	if Time.get_ticks_msec() >= panel._guard_until_msec and (panel.confirm_button.disabled or panel.reject_button.disabled):
		panel.confirm_button.disabled = false
		panel.reject_button.disabled = false

static func _auto_reload_changed_scene(panel, p: String) -> void:
	# v46: агент изменил сцену на диске — если она открыта в редакторе, перечитываем
	# её САМИ, чтобы пользователю не приходилось вручную отвечать на вопрос
	# «файлы изменены снаружи — перезагрузить?» после каждого действия агента.
	#
	# ЗАДАЧА 1: молча перезагружать нельзя. Если в открытой сцене есть
	# несохранённые правки пользователя, reload_scene_from_path их уничтожит
	# без вопроса — это единственное место в плане с риском потери данных.
	if not (p.ends_with(".tscn") or p.ends_with(".scn")):
		return
	if not FileAccess.file_exists(p):
		return
	for sp in EditorInterface.get_open_scenes():
		if str(sp) != p:
			continue
		if panel._scene_reload_would_lose_edits(p):
			panel._scene_reload_blocked_notice(p)
			return
		EditorInterface.reload_scene_from_path(p)
		panel._mark_scene_clean(p)
		return

## Есть ли в открытой сцене p правки, которые потеряются при перезагрузке.
##
## Публичного `is_scene_dirty()` в Godot 4.6 нет: `EditorUndoRedoManager.
## is_history_unsaved()` существует только в C++ и в скрипты не выведена.
## Поэтому чистота выводится из публичного UndoRedo.get_version():
##   - версия 0 — сцена открыта и ни разу не менялась, терять нечего;
##   - версия совпадает с записанной при последнем сохранении — тоже чисто;
##   - всё остальное (правки есть, а когда сцену сохраняли плагин не видел) —
##     считается грязной. Ложное «грязно» стоит одного лишнего сообщения,
##     ложное «чисто» стоит пользователю его работы.
static func _scene_reload_would_lose_edits(panel, p: String) -> bool:
	if not (p.ends_with(".tscn") or p.ends_with(".scn")):
		return false
	var root := EditorInterface.get_edited_scene_root()
	if root == null or str(root.get_scene_file_path()) != p:
		# Редактируемая сцена — другая или её нет вовсе: несохранённые правки
		# пользователя живут только в ней, терять нечего.
		return false
	var history = panel._scene_history(root)
	if history == null:
		return true
	# Пустая история — правок не было: сцена на диске и в памяти одно и то же.
	# Именно этот случай и ломала первую версию проверки: версия истории у
	# только что открытой сцены равна 1, а не 0, хотя правок нет.
	if int(history.get_history_count()) == 0:
		return false
	if panel._scene_saved_versions.has(p):
		return int(panel._scene_saved_versions[p]) != int(history.get_version())
	return true

## История отмены редактируемой сцены; null, если её не узнать.
##
## Тип возврата объявлен ЯВНО. Без него вызывающий `var history := ...` не
## выводится: get_history_undo_redo() отдаёт Object, а не UndoRedo, и Godot
## отказывается угадывать. Такая ошибка не видна ни в --check-only на
## agent_entry.gd (он не подтягивает панель статически), ни в 109 проверках
## обвязки — панель просто молча не грузится, и у пользователя исчезает чат.
static func _scene_history(panel, root: Node) -> UndoRedo:
	var manager := EditorInterface.get_editor_undo_redo()
	if manager == null:
		return null
	return manager.get_history_undo_redo(manager.get_object_history_id(root))

## Версия истории отмены редактируемой сцены p; -1, если её не узнать.
static func _scene_undo_version(panel, p: String) -> int:
	var root := EditorInterface.get_edited_scene_root()
	if root == null or str(root.get_scene_file_path()) != p:
		return -1
	var history = panel._scene_history(root)
	if history == null:
		return -1
	return int(history.get_version())

## Запомнить, что сцену p только что сохранили или перечитали с диска.
static func _mark_scene_clean(panel, p: String) -> void:
	var version = panel._scene_undo_version(p)
	if version >= 0:
		panel._scene_saved_versions[p] = version

## Сигнал EditorPlugin.scene_saved: пользователь нажал Ctrl+S — это тоже
## сохранение, и после него вернуть сцену можно.
static func _on_editor_scene_saved(panel, path: String) -> void:
	if path != "":
		panel._mark_scene_clean(path)
		# Исполнитель сцены ведёт ту же таблицу версий для восстановления
		# после неудачной транзакции — иначе он считал бы уже сохранённую
		# сцену грязной и пропускал авто-восстановление.
		if panel._scene_executor and panel._scene_executor.has_method("note_scene_saved"):
			panel._scene_executor.call("note_scene_saved", path)

## Сказать в чате, почему сцена не перечитана. Молчание здесь выглядело бы
## как «агент забыл про мою сцену», и пользователь стал бы искать причину.
static func _scene_reload_blocked_notice(panel, p: String) -> void:
	var message = panel._t("scene_reload_blocked") % p
	push_warning("[Godot Agent] " + message)
	if panel._view:
		panel._view.add_warning(message)
