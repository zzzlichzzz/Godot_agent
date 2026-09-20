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
#   - Вкладка агента автоматически становится ПЕРВОЙ в правом доке
#     и сразу открывается — пользователю не нужно её искать.
#   - Подписи локализуются через agent_locale.gd (RU/EN).
#
# Единственное требование самого Godot: папка аддона должна лежать
# где-то внутри res://addons/, а рядом с этим скриптом — plugin.cfg.
# ============================================================================

var _dock: Control = null
var _loc = null
var _promote_focus_done: bool = false
var _runtime_debugger = null


func _enter_tree() -> void:
	var self_script: Script = get_script() as Script
	var base: String = self_script.resource_path.get_base_dir()
	var panel_script_path: String = _find_file(base, "agent_panel.gd")
	if panel_script_path == "":
		push_error("[Godot Agent] agent_panel.gd не найден внутри " + base)
		return
	var locale_path: String = _find_file(base, "agent_locale.gd")
	if locale_path != "":
		_loc = load(locale_path)
	var debugger_path: String = _find_file(base, "agent_runtime_debugger.gd")
	if debugger_path != "":
		var debugger_script = load(debugger_path)
		if debugger_script:
			_runtime_debugger = debugger_script.new()
			add_debugger_plugin(_runtime_debugger)
	_dock = _build_panel(panel_script_path)
	_dock.name = _lt("dock_title", "ИИ Агент")
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)
	add_tool_menu_item(_lt("safe_rename_title", "Безопасное переименование файла..."), _on_safe_rename_menu_pressed)
	add_tool_menu_item(_lt("safe_node_rename_title", "Безопасное переименование узла..."), _on_safe_node_rename_menu_pressed)
	_ensure_fs_dock_connected()
	# Делаем вкладку агента первой и активной (отложенно: док должен
	# успеть попасть в TabContainer редактора).
	call_deferred("_promote_dock_tab")


func _ensure_fs_dock_connected() -> void:
	var fs_dock: FileSystemDock = EditorInterface.get_file_system_dock()
	if fs_dock:
		var connected_any := false
		if not fs_dock.files_moved.is_connected(_on_fs_files_moved):
			fs_dock.files_moved.connect(_on_fs_files_moved)
			connected_any = true
		if not fs_dock.folder_moved.is_connected(_on_fs_folder_moved):
			fs_dock.folder_moved.connect(_on_fs_folder_moved)
			connected_any = true
		if connected_any:
			print("[Godot Agent] Перехват событий FileSystemDock подключен (автосинхронизация ссылок активна при запущенном сервере).")


func _exit_tree() -> void:
	var fs_dock: FileSystemDock = EditorInterface.get_file_system_dock()
	if fs_dock:
		if fs_dock.files_moved.is_connected(_on_fs_files_moved):
			fs_dock.files_moved.disconnect(_on_fs_files_moved)
		if fs_dock.folder_moved.is_connected(_on_fs_folder_moved):
			fs_dock.folder_moved.disconnect(_on_fs_folder_moved)
	remove_tool_menu_item(_lt("safe_rename_title", "Безопасное переименование файла..."))
	remove_tool_menu_item(_lt("safe_node_rename_title", "Безопасное переименование узла..."))
	if _runtime_debugger:
		_runtime_debugger.cancel_pending("session_stopped")
		remove_debugger_plugin(_runtime_debugger)
		_runtime_debugger = null
	if _dock:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null


func _on_fs_files_moved(old_file: String, new_file: String) -> void:
	print("[Godot Agent] Событие FileSystem (перемещение файла): '%s' -> '%s'" % [old_file, new_file])
	if _dock and _dock.has_method("handle_filesystem_move"):
		_dock.call("handle_filesystem_move", old_file, new_file, false)
	else:
		push_warning("[Godot Agent] Панель агента не готова для обработки перемещения файла.")


func _on_fs_folder_moved(old_folder: String, new_folder: String) -> void:
	print("[Godot Agent] Событие FileSystem (перемещение папки): '%s' -> '%s'" % [old_folder, new_folder])
	if _dock and _dock.has_method("handle_filesystem_move"):
		_dock.call("handle_filesystem_move", old_folder, new_folder, true)
	else:
		push_warning("[Godot Agent] Панель агента не готова для обработки перемещения папки.")


func _on_safe_rename_menu_pressed() -> void:
	if _dock and _dock.has_method("open_safe_rename"):
		_dock.call("open_safe_rename")


func _on_safe_node_rename_menu_pressed() -> void:
	if _dock and _dock.has_method("open_safe_node_rename"):
		_dock.call("open_safe_node_rename")


func _lt(key: String, fallback: String) -> String:
	# Перевод с запасным русским текстом, если файл локализации не найден.
	if _loc:
		return _loc.t(key)
	return fallback


func _promote_dock_tab() -> void:
	# Редактор восстанавливает сохранённую раскладку доков УЖЕ ПОСЛЕ
	# включения плагинов и может вернуть вкладку на старое место.
	# Поэтому в течение ~4 секунд несколько раз передвигаем её на первое
	# место (позиция закрепится в раскладке после первого сохранения),
	# а также гарантируем подключение сигналов FileSystemDock.
	for i in range(8):
		_ensure_fs_dock_connected()
		_do_promote_once()
		if get_tree() == null:
			return
		await get_tree().create_timer(0.5).timeout
		if _dock == null:
			return
	_ensure_fs_dock_connected()
	_do_promote_once()


func _do_promote_once() -> void:
	if _dock == null or not is_instance_valid(_dock):
		return
	var tabs := _dock.get_parent() as TabContainer
	if tabs == null:
		return
	if tabs.get_child(0) != _dock:
		tabs.move_child(_dock, 0)
	var idx: int = tabs.get_tab_idx_from_control(_dock)
	if idx >= 0 and not _promote_focus_done:
		_promote_focus_done = true
		tabs.current_tab = idx


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
	chat_log.text = "[color=green]" + _lt("system_ready", "Система готова. Работаем через локальный Godot Agent!") + "[/color]\n"
	vbox.add_child(chat_log)

	var pbox := HBoxContainer.new()
	pbox.name = "PendingActionBox"
	pbox.visible = false
	vbox.add_child(pbox)
	var action_label := Label.new()
	action_label.name = "ActionLabel"
	action_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	action_label.text = _lt("pending_default", "Агент хочет выполнить действие...")
	action_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	pbox.add_child(action_label)
	var confirm_btn := Button.new()
	confirm_btn.name = "ConfirmButton"
	confirm_btn.text = _lt("allow", "Разрешить")
	pbox.add_child(confirm_btn)
	var reject_btn := Button.new()
	reject_btn.name = "RejectButton"
	reject_btn.text = _lt("reject", "Отклонить")
	pbox.add_child(reject_btn)

	var hbox := HBoxContainer.new()
	hbox.name = "HBoxContainer"
	vbox.add_child(hbox)
	var input_field := TextEdit.new()
	input_field.name = "InputField"
	input_field.custom_minimum_size = Vector2(0, 60)
	input_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	input_field.placeholder_text = _lt("input_placeholder", "Спросите или дайте указание (Ctrl+Enter для отправки)...")
	input_field.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	hbox.add_child(input_field)
	var send_btn := Button.new()
	send_btn.name = "SendButton"
	send_btn.text = _lt("send", "Отправить")
	hbox.add_child(send_btn)

	# Кнопка ВЫБОРА НЕЙРОСЕТИ для открытого чата. На этом месте раньше стояло
	# «⚙️ Дополнительно» — ящик с инструментами, которые нужны раз в месяц
	# (переинициализация, справочник API, ошибки запуска, живой ввод). Ящик
	# переехал в окно настроек (кнопка ⚙ в строке чатов), а строка прямо под
	# полем ввода отдана тому, что важно знать при КАЖДОМ сообщении: какая
	# модель и у какого провайдера сейчас отвечает. Нажатие открывает то же
	# окно выбора провайдера, что и настройки работы по ключу, и выбранная
	# модель применяется к ЭТОМУ чату — переписка сохраняется.
	var model_btn := Button.new()
	model_btn.name = "ChatModelBtn"
	model_btn.text = _lt("chat_model_pick", "🤖 Выбрать нейросеть")
	# Название модели бывает длинным (deepseek/deepseek-chat-v3-0324:free), а
	# панель живёт в доке 250–400 px: без обрезки кнопка растянула бы
	# наименьшую ширину всей панели по длине подписи.
	model_btn.clip_text = true
	vbox.add_child(model_btn)

	# Ящик редких инструментов. Остаётся в дереве и скрытым: панель наполняет его
	# в _ready (ошибки запуска, справочник API, живой ввод), а при первом
	# открытии настроек ПЕРЕНОСИТ узел целиком в окно настроек — см.
	# _on_settings_pressed в agent_panel.gd.
	var adv_box := VBoxContainer.new()
	adv_box.name = "AdvancedBox"
	adv_box.visible = false
	vbox.add_child(adv_box)
	var reinit_btn := Button.new()
	reinit_btn.name = "ReinitButton"
	reinit_btn.text = _lt("reinit", "Переинициализировать (переслать структуру проекта)")
	adv_box.add_child(reinit_btn)

	# Скрипт панели подключаем ПОСЛЕ создания детей: когда панель попадёт
	# в док, сработает _ready() и все @onready-ссылки найдут свои узлы.
	panel.set_script(load(panel_script_path))
	if panel.has_method("set_editor_plugin"):
		panel.call("set_editor_plugin", self)
	if _runtime_debugger and panel.has_method("set_runtime_debugger"):
		panel.call("set_runtime_debugger", _runtime_debugger)
	return panel
