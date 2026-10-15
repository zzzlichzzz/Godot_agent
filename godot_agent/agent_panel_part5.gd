@tool
extends RefCounted

# Модуль agent_panel_part5: методы вынесены «пилой» split_gd из agent_panel.gd.
# Реализация живёт ЗДЕСЬ; в доноре на месте метода — тонкая обёртка,
# поэтому connect()/call() по исходным именам продолжают работать.
# Тело работает через параметр panel: к членам донора — panel.<член>,
# к другим методам донора — panel.<метод> (через его обёртку).

# --- константы, скопированные из донора (неизменяемы) ---
const REFACTOR_NODE_PREVIEW_URL = AgentServer.URL_SCENE_REFACTOR_NODE_PREVIEW
const REFACTOR_NODE_APPLY_URL = AgentServer.URL_SCENE_REFACTOR_NODE_APPLY

static func _ensure_safe_node_rename_dialog(panel) -> void:
	if panel._safe_node_rename_dialog != null:
		return
	var T = panel._T()
	panel._safe_node_rename_dialog = ConfirmationDialog.new()
	panel._safe_node_rename_dialog.exclusive = false
	panel._safe_node_rename_dialog.title = panel._t("safe_node_rename_title")
	panel._safe_node_rename_dialog.get_ok_button().text = panel._t("safe_node_rename_apply")
	panel._safe_node_rename_dialog.get_cancel_button().text = panel._t("back")
	panel._safe_node_rename_dialog.add_button(panel._t("safe_node_rename_preview"), true, "preview")
	panel._safe_node_rename_dialog.custom_action.connect(func(action: String):
		if action == "preview":
			panel._on_safe_node_rename_preview()
	)
	panel._safe_node_rename_dialog.confirmed.connect(panel._on_safe_node_rename_apply)

	var wrap := MarginContainer.new()
	wrap.add_theme_constant_override("margin_left", 12)
	wrap.add_theme_constant_override("margin_top", 12)
	wrap.add_theme_constant_override("margin_right", 12)
	wrap.add_theme_constant_override("margin_bottom", 12)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	wrap.add_child(box)

	var desc_lbl := Label.new()
	desc_lbl.text = panel._t("safe_node_rename_desc")
	desc_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	desc_lbl.custom_minimum_size = Vector2(560, 0)
	if T:
		desc_lbl.add_theme_color_override("font_color", T.color("muted"))
	box.add_child(desc_lbl)

	# Scene path row
	var scene_row := HBoxContainer.new()
	var scene_lbl := Label.new()
	scene_lbl.text = panel._t("safe_node_rename_scene")
	scene_lbl.custom_minimum_size = Vector2(140, 0)
	scene_row.add_child(scene_lbl)
	panel._safe_node_rename_scene_edit = LineEdit.new()
	panel._safe_node_rename_scene_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel._safe_node_rename_scene_edit.placeholder_text = "res://scenes/player.tscn"
	if T:
		T.style_input(panel._safe_node_rename_scene_edit)
	scene_row.add_child(panel._safe_node_rename_scene_edit)
	var browse_btn := Button.new()
	browse_btn.text = panel._t("safe_node_rename_browse")
	if T:
		T.style_button(browse_btn, "neutral")
	browse_btn.pressed.connect(panel._on_safe_node_rename_scene_browse)
	scene_row.add_child(browse_btn)
	box.add_child(scene_row)

	# Target node row
	var node_row := HBoxContainer.new()
	var node_lbl := Label.new()
	node_lbl.text = panel._t("safe_node_rename_node")
	node_lbl.custom_minimum_size = Vector2(140, 0)
	node_row.add_child(node_lbl)
	panel._safe_node_rename_node_edit = LineEdit.new()
	panel._safe_node_rename_node_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel._safe_node_rename_node_edit.placeholder_text = "Gun"
	if T:
		T.style_input(panel._safe_node_rename_node_edit)
	node_row.add_child(panel._safe_node_rename_node_edit)
	box.add_child(node_row)

	# New name row
	var new_row := HBoxContainer.new()
	var new_lbl := Label.new()
	new_lbl.text = panel._t("safe_node_rename_new")
	new_lbl.custom_minimum_size = Vector2(140, 0)
	new_row.add_child(new_lbl)
	panel._safe_node_rename_new_edit = LineEdit.new()
	panel._safe_node_rename_new_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel._safe_node_rename_new_edit.placeholder_text = "Weapon"
	if T:
		T.style_input(panel._safe_node_rename_new_edit)
	new_row.add_child(panel._safe_node_rename_new_edit)
	box.add_child(new_row)

	# Status label
	panel._safe_node_rename_status_label = Label.new()
	panel._safe_node_rename_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	panel._safe_node_rename_status_label.custom_minimum_size = Vector2(560, 0)
	if T:
		panel._safe_node_rename_status_label.add_theme_color_override("font_color", T.color("accent"))
	box.add_child(panel._safe_node_rename_status_label)

	panel._safe_node_rename_dialog.add_child(wrap)
	panel.add_child(panel._safe_node_rename_dialog)

static func _on_safe_node_rename_scene_browse(panel) -> void:
	if panel._safe_node_rename_scene_dialog == null:
		panel._safe_node_rename_scene_dialog = FileDialog.new()
		panel._safe_node_rename_scene_dialog.exclusive = false
		panel._safe_node_rename_scene_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		panel._safe_node_rename_scene_dialog.access = FileDialog.ACCESS_RESOURCES
		panel._safe_node_rename_scene_dialog.filters = PackedStringArray([
			"*.tscn ; Godot Scenes",
			"* ; All Files"
		])
		panel._safe_node_rename_scene_dialog.file_selected.connect(func(path: String):
			if panel._safe_node_rename_scene_edit:
				panel._safe_node_rename_scene_edit.text = path
		)
		panel.add_child(panel._safe_node_rename_scene_dialog)
	panel._safe_node_rename_scene_dialog.popup_centered_ratio(0.7)

static func _on_safe_node_rename_preview(panel) -> void:
	if panel._is_network_busy: return
	if panel._safe_node_rename_scene_edit == null or panel._safe_node_rename_node_edit == null or panel._safe_node_rename_new_edit == null: return
	var scene_p = panel._safe_node_rename_scene_edit.text.strip_edges()
	var node_p = panel._safe_node_rename_node_edit.text.strip_edges()
	var new_n = panel._safe_node_rename_new_edit.text.strip_edges()
	if scene_p.is_empty() or node_p.is_empty() or new_n.is_empty():
		panel._safe_node_rename_status_label.text = panel._t("safe_node_rename_no_paths")
		return
	if node_p == new_n:
		panel._safe_node_rename_status_label.text = "Старое и новое имя совпадают."
		return
	panel._safe_node_rename_status_label.text = "Анализ ссылок узла..."
	var body = panel._policy_body({
		"scene": scene_p,
		"node_path": node_p,
		"new_name": new_n,
	})
	panel._pending_request_kind = "safe_node_rename_preview"
	panel._set_ui_busy(true)
	panel.http_request.set_http_proxy("", 0)
	var err = panel.http_request.request(REFACTOR_NODE_PREVIEW_URL, panel._json_headers(), HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._set_ui_busy(false)
		panel._safe_node_rename_status_label.text = "Ошибка сетевого запроса."

static func _on_safe_node_rename_apply(panel) -> void:
	if panel._is_network_busy: return
	if panel._safe_node_rename_scene_edit == null or panel._safe_node_rename_node_edit == null or panel._safe_node_rename_new_edit == null: return
	var scene_p = panel._safe_node_rename_scene_edit.text.strip_edges()
	var node_p = panel._safe_node_rename_node_edit.text.strip_edges()
	var new_n = panel._safe_node_rename_new_edit.text.strip_edges()
	if scene_p.is_empty() or node_p.is_empty() or new_n.is_empty():
		panel._safe_node_rename_status_label.text = panel._t("safe_node_rename_no_paths")
		return
	if node_p == new_n:
		panel._safe_node_rename_status_label.text = "Старое и новое имя совпадают."
		return
	var targets: Array[String] = [scene_p]
	if panel._safe_node_rename_prepared.has("affected_paths"):
		for p in panel._safe_node_rename_prepared["affected_paths"]:
			if not targets.has(str(p)):
				targets.append(str(p))
	var check_targets = PackedStringArray(targets) if panel._safe_node_rename_prepared.has("affected_paths") else PackedStringArray()
	var dirty = panel._dirty_open_scripts(check_targets)
	if not dirty.is_empty():
		panel._safe_node_rename_status_label.text = "Сначала сохраните изменённые вкладки: " + ", ".join(dirty)
		return
	panel._safe_node_rename_status_label.text = "Применение переименования узла..."
	var body = panel._policy_body({
		"scene": scene_p,
		"node_path": node_p,
		"new_name": new_n,
	})
	# ЗАДАЧА 3: пока плагин сам переименовывает, перехват подавлен.
	panel._node_rename_suppress += 1
	panel._pending_request_kind = "safe_node_rename_apply"
	panel._set_ui_busy(true)
	panel.http_request.set_http_proxy("", 0)
	var err = panel.http_request.request(REFACTOR_NODE_APPLY_URL, panel._json_headers(), HTTPClient.METHOD_POST, panel._policy_json(body))
	if err != OK:
		panel._set_ui_busy(false)
		panel._node_rename_suppress = maxi(0, panel._node_rename_suppress - 1)
		panel._safe_node_rename_status_label.text = "Ошибка отправки запроса на переименование узла."
