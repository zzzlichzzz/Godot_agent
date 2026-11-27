@tool
extends RefCounted

# ---------------------------------------------------------------------------
# Подсветка строк, изменённых агентом (вынесено из agent_panel.gd).
# Красим не по номерам строк, а ПО СОДЕРЖИМОМУ блока: при любой правке
# блок ищется заново, и подсветка «переезжает» вместе с кодом. Публичные
# методы: apply(), clear(), watchdog(), on_editor_script_changed().
# ---------------------------------------------------------------------------

const HL_COLOR := Color(0.25, 0.85, 0.35, 0.16)
var _hl_path: String = ""
var _hl_block: String = ""
var _hl_lines: Array = []
var _hl_code_edit: CodeEdit = null
var _list_mark_dbg_done: bool = false


func apply(path: String, block: String) -> void:
	clear()
	_list_mark_dbg_done = false
	if not path.begins_with("res://") or not path.ends_with(".gd"):
		return
	if not FileAccess.file_exists(path):
		return
	var scr := load(path) as Script
	if scr == null:
		return
	_hl_path = path
	_hl_block = block.replace("\r\n", "\n").strip_edges(false, true)
	if _hl_block.is_empty():
		return
	# Открываем изменённый скрипт в редакторе, чтобы изменения были на виду.
	EditorInterface.edit_script(scr, -1, 0, false)
	_hook_current_code_edit()
	_repaint_highlight()
	if _hl_code_edit and _hl_lines.size() > 0:
		_hl_code_edit.set_caret_line(_hl_lines[0])
	_mark_script_in_list_experimental(path)


func _hook_current_code_edit() -> void:
	_hl_code_edit = null
	var script_editor := EditorInterface.get_script_editor()
	if not script_editor: return
	var current := script_editor.get_current_editor()
	if not current: return
	var code_edit := current.get_base_editor() as CodeEdit
	if not code_edit: return
	_hl_code_edit = code_edit
	if not code_edit.text_changed.is_connected(_on_hl_text_changed):
		code_edit.text_changed.connect(_on_hl_text_changed)


func _on_hl_text_changed() -> void:
	# Текст меняется — блок мог сместиться. Ищем его заново и перекрашиваем.
	if _hl_block != "":
		_repaint_highlight()


func on_editor_script_changed(scr: Script) -> void:
	# Вернулись на вкладку с подсвеченным скриптом — восстанавливаем покрас.
	if scr and _hl_path != "" and scr.resource_path == _hl_path:
		_hook_current_code_edit()
		_repaint_highlight()


func clear() -> void:
	if _hl_code_edit and is_instance_valid(_hl_code_edit):
		for l in range(_hl_code_edit.get_line_count()):
			_hl_code_edit.set_line_background_color(l, Color(0, 0, 0, 0))
	_hl_lines = []
	_hl_path = ""
	_hl_block = ""
	_hl_code_edit = null


func _repaint_highlight() -> void:
	if _hl_code_edit == null or not is_instance_valid(_hl_code_edit):
		return
	# Сначала гасим все строки: после правок номера могли сместиться,
	# и точечная очистка по старым номерам оставила бы «хвосты».
	for l in range(_hl_code_edit.get_line_count()):
		_hl_code_edit.set_line_background_color(l, Color(0, 0, 0, 0))
	_hl_lines = []
	if _hl_block == "":
		return
	var idx := _hl_code_edit.text.find(_hl_block)
	if idx == -1:
		return  # блок изменён/удалён пользователем — подсвечивать нечего
	var start_line := _hl_code_edit.text.substr(0, idx).count("\n")
	var block_line_count := _hl_block.count("\n") + 1
	for i in range(block_line_count):
		var line := start_line + i
		if line < _hl_code_edit.get_line_count():
			_hl_code_edit.set_line_background_color(line, HL_COLOR)
			_hl_lines.append(line)


func watchdog() -> void:
	# Редактор Godot при перепроверке кода САМ сбрасывает фоновые цвета строк.
	# Раз в секунду проверяем и восстанавливаем подсветку, если её затёрли.
	if _hl_block == "":
		return
	if _hl_code_edit == null or not is_instance_valid(_hl_code_edit):
		return
	var intact := _hl_lines.size() > 0
	for l in _hl_lines:
		if l >= _hl_code_edit.get_line_count() or _hl_code_edit.get_line_background_color(l) != HL_COLOR:
			intact = false
			break
	if not intact:
		_repaint_highlight()
	_mark_script_in_list_experimental(_hl_path)


func _mark_script_in_list_experimental(path: String) -> void:
	# ЭКСПЕРИМЕНТ: список скриптов слева — внутренний UI редактора без
	# публичного API. Если внутренности Godot изменятся — просто тихо ничего.
	if path.is_empty(): return
	var script_editor := EditorInterface.get_script_editor()
	if not script_editor: return
	var fname := path.get_file()
	var lists_found := 0
	var matched := 0
	for node in script_editor.find_children("*", "ItemList", true, false):
		var item_list := node as ItemList
		if item_list == null: continue
		lists_found += 1
		for i in range(item_list.item_count):
			var t := item_list.get_item_text(i)
			var tip := item_list.get_item_tooltip(i)
			if t == fname or t.begins_with(fname + "(") or tip == path or tip.ends_with("/" + fname):
				item_list.set_item_custom_fg_color(i, Color(0.45, 1.0, 0.45))
				matched += 1
	if not _list_mark_dbg_done:
		_list_mark_dbg_done = true
		print("[ИИ-Агент] Пометка в списке скриптов: ItemList найдено %d, совпадений %d (файл: %s)" % [lists_found, matched, fname])
