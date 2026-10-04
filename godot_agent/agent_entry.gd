@tool
extends EditorPlugin

# ============================================================================
# AGENT ENTRY — композиционный корень Godot Agent.
#
# Единственный модуль, который знает про Godot: EditorPlugin, хуки add_*,
# сигналы редактора, EditorInterface. Всё остальное получает сервисы отсюда
# и не обращается к API редактора напрямую.
#
# Статус: ПРОТОТАЙП, НЕ ПОДКЛЮЧЁН.
# plugin.cfg по-прежнему указывает на plugin_universal.gd, поэтому плагин
# работает как прежде. Этот файл — готовая основа для шага 5 миграции.
#
# Что уже реализовано:
#   - единая точка сборки UI вместо четырёх разных мест;
#   - подписка на сигналы EditorPlugin вместо ручных подписок;
#   - контекстное меню дерева сцен и файловой системы;
#   - подменю команд вместо двух плоских пунктов меню;
#   - корректный detach всех интеграций в _exit_tree.
#
# Чего сознательно нет: единого HTTP-клиента и сервисного слоя — это шаг 4
# миграции, он трогает панель и стартовый экран и не должен смешиваться с
# переносом точки входа.
# ============================================================================

const PLUGIN_NAME := "Godot Agent"

var _integrations: Array[EditorContextMenuPlugin] = []
var _dock: Control = null
var _debugger: EditorDebuggerPlugin = null

# Подписки на сигналы редактора живут в отдельном модуле: у него одна
# причина существования, и в точке входа ему не место.
var _signals_integration: RefCounted = null

# Словарь локализации. Подменю берёт из него те же ключи, что и плоские
# пункты plugin_universal.gd, поэтому заголовки не расходятся ни на одном
# языке. Может остаться пустым — тогда работает запасной русский текст.
var _locale = null


## Контекстное меню дерева сцен и файловой системы: «Спросить агента про …».
##
## Пути выбранного передаются дальше, а не только название: без них агент
## не знает, о каком именно узле или файле его спросили. Список путей
## сохраняется при открытии меню, потому что обработчик пункта запускается
## уже после того, как Godot показал меню, и аргументы туда не доходят.
class SceneTreeMenu extends EditorContextMenuPlugin:
	var _host: EditorPlugin
	var _label: String
	var _paths: PackedStringArray = PackedStringArray()

	func _init(host: EditorPlugin, label: String) -> void:
		_host = host
		_label = label

	func _popup_menu(paths: PackedStringArray) -> void:
		if paths.is_empty():
			return
		_paths = paths
		add_context_menu_item("Спросить агента про " + _label, _on_ask)

	## Godot зовёт обработчик пункта контекстного меню С ОДНИМ аргументом,
	## хотя add_context_menu_item() ничего о сигнатуре не сообщает. Объявить
	## метод без параметров — значит получить ошибку в момент клика, то есть
	## ровно тогда, когда пользователь ждёт ответа. Аргумент не нужен: что
	## выбрано, уже лежит в _paths, заполненном в _popup_menu. Он объявлен
	## без типа и со значением по умолчанию, чтобы пережить и вызов с нулём
	## аргументов, и с любым типом, который движок подставит.
	func _on_ask(_item = null) -> void:
		if _host.has_method("agent_ask_about"):
			_host.call("agent_ask_about", _label, _paths)


func _enter_tree() -> void:
	_load_locale()
	_register_signals()
	_build_menu()
	_build_context_menus()
	_build_debugger()
	_build_dock()
	_ensure_fs_dock_connected()
	call_deferred("_promote_dock_tab")
	call_deferred("_report_entry_ready")
	# Подтверждение загрузки печатается не здесь, а в _report_entry_ready:
	# в _enter_tree панель ещё не успела собрать UI, и «загрузился» там означало бы
	# меньше, чем на самом деле.


## Подтверждение, что точка входа действительно отработала (ЗАДАЧА 5).
##
## Пока plugin.cfg указывал на plugin_universal.gd, признаком загрузки была
## строка про FileSystemDock. После переключения корня её больше нет, а
## проверять «плагин загрузился» оказалось нечем: headless-редактор стартует с
## кодом 0 и без единой ошибки даже тогда, когда плагин не инициализирован.
## Поэтому подтверждение печатается явно и содержит то, что важно: док,
## число интеграций и подписки на сигналы.
func _report_entry_ready() -> void:
	print("[Godot Agent] Точка входа agent_entry.gd загружена: dock=%s, интеграций=%d, сигналы=%s" % [
		"да" if _dock != null else "нет",
		_integrations.size(),
		"подключены" if _signals_integration != null else "нет",
	])


func _exit_tree() -> void:
	if _signals_integration != null:
		_signals_integration.detach()
		_signals_integration = null
	_disconnect_fs_dock()
	for integration in _integrations:
		remove_context_menu_plugin(integration)
	_integrations.clear()
	remove_tool_menu_item(PLUGIN_NAME)
	if _debugger:
		remove_debugger_plugin(_debugger)
		_debugger = null
	if _dock:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null


## Панель — единственное место, где собирается весь UI плагина.
##
## Сцена строится кодом, без привязки к абсолютным путям res://addons/…:
## папку аддона пользователь может как угодно назвать и переложить.
func _build_dock() -> void:
	if _dock != null:
		return
	var panel_script_path := _find_file(_addon_path(), "agent_panel.gd")
	if panel_script_path.is_empty():
		push_error("[Godot Agent] agent_panel.gd не найден в " + _addon_path())
		return
	_dock = _build_panel(panel_script_path)
	if _dock == null:
		return
	_dock.name = _menu_title("dock_title", "ИИ Агент")
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)


func _build_panel(panel_script_path: String) -> Control:
	var panel := Control.new()

	# Узел основных запросов панели. Он принадлежит дереву дока, а не панели:
	# панель берёт его через @onready $HTTPRequest.
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
	chat_log.text = "[color=green]" + _menu_title("system_ready",
		"Система готова. Работаем через локальный Godot Agent!") + "[/color]\n"
	vbox.add_child(chat_log)

	var pbox := HBoxContainer.new()
	pbox.name = "PendingActionBox"
	pbox.visible = false
	vbox.add_child(pbox)
	var action_label := Label.new()
	action_label.name = "ActionLabel"
	action_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	action_label.text = _menu_title("pending_default", "Агент хочет выполнить действие...")
	action_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	pbox.add_child(action_label)
	var confirm_btn := Button.new()
	confirm_btn.name = "ConfirmButton"
	confirm_btn.text = _menu_title("allow", "Разрешить")
	pbox.add_child(confirm_btn)
	var reject_btn := Button.new()
	reject_btn.name = "RejectButton"
	reject_btn.text = _menu_title("reject", "Отклонить")
	pbox.add_child(reject_btn)

	var hbox := HBoxContainer.new()
	hbox.name = "HBoxContainer"
	vbox.add_child(hbox)
	var input_field := TextEdit.new()
	input_field.name = "InputField"
	input_field.custom_minimum_size = Vector2(0, 60)
	input_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	input_field.placeholder_text = _menu_title("input_placeholder",
		"Спросите или дайте указание (Ctrl+Enter для отправки)...")
	input_field.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	hbox.add_child(input_field)
	var send_btn := Button.new()
	send_btn.name = "SendButton"
	send_btn.text = _menu_title("send", "Отправить")
	hbox.add_child(send_btn)

	# Кнопка выбора нейросети для открытого чата: какая модель и у какого
	# провайдера сейчас отвечает. Название модели бывает длинным, а панель
	# живёт в доке 250–400 px: без обрезки кнопка растянула бы наименьшую
	# ширину всей панели по длине подписи.
	var model_btn := Button.new()
	model_btn.name = "ChatModelBtn"
	model_btn.text = _menu_title("chat_model_pick", "🤖 Выбрать нейросеть")
	model_btn.clip_text = true
	vbox.add_child(model_btn)

	# Ящик редких инструментов. Остаётся в дереве и скрытым: панель наполняет
	# его в _ready, а при первом открытии настроек переносит узел целиком в
	# окно настроек — см. _on_settings_pressed в agent_panel.gd.
	var adv_box := VBoxContainer.new()
	adv_box.name = "AdvancedBox"
	adv_box.visible = false
	vbox.add_child(adv_box)
	var reinit_btn := Button.new()
	reinit_btn.name = "ReinitButton"
	reinit_btn.text = _menu_title("reinit",
		"Переинициализировать (переслать структуру проекта)")
	adv_box.add_child(reinit_btn)

	# Скрипт панели подключаем ПОСЛЕ создания детей: когда панель попадёт
	# в док, сработает _ready() и все @onready-ссылки найдут свои узлы.
	panel.set_script(load(panel_script_path))
	if panel.has_method("set_editor_plugin"):
		panel.call("set_editor_plugin", self)
	if _debugger and panel.has_method("set_runtime_debugger"):
		panel.call("set_runtime_debugger", _debugger)
	# Маршрут команд ОДНОНАПРАВЛЕННЫЙ: точка входа вызывает панель сама
	# (_handle_command -> панель). Обратной связи не нужно и раньше не было:
	# bind_command_handler передавал обработчик В панель, где он ни разу не
	# читался, а читался при этом никогда не записанный одноимённый слот в
	# точке входа. Из-за этого и был обрыв: клик доходил до пустого слота.
	return panel


## Маршрут команд меню в панель — то же, что умели плоские пункты меню
## рабочего плагина, плюс вопрос из контекстного меню.
func _handle_command(kind: String, what: String = "",
		paths: PackedStringArray = PackedStringArray()) -> void:
	match kind:
		"ask":
			if _dock != null and _dock.has_method("handle_context_ask"):
				_dock.call("handle_context_ask", what, paths)
			else:
				push_warning("[Godot Agent] Панель не готова принять вопрос из меню.")
		"file_rename":
			if _dock != null and _dock.has_method("open_safe_rename"):
				_dock.call("open_safe_rename")
		"node_rename":
			if _dock != null and _dock.has_method("open_safe_node_rename"):
				_dock.call("open_safe_node_rename")
		_:
			push_warning("[Godot Agent] Неизвестная команда меню: " + kind)


## Подменю команд. Сейчас это два плоских пункта; здесь — один вход,
## который растёт вместе с функционалом и не засоряет меню «Проекты».
##
## Идентификаторы — именованные константы: в add_item магия вроде `0`/`1`
## неотличима от позиции пункта, и при добавлении третьей команды легко
## перепутать, какой id какому действию соответствует.
const MENU_SAFE_RENAME_FILE := 101
const MENU_SAFE_NODE_RENAME := 202


## Подменю вместо плоских пунктов.
func _build_menu() -> void:
	var submenu := PopupMenu.new()
	submenu.add_item(_menu_title("safe_rename_title", "Безопасное переименование файла..."),
		MENU_SAFE_RENAME_FILE)
	submenu.add_item(_menu_title("safe_node_rename_title", "Безопасное переименование узла..."),
		MENU_SAFE_NODE_RENAME)
	add_tool_submenu_item(PLUGIN_NAME, submenu)
	submenu.id_pressed.connect(_on_menu_id)


## Раздача команд по id.
##
## Обработчик зовёт те же методы панели, что вызывали плоские пункты в
## plugin_universal.gd. Раньше здесь стоял `command_handler.call(id)` — он
## не назначен ни в одном файле проекта, поэтому оба пункта меню
## отрабатывали в никуда: пользователь кликал и не получал ничего.
func _on_menu_id(id: int) -> void:
	match id:
		MENU_SAFE_RENAME_FILE:
			_call_panel("open_safe_rename")
		MENU_SAFE_NODE_RENAME:
			_call_panel("open_safe_node_rename")
		_:
			push_warning("[Godot Agent] Неизвестный пункт меню: " + str(id))


## Точка входа диспетчера для проверок: тот же обработчик, но с подменой
## дока. В редакторе дока нет, а проверять маршрутизацию нужно.
func dispatch_menu_id_for_test(id: int) -> void:
	_on_menu_id(id)


## Док для проверок маршрутизации. В редакторе не используется.
var dock_for_test: Control = null


func _call_panel(method: StringName) -> void:
	var dock: Control = dock_for_test if dock_for_test != null else _dock
	if dock == null or not is_instance_valid(dock):
		return
	if not dock.has_method(method):
		# Панель ещё не собрана (или это не панель) — молча, как в
		# plugin_universal.gd: меню не должно сыпать ошибками при сборке.
		return
	dock.call(method)


## Перевод заголовка пункта. Ключи те же, что у плоских пунктов, поэтому
## подменю не расходится с ними ни на одном языке.
func _menu_title(key: String, fallback: String) -> String:
	if _locale != null:
		return _locale.t(key)
	return fallback


## Два контекстных меню — самый дешёвый способ встроить агента в редактор:
## он появляется ровно там, где пользователь уже работает.
func _build_context_menus() -> void:
	var tree_menu := SceneTreeMenu.new(self, "узел")
	add_context_menu_plugin(EditorContextMenuPlugin.CONTEXT_SLOT_SCENE_TREE, tree_menu)
	_integrations.append(tree_menu)

	var files_menu := SceneTreeMenu.new(self, "файл")
	add_context_menu_plugin(EditorContextMenuPlugin.CONTEXT_SLOT_FILESYSTEM, files_menu)
	_integrations.append(files_menu)


## Сигналы EditorPlugin — живая реакция на изменения проекта.
##
## Раньше плагин подписывался на FileSystemDock поиском, а на ScriptEditor
## напрямую. Теперь это публичный контракт движка, собранный в
## agent_integration_signals.gd. Здесь только создание и отписка.
func _register_signals() -> void:
	if _signals_integration != null:
		return
	var path := _addon_path() + "/agent_integration_signals.gd"
	if not ResourceLoader.exists(path):
		push_error("[Godot Agent] agent_integration_signals.gd не найден в " + path)
		return
	var script: Script = load(path)
	_signals_integration = script.new(self)
	_signals_integration.attach()


func _addon_path() -> String:
	var self_script: Script = get_script() as Script
	return self_script.resource_path.get_base_dir()


## Словарь локализации нужен заголовкам пунктов меню. Отсутствие файла —
## не ошибка: тогда остаётся запасной русский текст, как в plugin_universal.
func _load_locale() -> void:
	var path := _addon_path() + "/agent_locale.gd"
	if not ResourceLoader.exists(path):
		return
	_locale = load(path)


## Точка для плагина отладчика: один объект, один понятный хук.
func _build_debugger() -> void:
	_debugger = _make_runtime_debugger()
	if _debugger:
		add_debugger_plugin(_debugger)


func _make_runtime_debugger() -> EditorDebuggerPlugin:
	var self_script: Script = get_script() as Script
	var base: String = self_script.resource_path.get_base_dir()
	var path := base + "/agent_runtime_debugger.gd"
	if not ResourceLoader.exists(path):
		return null
	var script: Script = load(path)
	if script == null:
		return null
	return script.new() as EditorDebuggerPlugin


## Точка входа, которую вызывает контекстное меню.
##
## paths — то, что пользователь выбрал в дереве сцен или в файловой
## системе. Без них вопрос «про узел» не значит ничего конкретного,
## поэтому список передаётся дальше как есть, вместе с названием.
##
## Маршрут прямой, как у _on_menu_id. Раньше здесь стоял
## `command_handler.call(...)`, но это поле не назначалось нигде в проекте:
## объявлялось, читалось и никогда не записывалось, поэтому клик уходил в
## пустоту без единой ошибки. Обработчик нужен здесь один — этот метод, —
## и вызывать его нужно напрямую, без посредника.
func agent_ask_about(what: String, paths: PackedStringArray = PackedStringArray()) -> void:
	_handle_command("ask", what, paths)


## Поднимает вкладку агента первой — то же поведение, что сейчас даёт
## _promote_dock_tab в plugin_universal.gd.
func _promote_dock_tab() -> void:
	if _dock == null:
		return
	var parent := _dock.get_parent()
	var tabs := parent as TabContainer
	if tabs == null:
		return
	if tabs.get_child(0) != _dock:
		tabs.move_child(_dock, 0)
	var idx := tabs.get_tab_idx_from_control(_dock)
	if idx >= 0:
		tabs.current_tab = idx


## Перехват перемещений файлов в FileSystem: панель обновляет ссылки.
##
## Раньше это делал plugin_universal.gd поиском встроенного узла редактора.
## Здесь подписка оформлена как отдельная интеграция с честной отпиской.
func _ensure_fs_dock_connected() -> void:
	var fs_dock := EditorInterface.get_file_system_dock()
	if fs_dock == null:
		return
	if not fs_dock.files_moved.is_connected(_on_fs_files_moved):
		fs_dock.files_moved.connect(_on_fs_files_moved)
	if not fs_dock.folder_moved.is_connected(_on_fs_folder_moved):
		fs_dock.folder_moved.connect(_on_fs_folder_moved)


func _on_fs_files_moved(old_file: String, new_file: String) -> void:
	if _dock != null and _dock.has_method("handle_filesystem_move"):
		_dock.call("handle_filesystem_move", old_file, new_file, false)
	else:
		push_warning("[Godot Agent] Панель агента не готова к обработке перемещения файла.")


func _on_fs_folder_moved(old_folder: String, new_folder: String) -> void:
	if _dock != null and _dock.has_method("handle_filesystem_move"):
		_dock.call("handle_filesystem_move", old_folder, new_folder, true)
	else:
		push_warning("[Godot Agent] Панель агента не готова к обработке перемещения папки.")


func _disconnect_fs_dock() -> void:
	var fs_dock := EditorInterface.get_file_system_dock()
	if fs_dock == null:
		return
	if fs_dock.files_moved.is_connected(_on_fs_files_moved):
		fs_dock.files_moved.disconnect(_on_fs_files_moved)
	if fs_dock.folder_moved.is_connected(_on_fs_folder_moved):
		fs_dock.folder_moved.disconnect(_on_fs_folder_moved)


## Рекурсивный поиск файла внутри папки аддона (любая вложенность).
func _find_file(dir_path: String, file_name: String) -> String:
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
	for subdir in subdirs:
		var found: String = _find_file(subdir, file_name)
		if not found.is_empty():
			return found
	return ""