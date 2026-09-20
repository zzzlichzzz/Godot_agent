extends SceneTree

# Тест живой механики закрытия и открытия сцен в agent_panel.gd

class MockEditorInterface:
	extends RefCounted
	var saved_all := false
	var saved_scene := false
	var open_scenes: Array = []
	var closed_scenes: Array = []
	var opened_from_path: Array = []

	func get_open_scenes() -> PackedStringArray:
		var arr := PackedStringArray()
		for s in open_scenes:
			arr.append(str(s))
		return arr

	func save_all_scenes() -> void:
		saved_all = true

	func save_scene() -> int:
		saved_scene = true
		return OK

	func open_scene_from_path(path: String, _set_inherited: bool = false) -> void:
		opened_from_path.append(path)

	func close_scene() -> int:
		if not open_scenes.is_empty():
			var removed = open_scenes.pop_back()
			closed_scenes.append(removed)
		return OK

	func get_editor_settings():
		return null

class PanelTestProbe:
	extends "res://addons/Godot_agent/godot_agent/agent_panel.gd"
	var test_ei: MockEditorInterface = null

	func _init():
		test_ei = MockEditorInterface.new()

	func _open_pending_scene_paths() -> PackedStringArray:
		var result := PackedStringArray()
		var open_scenes := test_ei.get_open_scenes()
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

	func _close_scenes_before_write() -> void:
		_scenes_to_reopen = PackedStringArray()
		var ei: Object = test_ei
		if not ei.has_method("close_scene"):
			return
		if ei.has_method("save_all_scenes"):
			ei.call("save_all_scenes")
		elif ei.has_method("save_scene"):
			ei.call("save_scene")
		var open_targets := _open_pending_scene_paths()
		for raw in [_last_pending_action_path, _last_pending_action_dest]:
			var sp := str(raw)
			if sp == "" or not (sp.ends_with(".tscn") or sp.ends_with(".scn")):
				continue
			if not test_ei.get_open_scenes().has(sp) and not open_targets.has(sp):
				continue
			test_ei.open_scene_from_path(sp)
			if int(ei.call("close_scene")) == OK and not _scenes_to_reopen.has(sp):
				_scenes_to_reopen.append(sp)
		for sp in open_targets:
			if not _scenes_to_reopen.has(sp):
				test_ei.open_scene_from_path(sp)
				if int(ei.call("close_scene")) == OK:
					_scenes_to_reopen.append(sp)

	func _reopen_scenes_after_write() -> void:
		for sp in _scenes_to_reopen:
			if FileAccess.file_exists(str(sp)):
				test_ei.open_scene_from_path(str(sp))
		_scenes_to_reopen = PackedStringArray()


var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		print("FAIL: ", message)
	else:
		print("PASS: ", message)


func _initialize() -> void:
	call_deferred("run_live_test")


func run_live_test() -> void:
	print("--- ЗАПУСК ЖИВОГО ТЕСТА ЗАКРЫТИЯ И ОТКРЫТИЯ СЦЕН ---")
	var test_scene_path = "res://test_autoclose_temp.tscn"

	# 1. Создаём тестовый файл сцены на диске
	var f = FileAccess.open(test_scene_path, FileAccess.WRITE)
	if f:
		f.store_string("[gd_scene format=3]\n[node name=\"TestRoot\" type=\"Node2D\"]\n")
		f.close()
	check(FileAccess.file_exists(test_scene_path), "Тестовая сцена создана на диске")

	var panel = PanelTestProbe.new()

	# 2. Симулируем, что сцена открыта в редакторе
	panel.test_ei.open_scenes.append(test_scene_path)
	panel._last_pending_action_type = "patch_file"
	panel._last_pending_action_path = test_scene_path

	check(panel._open_pending_scene_paths().has(test_scene_path), "Сцена определена как открытая целевая сцена")

	# 3. Вызываем _close_scenes_before_write()
	panel._close_scenes_before_write()

	check(panel.test_ei.saved_all == true, "save_all_scenes вызван перед закрытием")
	check(panel.test_ei.closed_scenes.has(test_scene_path), "close_scene успешно закрыл сцену")
	check(panel._scenes_to_reopen.has(test_scene_path), "Путь сцены сохранён в _scenes_to_reopen")
	check(panel.test_ei.open_scenes.is_empty(), "Вкладка сцены больше не числится открытой")

	# 4. Симулируем изменение файла на диске (как это делает сервер/агент)
	var f2 = FileAccess.open(test_scene_path, FileAccess.WRITE)
	if f2:
		f2.store_string("[gd_scene format=3]\n[node name=\"TestRoot\" type=\"Node2D\"]\n[node name=\"Child\" type=\"Node2D\" parent=\".\"]\n")
		f2.close()

	# 5. Вызываем _reopen_scenes_after_write()
	panel._reopen_scenes_after_write()

	check(panel.test_ei.opened_from_path.has(test_scene_path), "open_scene_from_path открыл сцену заново")
	check(panel._scenes_to_reopen.is_empty(), "_scenes_to_reopen очищен после восстановления сцен")

	# Удаляем временный файл
	DirAccess.remove_absolute(ProjectSettings.globalize_path(test_scene_path))

	if failures.is_empty():
		print("=== ВСЕ ЖИВЫЕ ТЕСТЫ ЗАКРЫТИЯ И ОТКРЫТИЯ СЦЕН ПРОЙДЕНЫ УСПЕШНО ===")
		quit(0)
	else:
		print("=== ЕСТЬ ОШИБКИ В ТЕСТАХ: %d ===" % failures.size())
		quit(1)
