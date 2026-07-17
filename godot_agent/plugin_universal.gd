@tool
extends EditorPlugin

# ============================================================================
# УНИВЕРСАЛЬНЫЙ ЗАПУСК АДДОНА — без жёстких путей.
#
# Как применить: замените СОДЕРЖИМОЕ вашего файла плагина (того, на
# который указывает plugin.cfg, например gemini_agent.gd) содержимым
# этого файла. После этого:
#   - agent_panel.gd ищется АВТОМАТИЧЕСКИ внутри папки аддона, как бы
#     пользователь ни назвал/ни вложил папки при распаковке;
#   - agent_panel.tscn больше НЕ ИСПОЛЬЗУЕТСЯ — панель собирается кодом.
#     Удалять сцену НЕ ОБЯЗАТЕЛЬНО — она просто лежит без дела
#     и ничему не мешает.
#
# Единственное требование самого Godot: папка аддона должна лежать
# где-то внутри res://addons/, а рядом с этим скриптом — plugin.cfg.
# ============================================================================

var _dock: Control = null


func _enter_tree() -> void:
	var self_script: Script = get_script() as Script
	var base: String = self_script.resource_path.get_base_dir()
	var panel_script_path: String = _find_file(base, "agent_panel.gd")
	if panel_script_path == "":
		push_error("[Godot Agent] agent_panel.gd не найден внутри " + base)
		return
	_dock = _build_panel(panel_script_path)
	_dock.name = "ИИ Агент"
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)


func _exit_tree() -> void:
	if _dock:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null


func _find_file(dir_path: String, file_name: String) -> String:
	# Рекурсивный поиск файла внутри папки аддона (любая вложенность).
	var dir: DirAccess = DirAccess.open(dir_path)
	if dir == null:
		return ""
	var subdirs: Array[String] = []
	dir.list_dir_begin()
	var entry: String = dir.get_next()
	while entry != "":
		if dir.current_is_dir():
			if not entry.begins_with("."):
				subdirs.append(dir_path + "/" + entry)
		elif entry == file_name:
			dir.list_dir_end()
			return dir_path + "/" + entry
		entry = dir.get_next()
	dir.list_dir_end()
	for sd in subdirs:
		var found: String = _find_file(sd, file_name)
		if found != "":
			return found
	return ""


func _build_panel(panel_script_path: String) -> Control:
	# Собираем ту же сцену, что была в agent_panel.tscn, но кодом —
	# без привязки к абсолютным путям res://addons/…
	var panel := Control.new()

	var req := HTTPRequest.new()
	req.name = "HTTPRequest"
	panel.add_child(req)

	var vbox := VBoxContainer.new()
	vbox.name = "VBoxContainer"
	vbox.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.add_child(vbox)

	var chat_log := RichTextLabel.new()
	chat_log.name = "ChatLog"
	chat_log.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	chat_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	chat_log.focus_mode = Control.FOCUS_CLICK
	chat_log.bbcode_enabled = true
	chat_log.scroll_following = true
	chat_log.context_menu_enabled = true
	chat_log.selection_enabled = true
	chat_log.text = "[color=green]Система готова. Работаем через локальный Браузерный ИИ-Агент![/color]\n"
	vbox.add_child(chat_log)

	var pbox := HBoxContainer.new()
	pbox.name = "PendingActionBox"
	pbox.visible = false
	vbox.add_child(pbox)
	var action_label := Label.new()
	action_label.name = "ActionLabel"
	action_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	action_label.text = "Агент хочет выполнить действие..."
	action_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	pbox.add_child(action_label)
	var confirm_btn := Button.new()
	confirm_btn.name = "ConfirmButton"
	confirm_btn.text = "Разрешить"
	pbox.add_child(confirm_btn)
	var reject_btn := Button.new()
	reject_btn.name = "RejectButton"
	reject_btn.text = "Отклонить"
	pbox.add_child(reject_btn)

	var hbox := HBoxContainer.new()
	hbox.name = "HBoxContainer"
	vbox.add_child(hbox)
	var input_field := TextEdit.new()
	input_field.name = "InputField"
	input_field.custom_minimum_size = Vector2(0, 60)
	input_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	input_field.placeholder_text = "Спросите или дайте указание (Ctrl+Enter для отправки)..."
	input_field.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	hbox.add_child(input_field)
	var send_btn := Button.new()
	send_btn.name = "SendButton"
	send_btn.text = "Отправить"
	hbox.add_child(send_btn)

	var adv_toggle := Button.new()
	adv_toggle.name = "AdvancedToggleBtn"
	adv_toggle.text = "Дополнительно"
	vbox.add_child(adv_toggle)

	var adv_box := VBoxContainer.new()
	adv_box.name = "AdvancedBox"
	adv_box.visible = false
	vbox.add_child(adv_box)
	var reinit_btn := Button.new()
	reinit_btn.name = "ReinitButton"
	reinit_btn.text = "Переинициализировать (переслать структуру проекта)"
	adv_box.add_child(reinit_btn)
	var rollback_btn := Button.new()
	rollback_btn.name = "RollbackButton"
	rollback_btn.text = "Откатить последнее изменение"
	adv_box.add_child(rollback_btn)

	# Скрипт панели подключаем ПОСЛЕ создания детей: когда панель попадёт
	# в док, сработает _ready() и все @onready-ссылки найдут свои узлы.
	panel.set_script(load(panel_script_path))
	return panel
