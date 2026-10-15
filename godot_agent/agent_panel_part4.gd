@tool
extends RefCounted

# Модуль agent_panel_part4: методы вынесены «пилой» split_gd из agent_panel.gd.
# Реализация живёт ЗДЕСЬ; в доноре на месте метода — тонкая обёртка,
# поэтому connect()/call() по исходным именам продолжают работать.
# Тело работает через параметр panel: к членам донора — panel.<член>,
# к другим методам донора — panel.<метод> (через его обёртку).

# --- константы, скопированные из донора (неизменяемы) ---
const REFACTOR_FILE_PREVIEW_URL = AgentServer.URL_PROJECT_REFACTOR_FILE_PREVIEW
const REFACTOR_FILE_APPLY_URL = AgentServer.URL_PROJECT_REFACTOR_FILE_APPLY
const REFACTOR_FILE_POST_MOVE_SYNC_URL = AgentServer.URL_PROJECT_REFACTOR_FILE_POST_MOVE_SYNC
const REFACTOR_NODE_PREVIEW_URL = AgentServer.URL_SCENE_REFACTOR_NODE_PREVIEW
const REFACTOR_NODE_APPLY_URL = AgentServer.URL_SCENE_REFACTOR_NODE_APPLY

static func _on_settings_pressed(panel) -> void:
	var T = panel._T()
	if panel._safe_rename_dialog and panel._safe_rename_dialog.visible:
		panel._safe_rename_dialog.hide()
	if panel._safe_node_rename_dialog and panel._safe_node_rename_dialog.visible:
		panel._safe_node_rename_dialog.hide()
	if panel._settings_dialog == null:
		panel._settings_dialog = AcceptDialog.new()
		panel._settings_dialog.exclusive = false
		# Содержимое обёрнуто в панель со стилем аддона
		var wrap := PanelContainer.new()
		if T:
			wrap.add_theme_stylebox_override("panel", T.panel_style("agent"))
		var box := VBoxContainer.new()
		box.add_theme_constant_override("separation", 6)
		wrap.add_child(box)

		# Основная настройка: безопасное переименование файлов и узлов прямо в редакторе Godot
		panel._safe_rename_check = CheckBox.new()
		panel._safe_rename_check.button_pressed = panel._safe_rename_enabled
		panel._safe_rename_check.toggled.connect(panel._on_safe_rename_toggled)
		box.add_child(panel._safe_rename_check)

		var policy_group := VBoxContainer.new()
		policy_group.name = "AccessPolicyGroup"
		var policy_header := Label.new()
		policy_header.text = panel._t("policy_group")
		policy_header.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		policy_group.add_child(policy_header)
		panel._allow_addons_check = CheckBox.new()
		panel._allow_addons_check.text = panel._t("policy_allow_addons")
		panel._allow_addons_check.tooltip_text = panel._t("policy_allow_addons_tip")
		panel._allow_addons_check.button_pressed = panel._allow_addons
		panel._allow_addons_check.toggled.connect(panel._on_allow_addons_toggled)
		policy_group.add_child(panel._allow_addons_check)
		panel._allow_self_edit_check = CheckBox.new()
		panel._allow_self_edit_check.text = panel._t("policy_allow_self_edit")
		panel._allow_self_edit_check.tooltip_text = panel._t("policy_allow_self_edit_tip")
		panel._allow_self_edit_check.button_pressed = false
		panel._allow_self_edit_check.toggled.connect(panel._on_allow_self_edit_toggled)
		policy_group.add_child(panel._allow_self_edit_check)
		panel._policy_warning_label = Label.new()
		panel._policy_warning_label.text = panel._t("policy_warning")
		panel._policy_warning_label.tooltip_text = panel._t("policy_warning_tip")
		panel._policy_warning_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		policy_group.add_child(panel._policy_warning_label)
		box.add_child(policy_group)

		# ---------------------------------------------------------------------------
		# Экспериментальные настройки (MiniLich) — заготовка нейросети для Godot.
		# Это то, что осталось от старой версии, скрыто из интерфейса настроек.
		# НЕ УДАЛЯТЬ: на этом завязаны внутренние механизмы и обработчики, оставить на будущее!
		# ---------------------------------------------------------------------------
		var exp_box := VBoxContainer.new()
		exp_box.visible = false
		box.add_child(exp_box)

		panel._settings_exp_header = Label.new()
		panel._settings_exp_header.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		panel._settings_exp_header.custom_minimum_size = Vector2(360, 0)
		if T:
			panel._settings_exp_header.add_theme_color_override("font_color", T.color("accent"))
		exp_box.add_child(panel._settings_exp_header)
		exp_box.add_child(HSeparator.new())
		panel._minilich_check = CheckBox.new()
		panel._minilich_check.button_pressed = false
		panel._minilich_check.toggled.connect(panel._on_minilich_toggled)
		exp_box.add_child(panel._minilich_check)
		panel._minilich_status_label = Label.new()
		panel._minilich_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		panel._minilich_status_label.custom_minimum_size = Vector2(360, 0)
		if T:
			panel._minilich_status_label.add_theme_color_override("font_color", T.color("dim"))
		exp_box.add_child(panel._minilich_status_label)
		panel._minilich_train_check = CheckBox.new()
		panel._minilich_train_check.button_pressed = false
		panel._minilich_train_check.toggled.connect(panel._on_train_mode_toggled)
		exp_box.add_child(panel._minilich_train_check)
		panel._minilich_train_warn = Label.new()
		panel._minilich_train_warn.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		panel._minilich_train_warn.custom_minimum_size = Vector2(360, 0)
		if T:
			panel._minilich_train_warn.add_theme_color_override("font_color", T.color("warning"))
		panel._minilich_train_warn.visible = false
		exp_box.add_child(panel._minilich_train_warn)
		exp_box.add_child(HSeparator.new())
		panel._minilich_repos_edit = LineEdit.new()
		panel._minilich_repos_edit.custom_minimum_size = Vector2(360, 0)
		if T:
			T.style_input(panel._minilich_repos_edit)
		exp_box.add_child(panel._minilich_repos_edit)
		panel._minilich_github_btn = Button.new()
		panel._minilich_github_btn.pressed.connect(panel._on_github_fetch_pressed)
		if T:
			T.style_button(panel._minilich_github_btn, "accent", false)
			panel._minilich_github_btn.icon = T.first_icon(["ExternalLink", "Load"])
		exp_box.add_child(panel._minilich_github_btn)
		panel._minilich_github_label = Label.new()
		panel._minilich_github_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		panel._minilich_github_label.custom_minimum_size = Vector2(360, 0)
		if T:
			panel._minilich_github_label.add_theme_color_override("font_color", T.color("dim"))
		exp_box.add_child(panel._minilich_github_label)

		# Раздел редких инструментов (advanced_box)
		if panel.advanced_box and panel.advanced_box.get_parent():
			box.add_child(HSeparator.new())
			panel._settings_adv_header = Label.new()
			if T:
				panel._settings_adv_header.add_theme_color_override("font_color", T.color("accent"))
			box.add_child(panel._settings_adv_header)
			panel.advanced_box.get_parent().remove_child(panel.advanced_box)
			box.add_child(panel.advanced_box)
			panel.advanced_box.visible = true

		# Раздел обновления плагина
		box.add_child(HSeparator.new())
		panel._update_check_btn = Button.new()
		panel._update_check_btn.text = panel._t("update_check_now_btn")
		panel._update_check_btn.tooltip_text = panel._t("update_check_now_tip")
		panel._update_check_btn.pressed.connect(panel._on_check_updates_pressed)
		if T:
			T.style_button(panel._update_check_btn, "neutral", false)
			panel._update_check_btn.icon = T.first_icon(["Reload", "Loop", "ActionCopy"])
		box.add_child(panel._update_check_btn)
		panel._update_check_status_label = Label.new()
		panel._update_check_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		panel._update_check_status_label.custom_minimum_size = Vector2(360, 0)
		if T:
			panel._update_check_status_label.add_theme_color_override("font_color", T.color("dim"))
		box.add_child(panel._update_check_status_label)
		panel._settings_dialog.add_child(wrap)
		panel.add_child(panel._settings_dialog)
	panel._settings_dialog.title = panel._t("settings_title")
	if panel._safe_rename_check:
		panel._safe_rename_check.text = panel._t("safe_rename_toggle")
		panel._safe_rename_check.tooltip_text = panel._t("safe_rename_tip")
		panel._safe_rename_check.button_pressed = panel._safe_rename_enabled
	if panel._allow_addons_check:
		panel._allow_addons_check.text = panel._t("policy_allow_addons")
		panel._allow_addons_check.tooltip_text = panel._t("policy_allow_addons_tip")
		panel._allow_addons_check.set_pressed_no_signal(panel._allow_addons)
	if panel._allow_self_edit_check:
		panel._allow_self_edit_check.text = panel._t("policy_allow_self_edit")
		panel._allow_self_edit_check.tooltip_text = panel._t("policy_allow_self_edit_tip")
		panel._allow_self_edit_check.set_pressed_no_signal(panel._allow_self_edit)
	if panel._policy_warning_label:
		panel._policy_warning_label.visible = panel._allow_self_edit
		panel._policy_warning_label.text = panel._t("policy_warning")
		panel._policy_warning_label.tooltip_text = panel._t("policy_warning_tip")
	if panel._safe_rename_button:
		panel._safe_rename_button.visible = false
	if panel._safe_node_rename_button:
		panel._safe_node_rename_button.visible = false
	if panel._live_toggle:
		panel._live_toggle.visible = false
	panel._settings_exp_header.text = panel._t("experimental_hdr") + ":"
	panel._minilich_check.text = panel._t("minilich_toggle")
	panel._minilich_train_check.text = panel._t("train_mode_toggle")
	panel._minilich_train_warn.text = panel._t("train_mode_warn")
	if panel._minilich_repos_edit:
		panel._minilich_repos_edit.placeholder_text = panel._t("github_repos_hint")
	if panel._minilich_github_btn:
		panel._minilich_github_btn.text = panel._t("github_fetch_btn")
	if panel._minilich_github_label:
		panel._minilich_github_label.text = ""
	if panel._settings_adv_header:
		panel._settings_adv_header.text = panel._t("advanced_show") + ":"
	if panel._update_check_btn:
		panel._update_check_btn.text = panel._t("update_check_now_btn")
		panel._update_check_btn.tooltip_text = panel._t("update_check_now_tip")
	if panel._update_check_status_label:
		var cur_v: String = panel._updater.get_current_version() if panel._updater else "0.7.0"
		panel._update_check_status_label.text = panel._t("update_current_version") % cur_v
	panel._minilich_status_label.text = panel._t("minilich_loading")
	panel._settings_dialog.popup_centered()
	# Статус запрашиваем БЕЗ автозапуска сервера — просто открытие настроек
	# не должно поднимать сервер.
	panel._request_chats("minilich_status", {}, false)

static func _check_updates_startup(panel) -> void:
	if panel._updater:
		panel._updater.check_for_updates(false)

static func _open_update_dialog(panel, info: Dictionary) -> void:
	var T = panel._T()
	if panel._update_dialog == null:
		panel._update_dialog = AcceptDialog.new()
		panel._update_dialog.exclusive = false
		panel._update_dialog.name = "UpdateDialog"
		panel._update_dialog.custom_minimum_size = Vector2(460, 340)
		var wrap := PanelContainer.new()
		if T:
			wrap.add_theme_stylebox_override("panel", T.panel_style("agent"))
		var box := VBoxContainer.new()
		box.add_theme_constant_override("separation", 8)
		wrap.add_child(box)

		panel._update_dialog_version_label = Label.new()
		panel._update_dialog_version_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		if T:
			panel._update_dialog_version_label.add_theme_color_override("font_color", T.color("accent"))
		box.add_child(panel._update_dialog_version_label)

		var changelog_hdr := Label.new()
		changelog_hdr.text = panel._t("update_changelog")
		box.add_child(changelog_hdr)

		panel._update_dialog_changelog = RichTextLabel.new()
		panel._update_dialog_changelog.custom_minimum_size = Vector2(420, 160)
		panel._update_dialog_changelog.size_flags_vertical = Control.SIZE_EXPAND_FILL
		panel._update_dialog_changelog.bbcode_enabled = true
		panel._update_dialog_changelog.scroll_following = false
		panel._update_dialog_changelog.selection_enabled = true
		box.add_child(panel._update_dialog_changelog)

		panel._update_dialog_progress = ProgressBar.new()
		panel._update_dialog_progress.visible = false
		panel._update_dialog_progress.min_value = 0
		panel._update_dialog_progress.max_value = 100
		box.add_child(panel._update_dialog_progress)

		panel._update_dialog_status = Label.new()
		panel._update_dialog_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		if T:
			panel._update_dialog_status.add_theme_color_override("font_color", T.color("dim"))
		box.add_child(panel._update_dialog_status)

		var btn_box := HBoxContainer.new()
		btn_box.add_theme_constant_override("separation", 8)
		panel._update_dialog_btn_auto = Button.new()
		panel._update_dialog_btn_auto.text = panel._t("update_btn_auto")
		panel._update_dialog_btn_auto.pressed.connect(panel._on_update_auto_pressed)
		if T:
			T.style_button(panel._update_dialog_btn_auto, "accent", false)
		btn_box.add_child(panel._update_dialog_btn_auto)

		panel._update_dialog_btn_github = Button.new()
		panel._update_dialog_btn_github.text = panel._t("update_btn_github")
		panel._update_dialog_btn_github.pressed.connect(panel._on_update_github_pressed)
		if T:
			T.style_button(panel._update_dialog_btn_github, "neutral", false)
		btn_box.add_child(panel._update_dialog_btn_github)

		panel._update_dialog_btn_restart = Button.new()
		panel._update_dialog_btn_restart.text = panel._t("update_restart_btn")
		panel._update_dialog_btn_restart.visible = false
		panel._update_dialog_btn_restart.pressed.connect(panel._on_update_restart_pressed)
		if T:
			T.style_button(panel._update_dialog_btn_restart, "accent", false)
		btn_box.add_child(panel._update_dialog_btn_restart)

		box.add_child(btn_box)

		panel._update_dialog.add_child(wrap)
		panel.add_child(panel._update_dialog)

	panel._update_dialog.title = panel._t("update_dialog_title")
	var cur_v: String = panel._updater.get_current_version() if panel._updater else "0.7.0"
	var new_v: String = info.get("version", "")
	panel._update_dialog_version_label.text = (panel._t("update_current_version") % cur_v) + "  →  " + (panel._t("update_new_version") % new_v)
	# notes - уже переведённый в BBCode текст. body оставлен запасным
	# вариантом: старый кэш user:// мог быть записан до появления notes.
	panel._update_dialog_changelog.text = String(info.get("notes", info.get("body", "")))
	if panel._update_dialog_progress:
		panel._update_dialog_progress.visible = false
		panel._update_dialog_progress.value = 0
	if panel._update_dialog_status:
		panel._update_dialog_status.text = ""
	if panel._update_dialog_btn_auto:
		panel._update_dialog_btn_auto.visible = true
	if panel._update_dialog_btn_restart:
		panel._update_dialog_btn_restart.visible = false
	panel._update_dialog.popup_centered()

static func _on_updater_available(panel, info: Dictionary) -> void:
	panel._pending_update_info = info
	if panel._update_badge:
		panel._update_badge.text = "⚡ v" + info.get("version", "")
		panel._update_badge.tooltip_text = panel._t("update_badge_text") % info.get("version", "")
		var T = panel._T()
		if T:
			T.style_button(panel._update_badge, "accent", false)
		panel._update_badge.visible = true

static func _on_updater_progress(panel, phase: String, current: int, total: int) -> void:
	if panel._update_dialog_progress:
		panel._update_dialog_progress.visible = true
		panel._update_dialog_progress.max_value = total
		panel._update_dialog_progress.value = current
	if panel._update_dialog_status:
		if phase == "downloading":
			panel._update_dialog_status.text = panel._t("update_status_downloading") % current
		elif phase == "extracting":
			panel._update_dialog_status.text = panel._t("update_status_extracting")

static func _on_updater_completed(panel, _restart_needed: bool) -> void:
	if panel._update_dialog_progress:
		panel._update_dialog_progress.visible = false
	if panel._update_dialog_status:
		panel._update_dialog_status.text = panel._t("update_status_ready_restart")
	if panel._update_dialog_btn_auto:
		panel._update_dialog_btn_auto.visible = false
	if panel._update_dialog_btn_restart:
		panel._update_dialog_btn_restart.visible = true
	if panel._update_badge:
		panel._update_badge.visible = false
	panel._notify(panel._t("update_status_ready_restart"), "success")

static func _on_updater_error(panel, msg: String) -> void:
	if panel._update_dialog_progress:
		panel._update_dialog_progress.visible = false
	if panel._update_dialog_status:
		panel._update_dialog_status.text = panel._t("update_error") % msg
	if panel._update_check_status_label:
		panel._update_check_status_label.text = panel._t("update_error") % msg
	panel._notify(panel._t("update_error") % msg, "error")

static func _on_updater_check_completed(panel, has_update: bool, info: Dictionary) -> void:
	if panel._update_check_status_label:
		if has_update:
			panel._update_check_status_label.text = panel._t("update_badge_text") % info.get("version", "")
		else:
			var cur_v: String = panel._updater.get_current_version() if panel._updater else "0.7.0"
			panel._update_check_status_label.text = panel._t("update_status_latest") % cur_v

static func _on_update_badge_pressed(panel) -> void:
	panel._open_update_dialog(panel._pending_update_info)

static func _on_check_updates_pressed(panel) -> void:
	if panel._update_check_status_label:
		panel._update_check_status_label.text = panel._t("update_status_checking")
	if panel._updater:
		panel._updater.check_for_updates(true)

static func _on_update_auto_pressed(panel) -> void:
	if panel._updater:
		panel._updater.start_update()

static func _on_update_github_pressed(panel) -> void:
	if panel._updater:
		panel._updater.open_github_release()

static func _on_update_restart_pressed(panel) -> void:
	if panel._updater:
		panel._updater.restart_editor()

static func _on_train_mode_toggled(panel, pressed: bool) -> void:
	# v69: кнопка «Обучение модели» заменена галочкой. Галочка стоит — теневой
	# режим: mini-lich учится, а сцены применяет большая модель. Снята — боевой
	# режим: mini-lich чинит сам (каждый результат обязан пройти линтер).
	if panel._minilich_train_warn:
		panel._minilich_train_warn.visible = pressed
	panel._minilich_set_pending = true
	# v70: шлём только training_mode — галочку mini-lich не трогаем (гонка со старым статусом могла выключить обучение)
	panel._request_chats("minilich_set", {"training_mode": pressed})

static func _on_minilich_toggled(panel, pressed: bool) -> void:
	if panel._minilich_status_label:
		panel._minilich_status_label.text = panel._t("minilich_loading")
	# Ставим флаг до ответа сервера — иначе устаревший minilich_status, ожидавший ответа в очереди, сбрасывает галочку обратно.
	panel._minilich_set_pending = true
	# Здесь автозапуск разрешён: пользователь явно меняет настройку.
	panel._request_chats("minilich_set", {"enabled": pressed})

static func _on_github_fetch_pressed(panel) -> void:
	# v81: сбор обучающих пар со сцен GitHub-репозиториев (только Godot 4, format=3).
	var repos := ""
	if panel._minilich_repos_edit:
		repos = panel._minilich_repos_edit.text.strip_edges()
	if repos == "":
		if panel._minilich_github_label:
			panel._minilich_github_label.text = panel._t("github_repos_empty")
		return
	if panel._minilich_github_label:
		panel._minilich_github_label.text = panel._t("github_fetch_started")
	panel._request_chats("minilich_github", {"repos": repos})

static func _on_minilich_payload(panel, kind: String, json: Dictionary) -> void:
	if kind == "minilich_set":
		panel._minilich_set_pending = false
	if json.has("error"):
		if panel._minilich_status_label:
			panel._minilich_status_label.text = str(json.get("error", ""))
		return
	# Статус-запрос мог уйти до ответа на ещё не завершённый minilich_set — не трогаем галочку его устаревшим значением.
	if panel._minilich_check and not (kind == "minilich_status" and panel._minilich_set_pending):
		panel._minilich_check.set_pressed_no_signal(bool(json.get("enabled", false)))
	if panel._minilich_train_check and not (kind == "minilich_status" and panel._minilich_set_pending):
		var _tm := bool(json.get("training_mode", true))
		panel._minilich_train_check.set_pressed_no_signal(_tm)
		if panel._minilich_train_warn:
			panel._minilich_train_warn.visible = _tm
	if panel._minilich_status_label:
		if not bool(json.get("enabled", false)):
			panel._minilich_status_label.text = panel._t("train_console_disabled")
		else:
			panel._minilich_status_label.text = panel._minilich_status_text(json)

static func _minilich_status_text(panel, json: Dictionary) -> String:
	var mb := float(json.get("disk_bytes", 0)) / 1048576.0
	var loss = json.get("last_loss")
	var loss_s := "—"
	if loss != null:
		loss_s = "%.3f" % float(loss)
	var active_s = panel._t("ml_yes") if bool(json.get("training_active", false)) else panel._t("ml_no")
	return panel._t("minilich_status_fmt") % [int(json.get("examples", 0)), int(json.get("train_step", 0)), loss_s, "%.1f" % mb, active_s]

static func _on_safe_rename_pressed(panel) -> void:
	panel.open_safe_rename()

static func open_safe_rename(panel, prefill_path: String = "") -> void:
	panel._ensure_safe_rename_dialog()
	if panel._settings_dialog and panel._settings_dialog.visible:
		panel._settings_dialog.hide()
	if panel._update_dialog and panel._update_dialog.visible:
		panel._update_dialog.hide()
	var initial_path := prefill_path
	if initial_path.is_empty():
		# 1. Приоритет: файл или папка, выделенная в доке FileSystem
		var selected := EditorInterface.get_selected_paths()
		if not selected.is_empty() and (FileAccess.file_exists(selected[0]) or DirAccess.dir_exists_absolute(selected[0])):
			initial_path = selected[0]
		else:
			# 2. Если пользователь редактирует скрипт в видимом редакторе скриптов
			var se := EditorInterface.get_script_editor()
			if se and se.is_visible_in_tree() and se.get_current_script():
				initial_path = se.get_current_script().resource_path
			# 3. Если открыта 2D или 3D сцена (главная сцена в редакторе)
			elif EditorInterface.get_edited_scene_root() and not EditorInterface.get_edited_scene_root().scene_file_path.is_empty():
				initial_path = EditorInterface.get_edited_scene_root().scene_file_path
			# 4. Фоновый открытый скрипт
			elif se and se.get_current_script():
				initial_path = se.get_current_script().resource_path
			else:
				var cur := EditorInterface.get_current_path()
				if not cur.is_empty() and cur != "res://" and (FileAccess.file_exists(cur) or DirAccess.dir_exists_absolute(cur)):
					initial_path = cur
	if initial_path != "" and initial_path.begins_with("res://"):
		panel._safe_rename_old_edit.text = initial_path
		panel._safe_rename_new_edit.text = initial_path
	else:
		panel._safe_rename_old_edit.text = ""
		panel._safe_rename_new_edit.text = ""
	panel._safe_rename_status_label.text = ""
	panel._safe_rename_prepared = {}
	panel._safe_rename_dialog.popup_centered(Vector2(600, 320))

static func _ensure_safe_rename_dialog(panel) -> void:
	if panel._safe_rename_dialog != null:
		return
	var T = panel._T()
	panel._safe_rename_dialog = ConfirmationDialog.new()
	panel._safe_rename_dialog.exclusive = false
	panel._safe_rename_dialog.title = panel._t("safe_rename_title")
	panel._safe_rename_dialog.get_ok_button().text = panel._t("safe_rename_apply")
	panel._safe_rename_dialog.get_cancel_button().text = panel._t("back")
	panel._safe_rename_dialog.add_button(panel._t("safe_rename_preview"), true, "preview")
	panel._safe_rename_dialog.custom_action.connect(func(action: String):
		if action == "preview":
			panel._on_safe_rename_preview()
	)
	panel._safe_rename_dialog.confirmed.connect(panel._on_safe_rename_apply)

	var wrap := PanelContainer.new()
	if T:
		wrap.add_theme_stylebox_override("panel", T.panel_style("agent"))
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	wrap.add_child(box)

	var desc_lbl := Label.new()
	desc_lbl.text = panel._t("safe_rename_desc")
	desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	desc_lbl.custom_minimum_size = Vector2(560, 0)
	if T:
		desc_lbl.add_theme_color_override("font_color", T.color("dim"))
	box.add_child(desc_lbl)
	box.add_child(HSeparator.new())

	# Old path row
	var old_row := HBoxContainer.new()
	var old_lbl := Label.new()
	old_lbl.text = panel._t("safe_rename_old")
	old_lbl.custom_minimum_size = Vector2(130, 0)
	old_row.add_child(old_lbl)
	panel._safe_rename_old_edit = LineEdit.new()
	panel._safe_rename_old_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel._safe_rename_old_edit.placeholder_text = "res://scripts/my_script.gd"
	if T:
		T.style_input(panel._safe_rename_old_edit)
	old_row.add_child(panel._safe_rename_old_edit)
	var browse_btn := Button.new()
	browse_btn.text = panel._t("safe_rename_browse")
	if T:
		T.style_button(browse_btn, "neutral")
	browse_btn.pressed.connect(panel._on_safe_rename_browse)
	old_row.add_child(browse_btn)
	box.add_child(old_row)

	# New path row
	var new_row := HBoxContainer.new()
	var new_lbl := Label.new()
	new_lbl.text = panel._t("safe_rename_new")
	new_lbl.custom_minimum_size = Vector2(130, 0)
	new_row.add_child(new_lbl)
	panel._safe_rename_new_edit = LineEdit.new()
	panel._safe_rename_new_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel._safe_rename_new_edit.placeholder_text = "res://scripts/new_script.gd"
	if T:
		T.style_input(panel._safe_rename_new_edit)
	new_row.add_child(panel._safe_rename_new_edit)
	box.add_child(new_row)

	# Options
	panel._safe_rename_refs_check = CheckBox.new()
	panel._safe_rename_refs_check.text = panel._t("safe_rename_refs")
	panel._safe_rename_refs_check.button_pressed = true
	box.add_child(panel._safe_rename_refs_check)

	# Status label
	panel._safe_rename_status_label = Label.new()
	panel._safe_rename_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	panel._safe_rename_status_label.custom_minimum_size = Vector2(560, 0)
	if T:
		panel._safe_rename_status_label.add_theme_color_override("font_color", T.color("accent"))
	box.add_child(panel._safe_rename_status_label)

	panel._safe_rename_dialog.add_child(wrap)
	panel.add_child(panel._safe_rename_dialog)

static func _on_safe_rename_browse(panel) -> void:
	if panel._safe_rename_file_dialog == null:
		panel._safe_rename_file_dialog = FileDialog.new()
		panel._safe_rename_file_dialog.exclusive = false
		panel._safe_rename_file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		panel._safe_rename_file_dialog.access = FileDialog.ACCESS_RESOURCES
		panel._safe_rename_file_dialog.filters = PackedStringArray([
			"*.gd ; GDScript Files",
			"*.tscn ; Godot Scenes",
			"*.tres ; Godot Resources",
			"* ; All Files"
		])
		panel._safe_rename_file_dialog.file_selected.connect(func(path: String):
			if panel._safe_rename_old_edit:
				panel._safe_rename_old_edit.text = path
			if panel._safe_rename_new_edit and panel._safe_rename_new_edit.text.is_empty():
				panel._safe_rename_new_edit.text = path
		)
		panel.add_child(panel._safe_rename_file_dialog)
	panel._safe_rename_file_dialog.popup_centered_ratio(0.7)

static func _on_safe_rename_preview(panel) -> void:
	if panel._is_network_busy: return
	if panel._safe_rename_old_edit == null or panel._safe_rename_new_edit == null: return
	var old_p = panel._safe_rename_old_edit.text.strip_edges()
	var new_p = panel._safe_rename_new_edit.text.strip_edges()
	if old_p.is_empty() or new_p.is_empty():
		panel._safe_rename_status_label.text = panel._t("safe_rename_no_paths")
		return
	if old_p == new_p:
		panel._safe_rename_status_label.text = "Старый и новый пути совпадают."
		return
	panel._safe_rename_status_label.text = "Анализ ссылок..."
	var body = panel._policy_body({
		"old_path": old_p,
		"new_path": new_p,
		"update_references": panel._safe_rename_refs_check.button_pressed if panel._safe_rename_refs_check else true,
	})
	panel._pending_request_kind = "safe_rename_preview"
	panel._set_ui_busy(true)
	panel.http_request.set_http_proxy("", 0)
	var err = panel.http_request.request(REFACTOR_FILE_PREVIEW_URL, panel._json_headers(), HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._set_ui_busy(false)
		panel._safe_rename_status_label.text = "Ошибка сетевого запроса."

static func _on_safe_rename_apply(panel) -> void:
	if panel._is_network_busy: return
	if panel._safe_rename_old_edit == null or panel._safe_rename_new_edit == null: return
	var old_p = panel._safe_rename_old_edit.text.strip_edges()
	var new_p = panel._safe_rename_new_edit.text.strip_edges()
	if old_p.is_empty() or new_p.is_empty():
		panel._safe_rename_status_label.text = panel._t("safe_rename_no_paths")
		return
	if old_p == new_p:
		panel._safe_rename_status_label.text = "Старый и новый пути совпадают."
		return
	var targets: Array[String] = [old_p, new_p]
	if panel._safe_rename_prepared.has("affected_paths"):
		for p in panel._safe_rename_prepared["affected_paths"]:
			if not targets.has(str(p)):
				targets.append(str(p))
	var check_targets = PackedStringArray(targets) if panel._safe_rename_prepared.has("affected_paths") else PackedStringArray(targets)
	var dirty = panel._dirty_open_scripts(check_targets)
	if not dirty.is_empty():
		panel._safe_rename_status_label.text = "Сначала сохраните изменённые вкладки: " + ", ".join(dirty)
		return
	panel._close_target_scenes_before_write(check_targets)
	panel._safe_rename_status_label.text = "Применение переименования..."
	var body = panel._policy_body({
		"old_path": old_p,
		"new_path": new_p,
		"update_references": panel._safe_rename_refs_check.button_pressed if panel._safe_rename_refs_check else true,
	})
	panel._pending_request_kind = "safe_rename_apply"
	panel._set_ui_busy(true)
	panel.http_request.set_http_proxy("", 0)
	var err = panel.http_request.request(REFACTOR_FILE_APPLY_URL, panel._json_headers(), HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._set_ui_busy(false)
		panel._safe_rename_status_label.text = "Ошибка отправки запроса на переименование."

static func handle_filesystem_move(panel, old_path: String, new_path: String, is_folder: bool = false) -> void:
	if not panel._safe_rename_enabled:
		return
	var clean_old := old_path.strip_edges().replace("\\", "/")
	var clean_new := new_path.strip_edges().replace("\\", "/")
	# v106 (audit 4.3): localize_path корректно разворачивает и относительные,
	# и абсолютные пути ОС (например D:/...) в res://-форму; старый
	# старый ручной префикс порождал некорректный res://D:/...
	if not clean_old.begins_with("res://") and not clean_old.begins_with("user://"):
		clean_old = ProjectSettings.localize_path(clean_old)
	if not clean_new.begins_with("res://") and not clean_new.begins_with("user://"):
		clean_new = ProjectSettings.localize_path(clean_new)
	if clean_old.is_empty() or clean_new.is_empty() or clean_old == clean_new:
		return

	# v106 (audit 1.4): Godot генерирует files_moved на каждый файл пакета
	# drag-and-drop. Шлём запросы строго по очереди, а не шквалом параллельных.
	panel._fs_move_queue.append({"old": clean_old, "new": clean_new, "folder": is_folder})
	panel._process_fs_move_queue()

static func _process_fs_move_queue(panel) -> void:
	if panel._fs_move_busy or panel._fs_move_queue.is_empty():
		return
	panel._fs_move_busy = true
	var item: Dictionary = panel._fs_move_queue.pop_front()
	panel._send_post_move_sync(str(item.get("old", "")), str(item.get("new", "")), bool(item.get("folder", false)))

static func _send_post_move_sync(panel, clean_old: String, clean_new: String, is_folder: bool) -> void:
	print("[Godot Agent] Перемещение/переименование в FileSystem: %s -> %s (папка=%s)" % [clean_old, clean_new, str(is_folder)])
	var body = {
		"old_path": clean_old,
		"new_path": clean_new,
		"is_directory": is_folder,
		"project_root": ProjectSettings.globalize_path("res://"),
		"user_data_dir": OS.get_user_data_dir(),
		"addon_dir": ProjectSettings.globalize_path(panel.get_script().resource_path.get_base_dir()),
	}
	# Запрос уходит через узел связи: панель своих HTTPRequest не создаёт.
	panel._sync_old = clean_old
	panel._sync_new = clean_new
	panel._sync_is_folder = is_folder
	if panel._link == null or not panel._link.post_now("post_move_sync", REFACTOR_FILE_POST_MOVE_SYNC_URL, panel._policy_json(body)):
		push_warning("[Godot Agent] Не удалось отправить post_move_sync: сервер недоступен.")
		panel._fs_move_busy = false
		panel.call_deferred("_process_fs_move_queue")
		return

static func _on_post_move_sync_response(panel, result: int, response_code: int,
		body_bytes: PackedByteArray) -> void:
	var clean_old = panel._sync_old
	var clean_new = panel._sync_new
	var is_folder = panel._sync_is_folder
	# Запрос завершён — можно отправлять следующий из очереди (audit 1.4).
	panel._fs_move_busy = false
	panel.call_deferred("_process_fs_move_queue")
	var json_str := body_bytes.get_string_from_utf8()
	if result != HTTPRequest.RESULT_SUCCESS:
		var down_msg = "[Godot Agent] Внимание: файл '%s' переименован/перемещён, но сервер агента недоступен (не запущен). Ссылки в коде и сценах не обновлены! Запустите godot_agent_server.exe." % clean_old
		push_warning(down_msg)
		# Предупреждение должно быть видно прямо в чате, а не только
		# в консоли редактора — иначе пользователь не узнает о рассинхроне.
		if panel._view:
			panel._view.add_warning(down_msg)
		return
	if response_code != 200:
		var code_msg := "[Godot Agent] Сервер вернул ошибку синхронизации (код %d): %s" % [response_code, json_str]
		push_warning(code_msg)
		if panel._view:
			panel._view.add_warning(code_msg)
		return
	var p := JSON.new()
	if p.parse(json_str) != OK or not (p.data is Dictionary):
		var json_msg := "[Godot Agent] Некорректный JSON-ответ сервера при автосинхронизации: %s" % json_str
		push_warning(json_msg)
		if panel._view:
			panel._view.add_warning(json_msg)
		return
	var resp: Dictionary = p.data
	if not bool(resp.get("ok", false)):
		var err_msg := str(resp.get("error", "Неизвестная ошибка синхронизации"))
		push_warning("[Godot Agent] Ошибка автосинхронизации: " + err_msg)
		if panel._view:
			panel._view.add_warning("[Godot Agent] Ошибка автосинхронизации: " + err_msg)
		return

	panel._sync_resource_uid(clean_old, clean_new)
	var ref_cnt := int(resp.get("reference_count", 0))
	var changed_paths = resp.get("changed_paths", [])
	# ЗАДАЧА 3: сервер вернул точный список изменённых файлов, поэтому полный
	# пересчёт проекта не нужен — обновляем названные файлы.
	panel._refresh_changed_paths([clean_old, clean_new, changed_paths])
	if changed_paths is Array:
		for cp in changed_paths:
			panel._sync_open_script_with_disk(str(cp))
			panel._auto_reload_changed_scene(str(cp))
		# v106 (audit 3.3): файл уже обновлён на диске сервером, но если он
		# открыт с несохранёнными правками — вкладка держит старую версию, и
		# Ctrl+S вернёт битые пути. Честно предупреждаем пользователя.
		var dirty_paths = panel._dirty_open_scripts(PackedStringArray(changed_paths))
		if not dirty_paths.is_empty():
			var dirty_msg = "[Godot Agent] Файлы обновлены на диске, но открыты с несохранёнными правками: %s. Сохранение из редактора (Ctrl+S) вернёт старые пути — закройте вкладку без сохранения или перенесите правки вручную." % ", ".join(dirty_paths)
			push_warning(dirty_msg)
			if panel._view:
				panel._view.add_agent_message("⚠ " + dirty_msg)
		# v106 (audit 3.4): project.godot обновлён на диске, но редактор держит
		# старые значения в памяти — честно предупреждаем, ничего не перезаписывая.
		if changed_paths.has("res://project.godot"):
			push_warning("[Godot Agent] Обновлён project.godot (например автозагрузка или главная сцена). Перезапустите редактор, чтобы F5 использовал новые настройки, — память редактора их не перечитывает.")
	# v106 (audit 3.2): закрываем «зомби»-вкладки старых путей даже если
	# ссылок не нашлось; для папок — все скрипты внутри по префиксу.
	panel._close_ghost_script_tabs_for_move(clean_old, is_folder)
	if FileAccess.file_exists(clean_new) and clean_new.ends_with(".gd"):
		var scr = ResourceLoader.load(clean_new, "", ResourceLoader.CACHE_MODE_REPLACE)
		if scr is Script:
			scr.reload(true)
	var file_cnt := int(resp.get("file_count", 0))
	var entry_id := str(resp.get("entry_id", ""))
	var msg = panel._t("safe_post_move_sync_success") % [clean_old, clean_new, ref_cnt, file_cnt]
	if panel._view:
		panel._view.add_agent_message(msg, entry_id)
	print("[Godot Agent] ", msg)

## Вызывается модулем сигналов, когда ЧЕЛОВЕК переименовал узел в дереве.
## Применяем сразу, как для файлов, но только скрипты: .tscn на диске может
## содержать несохранённые правки редактора, и переписывать его нельзя.
static func handle_scene_node_renamed(panel, scene_path: String, old_path: String,
		old_name: String, new_name: String) -> void:
	if panel._node_rename_suppress > 0:
		return
	var clean_scene := scene_path.strip_edges().replace("\\", "/")
	var clean_old := old_name.strip_edges()
	var clean_new := new_name.strip_edges()
	var clean_path := old_path.strip_edges()
	if clean_scene.is_empty() or clean_old.is_empty() or clean_new.is_empty():
		return
	if not clean_scene.begins_with("res://") or clean_old == clean_new:
		return
	panel._node_rename_queue.append({
		"scene": clean_scene, "old_path": clean_path,
		"old_name": clean_old, "new_name": clean_new,
	})
	panel._process_node_rename_queue()

static func _process_node_rename_queue(panel) -> void:
	if panel._node_rename_busy or panel._node_rename_queue.is_empty():
		return
	panel._node_rename_busy = true
	panel._send_node_rename_sync(panel._node_rename_queue.pop_front())

static func _node_rename_body(panel, item: Dictionary) -> Dictionary:
	# Контракт сервера при scripts_only: node_path — путь узла НА ДИСКЕ
	# (сцену сервер не переписывает и ищет узел в её фактическом тексте),
	# previous_name — как узел называется у редактора. Полный путь, а не лист:
	# при двух узлах с одинаковым именем в разных ветках лист неоднозначен,
	# и сервер отказывается искать узел по нему. disk_path кладёт
	# _send_node_rename_sync; при его отсутствии — прежнее поведение.
	# Контракт закреплён профильными тестами godot_agent/python/tests/
	# test_node_refactor_flow.py (scripts_only: сцена на диске не меняется)
	# и test_node_rename_intercept.py.
	var disk_path := str(item.get("disk_path", ""))
	return panel._policy_body({
		"scene": str(item.get("scene", "")),
		"node_path": disk_path if disk_path != "" else str(item.get("old_path", "")),
		"previous_name": str(item.get("old_name", "")),
		"new_name": str(item.get("new_name", "")),
		"scripts_only": true,
	})

static func _send_node_rename_sync(panel, item: Dictionary) -> void:
	panel._node_sync_ctx = item
	panel._node_rename_suppress += 1
	var scene_path := str(item.get("scene", ""))
	var old_path := str(item.get("old_path", ""))
	var old_name := str(item.get("old_name", ""))
	var new_name := str(item.get("new_name", ""))
	# scripts_only сцену не переписывает: после первого перехвата имя узла
	# в редакторе уже разошлось с диском, и искать узел надо по ДИСКОВОМУ
	# пути (история — _node_disk_names). Пустой результат означает, что
	# панель ничего не знает об узле: прежний предохранитель от устаревшего
	# состояния редактора остаётся как честное предупреждение.
	var disk_path = panel._node_disk_path_for_sync(scene_path, old_path, old_name)
	if disk_path == "":
		var editor_path := old_path if old_path != "" else old_name
		if panel._scene_has_node_path(scene_path, panel._node_path_with_leaf(editor_path, new_name)):
			print("[Godot Agent] Узел '%s' уже переименован на диске в '%s' — синхронизация не требуется." % [editor_path, new_name])
		else:
			push_warning("[Godot Agent] В сцене '%s' нет узла '%s' (и нет '%s') — синхронизация пропущена." % [scene_path, editor_path, new_name])
		panel._finish_node_rename_roundtrip()
		return
	item["disk_path"] = disk_path
	# Лист может быть неоднозначным: два узла с одним именем в разных ветках.
	# Путь мы уже уточнили сами — человек должен это увидеть, а не угадывать,
	# почему обновились «не те» ссылки.
	item["non_unique"] = panel._scene_node_name_count(scene_path, disk_path.get_file()) > 1
	if panel._link == null or not panel._link.post_now("node_rename_sync", REFACTOR_NODE_PREVIEW_URL, panel._policy_json(panel._node_rename_body(item))):
		panel._node_rename_failed("сервер агента недоступен")

## Полный путь узла НА ДИСКЕ для контракта scripts_only: сначала фактическая
## проверка по тексту .tscn, затем история перехватов «редактор → диск».
## Путь, а не лист: при двух узлах с одинаковым именем лист неоднозначен.
## Пустая строка — путь не найден ни на диске, ни в истории.
static func _node_disk_path_for_sync(panel, scene_path: String, old_path: String, old_name: String) -> String:
	var editor_path := old_path if old_path != "" else old_name
	if editor_path == "":
		return ""
	if panel._scene_has_node_path(scene_path, editor_path):
		return editor_path
	var scene_map: Dictionary = panel._node_disk_names.get(scene_path, {})
	var mapped := str(scene_map.get(editor_path, ""))
	if mapped == "":
		# Переименован ВНУК уже переименованного предка: в редакторе путь
		# "ActorPanel/HpLabel", на диске — "PlayerPanel/HpLabel" (scripts_only
		# .tscn не трогает, и точного ключа в истории нет). Ищем в истории
		# САМЫЙ ДЛИННЫЙ предок-префикс и переносим в него остаток пути: при
		# двух подходящих ветках короткий предок дал бы не тот узел.
		var best_editor := ""
		var best_disk := ""
		for key in scene_map.keys():
			var prefix := str(key)
			if not editor_path.begins_with(prefix + "/"):
				continue
			if prefix.length() > best_editor.length():
				best_editor = prefix
				best_disk = str(scene_map[key])
		if best_editor == "":
			return ""
		var via_ancestor: String = best_disk.rstrip("/") + editor_path.substr(best_editor.length())
		return via_ancestor if panel._scene_has_node_path(scene_path, via_ancestor) else ""
	if panel._scene_has_node_path(scene_path, mapped):
		return mapped
	# Человек сохранил сцену: диск догнал редактор — запись устарела.
	scene_map.erase(editor_path)
	return ""

## Запомнить пару «путь в редакторе → путь на диске» после успешного
## применения: scripts_only не трогает .tscn, поэтому путь на диске прежний.
static func _note_node_disk_name(panel, scene_path: String, editor_path: String, disk_path: String) -> void:
	if scene_path == "" or editor_path == "" or disk_path == "":
		return
	var scene_map: Dictionary = panel._node_disk_names.get(scene_path, {})
	scene_map[editor_path] = disk_path
	panel._node_disk_names[scene_path] = scene_map

## Полные пути узлов файла сцены — так же, как их считает сервер: у корня
## ".", у прямого ребёнка корня — имя, глубже — путь родителя плюс имя.
static func _scene_node_paths(panel, scene_path: String) -> PackedStringArray:
	var paths := PackedStringArray()
	if scene_path.is_empty() or not FileAccess.file_exists(scene_path):
		return paths
	var f := FileAccess.open(scene_path, FileAccess.READ)
	if f == null:
		return paths
	var text := f.get_as_text()
	f.close()
	# name/parent — атрибуты СЕКЦИИ узла ([node name="X" ...]), а не любая
	# подстрока в файле: ключи вида metadata/display_name="X" давали ложное
	# «узел есть на диске», и обновление ссылок молча пропускалось.
	var idx := text.find("[node ")
	while idx >= 0:
		var stop := text.find("]", idx)
		if stop < 0:
			break
		var header := text.substr(idx, stop - idx + 1)
		var node_name = panel._tscn_attr(header, "name")
		if node_name != "":
			if not header.contains("parent="):
				paths.append(".")
			else:
				var parent = panel._tscn_attr(header, "parent")
				paths.append(node_name if parent == "." else parent.rstrip("/") + "/" + node_name)
		idx = text.find("[node ", stop)
	return paths

## Значение атрибута в заголовке секции .tscn. Пустая строка — атрибута нет.
static func _tscn_attr(panel, header: String, key: String) -> String:
	var needle := key + "=\""
	var start := header.find(needle)
	if start < 0:
		return ""
	start += needle.length()
	var stop := header.find("\"", start)
	return header.substr(start, stop - start) if stop >= 0 else ""

## Есть ли в файле сцены узел ровно по этому полному пути. Консервативно:
## отсутствие файла или ошибка чтения — false, и решение остаётся за сервером.
static func _scene_has_node_path(panel, scene_path: String, node_path: String) -> bool:
	var clean := node_path.strip_edges().replace("\\", "/")
	if clean == "":
		clean = "."
	return panel._scene_node_paths(scene_path).has(clean)

## Сколько узлов файла сцены называются так же. Больше одного — путь по
## листу неоднозначен, и это стоит показать человеку, а не угадывать.
static func _scene_node_name_count(panel, scene_path: String, node_name: String) -> int:
	if node_name.is_empty():
		return 0
	var count := 0
	for path in panel._scene_node_paths(scene_path):
		if path == node_name or path.get_file() == node_name:
			count += 1
	return count

## Полный путь с заменённым листом: "Panel/Stats" + "Row" -> "Panel/Row".
static func _node_path_with_leaf(panel, node_path: String, leaf: String) -> String:
	var slash := node_path.rfind("/")
	return (node_path.substr(0, slash + 1) + leaf) if slash >= 0 else leaf

static func _node_rename_failed(panel, reason: String) -> void:
	var item: Dictionary = panel._node_sync_ctx
	var msg = panel._t("node_rename_intercept_failed") % [
		str(item.get("old_name", "?")), str(item.get("new_name", "?")), reason]
	push_warning("[Godot Agent] " + msg)
	if panel._view:
		panel._view.add_warning(msg)
	panel._finish_node_rename_roundtrip()

static func _finish_node_rename_roundtrip(panel) -> void:
	panel._node_rename_busy = false
	panel._node_rename_suppress = maxi(0, panel._node_rename_suppress - 1)
	panel.call_deferred("_process_node_rename_queue")

static func _short_channel_error_text(panel, response_code: int, body: PackedByteArray) -> String:
	# Тело ответа несёт пояснение сервера («Узел 'X' не найден в сцене»).
	# Раньше оно терялось и пользователь видел только «HTTP 400» — по такому
	# сообщению невозможно понять, что случилось и что делать.
	var text := "HTTP " + str(response_code)
	var json = JSON.parse_string(body.get_string_from_utf8())
	if typeof(json) == TYPE_DICTIONARY:
		var detail := str(json.get("error", json.get("message", ""))).strip_edges()
		if detail != "":
			text += ": " + detail
	return text

static func _on_node_rename_sync_response(panel, result: int, response_code: int,
		body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS:
		panel._node_rename_failed("сервер агента недоступен")
		return
	if response_code != 200:
		panel._node_rename_failed(panel._short_channel_error_text(response_code, body))
		return
	var json = JSON.parse_string(body.get_string_from_utf8())
	if typeof(json) != TYPE_DICTIONARY or not bool(json.get("ok", false)):
		var err := "некорректный ответ сервера"
		if typeof(json) == TYPE_DICTIONARY:
			err = str(json.get("error", err))
		panel._node_rename_failed(err)
		return
	var prep: Dictionary = json.get("prepared", {})
	if int(prep.get("file_count", 0)) == 0:
		# Ссылок на узел в скриптах нет — обновлять нечего, но «нет ссылок»
		# при НЕ уникальном имени узла похоже на путаницу с одноимённым
		# узлом: здесь молчать нельзя.
		if bool(panel._node_sync_ctx.get("non_unique", false)):
			var ambiguous_msg = "[Godot Agent] В сцене '%s' несколько узлов с именем '%s' — ссылки не обновлены. Убедитесь, что переименован именно '%s'." % [str(panel._node_sync_ctx.get("scene", "")), str(panel._node_sync_ctx.get("new_name", "")), str(panel._node_sync_ctx.get("disk_path", ""))]
			push_warning(ambiguous_msg)
			if panel._view:
				panel._view.add_warning(ambiguous_msg)
		panel._finish_node_rename_roundtrip()
		return
	# Фаза 2: применение того же запроса. Двухфазность общая с панелью
	# безопасного переименования — отдельного пути применения нет.
	if panel._link == null or not panel._link.post_now("node_rename_apply", REFACTOR_NODE_APPLY_URL, panel._policy_json(panel._node_rename_body(panel._node_sync_ctx))):
		panel._node_rename_failed("сервер агента недоступен")

static func _on_node_rename_apply_response(panel, result: int, response_code: int,
		body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS:
		panel._node_rename_failed("сервер агента недоступен")
		return
	if response_code != 200:
		panel._node_rename_failed(panel._short_channel_error_text(response_code, body))
		return
	var json = JSON.parse_string(body.get_string_from_utf8())
	if typeof(json) != TYPE_DICTIONARY or not bool(json.get("ok", false)):
		var err := "некорректный ответ сервера"
		if typeof(json) == TYPE_DICTIONARY:
			err = str(json.get("error", err))
		panel._node_rename_failed(err)
		return
	var item: Dictionary = panel._node_sync_ctx
	var ref_cnt := int(json.get("reference_count", 0))
	var file_cnt := int(json.get("file_count", 0))
	var changed_paths = json.get("changed_paths", [])
	# Обновляем только скрипты. Сцену НЕ трогаем: при перехвате в ней
	# несохранённые правки редактора, перезагрузка их потеряет.
	if changed_paths is Array:
		panel._refresh_changed_paths([changed_paths])
		for cp in changed_paths:
			panel._sync_open_script_with_disk(str(cp))
	var msg = panel._t("node_rename_intercept_success") % [
		str(item.get("old_name", "")), str(item.get("new_name", "")),
		ref_cnt, file_cnt]
	if panel._view:
		panel._view.add_agent_message(msg, str(json.get("entry_id", "")))
	print("[Godot Agent] ", msg)
	# scripts_only: .tscn на диске не менялся, поэтому редакторский путь
	# продолжает соответствовать тому же дисковому пути (сменён только лист).
	var editor_before := str(item.get("old_path", ""))
	if editor_before == "":
		editor_before = str(item.get("old_name", ""))
	panel._note_node_disk_name(str(item.get("scene", "")),
		panel._node_path_with_leaf(editor_before, str(item.get("new_name", ""))),
		str(item.get("disk_path", "")))
	panel._finish_node_rename_roundtrip()

static func _on_safe_node_rename_pressed(panel) -> void:
	panel.open_safe_node_rename()

static func open_safe_node_rename(panel, prefill_scene: String = "", prefill_node: String = "") -> void:
	panel._ensure_safe_node_rename_dialog()
	if panel._settings_dialog and panel._settings_dialog.visible:
		panel._settings_dialog.hide()
	if panel._update_dialog and panel._update_dialog.visible:
		panel._update_dialog.hide()
	var initial_scene := prefill_scene
	var initial_node := prefill_node
	var initial_new_name := prefill_node
	var edited_root = EditorInterface.get_edited_scene_root()
	if initial_scene.is_empty():
		if edited_root and not edited_root.scene_file_path.is_empty():
			initial_scene = edited_root.scene_file_path
	if initial_node.is_empty():
		var selection := EditorInterface.get_selection()
		if selection:
			var selected_nodes := selection.get_selected_nodes()
			if not selected_nodes.is_empty() and is_instance_valid(selected_nodes[0]):
				var node := selected_nodes[0] as Node
				if edited_root and (node == edited_root or edited_root.is_ancestor_of(node)):
					if node == edited_root:
						initial_node = "."
					else:
						initial_node = str(edited_root.get_path_to(node))
					initial_new_name = str(node.name)
	if panel._safe_node_rename_scene_edit:
		panel._safe_node_rename_scene_edit.text = initial_scene
	if panel._safe_node_rename_node_edit:
		panel._safe_node_rename_node_edit.text = initial_node
	if panel._safe_node_rename_new_edit:
		panel._safe_node_rename_new_edit.text = initial_new_name
	if panel._safe_node_rename_status_label:
		panel._safe_node_rename_status_label.text = ""
	panel._safe_node_rename_prepared = {}
	panel._safe_node_rename_dialog.popup_centered(Vector2(600, 360))
