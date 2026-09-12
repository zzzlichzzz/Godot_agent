@tool
extends RefCounted

# Applies normalized project settings through Godot APIs. project.godot is
# never opened for writing here; Python owns the byte snapshot and rollback.

var _plugin: EditorPlugin


func configure(plugin: EditorPlugin) -> void:
	_plugin = plugin


func prepare(action: Dictionary, expected_hash: String) -> Dictionary:
	var ready := _ready(action, expected_hash)
	if not bool(ready.get("ok", false)):
		return ready
	var before := _capture(action)
	var simulated := before.duplicate(true)
	var changes: Array[String] = []
	var result := _simulate(simulated, action.get("operations", []), changes)
	if not bool(result.get("ok", false)):
		return result
	var before_hash := _semantic_hash(before)
	var result_hash := _semantic_hash(simulated)
	if before_hash == result_hash:
		return _fail("no_changes", "Настройки уже имеют запрошенные значения")
	return {"ok": true, "changes": changes, "semantic_hash": result_hash,
		"before_semantic_hash": before_hash, "requires_editor_restart": true}


func execute(action: Dictionary, expected_hash: String) -> Dictionary:
	var ready := _ready(action, expected_hash)
	if not bool(ready.get("ok", false)):
		return _with_hash(ready)
	var before := _capture(action)
	var simulated := before.duplicate(true)
	var changes: Array[String] = []
	var preview := _simulate(simulated, action.get("operations", []), changes)
	if not bool(preview.get("ok", false)):
		return _with_hash(preview)
	var expected_semantic_hash := str(action.get("_expected_semantic_hash", ""))
	if expected_semantic_hash == "" or _semantic_hash(simulated) != expected_semantic_hash:
		return _with_hash(_fail("preview_mismatch", "Настройки больше не совпадают с подтверждённым предпросмотром"))
	var applied := _apply(action.get("operations", []))
	if not bool(applied.get("ok", false)):
		var restored := _restore(before)
		applied["memory_restored"] = bool(restored.get("ok", false))
		if not bool(restored.get("ok", false)):
			applied["restore_error"] = str(restored.get("error", ""))
		return _with_hash(applied)
	var actual := _capture(action)
	if _semantic_hash(actual) != expected_semantic_hash:
		var restored := _restore(before)
		var mismatch := _fail("postcondition_failed", "Godot сохранил настройки не так, как показал предпросмотр")
		mismatch["memory_restored"] = bool(restored.get("ok", false))
		return _with_hash(mismatch)
	return {"ok": true, "project_hash": _file_hash(), "changes": changes,
		"requires_editor_restart": true}


func _ready(_action: Dictionary, expected_hash: String) -> Dictionary:
	if _plugin == null:
		return _fail("editor_unavailable", "EditorPlugin недоступен")
	var editor := _plugin.get_editor_interface()
	if editor and editor.is_playing_scene():
		return _fail("game_running", "Остановите запущенную игру перед изменением настроек проекта")
	if _file_hash() != expected_hash:
		return _fail("stale_project_settings", "project.godot изменился после подготовки действия")
	return {"ok": true}


func _touched_keys(action: Dictionary) -> Array[String]:
	var keys: Array[String] = []
	for operation in action.get("operations", []):
		match str(operation.get("op", "")):
			"add_input_action", "add_input_event": keys.append("input/" + str(operation.get("name", operation.get("action", ""))))
			"add_autoload", "remove_autoload": keys.append("autoload/" + str(operation.get("name", "")))
			"set_main_scene": keys.append("application/run/main_scene")
			"set_layer_name": keys.append("layer_names/%s/layer_%d" % [operation.get("layer", ""), int(operation.get("index", 0))])
			"set_display_settings":
				var mapping := _display_mapping()
				for field in operation:
					if mapping.has(field): keys.append(str(mapping[field]))
	keys.sort()
	var unique: Array[String] = []
	for key in keys:
		if key not in unique: unique.append(key)
	return unique


func _capture(action: Dictionary) -> Dictionary:
	var state := {}
	for key in _touched_keys(action):
		state[key] = {"present": ProjectSettings.has_setting(key),
			"value": ProjectSettings.get_setting(key) if ProjectSettings.has_setting(key) else null}
	return state


func _simulate(state: Dictionary, operations: Array, changes: Array[String]) -> Dictionary:
	for index in range(operations.size()):
		var operation = operations[index]
		var result := _simulate_operation(state, operation)
		if not bool(result.get("ok", false)):
			result["operation_index"] = index + 1
			return result
		changes.append(str(result.get("summary", operation.get("op", ""))))
	return {"ok": true}


func _simulate_operation(state: Dictionary, operation: Dictionary) -> Dictionary:
	var op := str(operation.get("op", ""))
	if op == "add_input_action":
		var key := "input/" + str(operation.get("name", ""))
		if state.has(key) and bool(state[key].get("present", false)):
			return _fail("input_action_exists", "InputMap action уже существует: " + key.trim_prefix("input/"))
		state[key] = {"present": true, "value": {"deadzone": float(operation.get("deadzone", 0.2)), "events": []}}
		return {"ok": true, "summary": "Добавлено действие ввода " + key.trim_prefix("input/")}
	if op == "add_input_event":
		var key := "input/" + str(operation.get("action", ""))
		if not state.has(key) or not bool(state[key].get("present", false)):
			return _fail("input_action_missing", "InputMap action не существует: " + key.trim_prefix("input/"))
		var event_result := _decode_input_event(operation.get("event", {}))
		if not bool(event_result.get("ok", false)):
			return event_result
		var config: Dictionary = state[key].get("value", {}).duplicate(true)
		var events: Array = config.get("events", []).duplicate()
		var event = event_result.get("value")
		for existing in events:
			if existing is InputEvent and (existing as InputEvent).is_match(event, true):
				return _fail("input_event_exists", "Такое событие ввода уже назначено")
		events.append(event)
		config["events"] = events
		state[key] = {"present": true, "value": config}
		return {"ok": true, "summary": "Добавлено событие для " + key.trim_prefix("input/")}
	if op == "add_autoload":
		var key := "autoload/" + str(operation.get("name", ""))
		if state.has(key) and bool(state[key].get("present", false)):
			return _fail("autoload_exists", "Autoload уже существует: " + key.trim_prefix("autoload/"))
		state[key] = {"present": true, "value": "*" + str(operation.get("path", ""))}
		return {"ok": true, "summary": "Добавлен autoload " + key.trim_prefix("autoload/")}
	if op == "remove_autoload":
		var key := "autoload/" + str(operation.get("name", ""))
		if not state.has(key) or not bool(state[key].get("present", false)):
			return _fail("autoload_missing", "Autoload не найден: " + key.trim_prefix("autoload/"))
		state[key] = {"present": false, "value": null}
		return {"ok": true, "summary": "Удалён autoload " + key.trim_prefix("autoload/")}
	var setting := _setting_for(operation)
	if not bool(setting.get("ok", false)):
		return setting
	var setting_key := str(setting.get("key", ""))
	if not _setting_supported(setting_key):
		return _fail("setting_unsupported", "Эта версия Godot не поддерживает настройку: " + setting_key)
	state[setting_key] = {"present": true, "value": setting.get("value")}
	return {"ok": true, "summary": "Изменена настройка " + setting_key}


func _setting_for(operation: Dictionary) -> Dictionary:
	match str(operation.get("op", "")):
		"set_main_scene": return {"ok": true, "key": "application/run/main_scene", "value": operation.get("scene", "")}
		"set_layer_name": return {"ok": true, "key": "layer_names/%s/layer_%d" % [operation.get("layer", ""), int(operation.get("index", 0))], "value": operation.get("name", "")}
	return _fail("operation", "Операция не задаёт одну настройку")


func _display_mapping() -> Dictionary:
	return {"viewport_width": "display/window/size/viewport_width",
		"viewport_height": "display/window/size/viewport_height",
		"window_mode": "display/window/size/mode", "resizable": "display/window/size/resizable",
		"stretch_mode": "display/window/stretch/mode", "stretch_aspect": "display/window/stretch/aspect"}


func _display_value(field: String, value):
	if field == "window_mode":
		return {"windowed": 0, "minimized": 1, "maximized": 2, "fullscreen": 3, "exclusive_fullscreen": 4}.get(str(value), -1)
	if field == "stretch_mode": return str(value)
	if field == "stretch_aspect": return str(value)
	return value


func _setting_supported(key: String) -> bool:
	for info in ProjectSettings.get_property_list():
		if str(info.get("name", "")) == key:
			return true
	# Layer names are sparse custom settings and may not exist until assigned.
	return key.begins_with("layer_names/")


func _apply(operations: Array) -> Dictionary:
	for index in range(operations.size()):
		var operation: Dictionary = operations[index]
		var op := str(operation.get("op", ""))
		if op == "add_autoload":
			var add_error := _plugin.add_autoload_singleton(str(operation["name"]), str(operation["path"]))
			if add_error != OK:
				return _fail("autoload_add_failed", "Не удалось добавить autoload: " + error_string(add_error))
		elif op == "remove_autoload":
			var remove_error := _plugin.remove_autoload_singleton(str(operation["name"]))
			if remove_error != OK:
				return _fail("autoload_remove_failed", "Не удалось удалить autoload: " + error_string(remove_error))
		elif op == "set_display_settings":
			var mapping := _display_mapping()
			for field in operation:
				if mapping.has(field): ProjectSettings.set_setting(mapping[field], _display_value(field, operation[field]))
		else:
			if op == "add_input_action":
				ProjectSettings.set_setting("input/" + str(operation["name"]),
					{"deadzone": float(operation.get("deadzone", 0.2)), "events": []})
			elif op == "add_input_event":
				var key := "input/" + str(operation["action"])
				var config: Dictionary = ProjectSettings.get_setting(key, {}).duplicate(true)
				var decoded := _decode_input_event(operation["event"])
				if not bool(decoded.get("ok", false)):
					decoded["operation_index"] = index + 1
					return decoded
				var events: Array = config.get("events", []).duplicate()
				events.append(decoded["value"])
				config["events"] = events
				ProjectSettings.set_setting(key, config)
			else:
				var setting := _setting_for(operation)
				if not bool(setting.get("ok", false)):
					setting["operation_index"] = index + 1
					return setting
				ProjectSettings.set_setting(setting["key"], setting["value"])
	var save_error := ProjectSettings.save()
	if save_error != OK:
		return _fail("save_failed", "ProjectSettings.save завершился ошибкой: " + error_string(save_error))
	return {"ok": true}


func _restore(before: Dictionary) -> Dictionary:
	for key in before:
		var item: Dictionary = before[key]
		if str(key).begins_with("autoload/"):
			var name := str(key).trim_prefix("autoload/")
			if ProjectSettings.has_setting(key):
				var remove_error := _plugin.remove_autoload_singleton(name)
				if remove_error != OK:
					return _fail("autoload_restore_failed", "Не удалось удалить autoload при восстановлении: " + error_string(remove_error))
			if bool(item.get("present", false)):
				var path := str(item.get("value", "")).trim_prefix("*")
				var add_error := _plugin.add_autoload_singleton(name, path)
				if add_error != OK:
					return _fail("autoload_restore_failed", "Не удалось вернуть autoload: " + error_string(add_error))
			continue
		if bool(item.get("present", false)):
			ProjectSettings.set_setting(key, item.get("value"))
		else:
			ProjectSettings.clear(key)
	var error := ProjectSettings.save()
	return {"ok": error == OK, "error": error_string(error) if error != OK else ""}


func _decode_input_event(spec: Dictionary) -> Dictionary:
	var event: InputEvent
	match str(spec.get("type", "")):
		"key":
			var key := InputEventKey.new()
			var code := OS.find_keycode_from_string(str(spec.get("key", "")))
			if code == KEY_NONE: return _fail("key_unknown", "Godot не знает клавишу " + str(spec.get("key", "")))
			if bool(spec.get("physical", false)): key.physical_keycode = code
			else: key.keycode = code
			key.ctrl_pressed = bool(spec.get("ctrl", false)); key.alt_pressed = bool(spec.get("alt", false))
			key.shift_pressed = bool(spec.get("shift", false)); key.meta_pressed = bool(spec.get("meta", false))
			event = key
		"mouse_button":
			var mouse := InputEventMouseButton.new(); mouse.button_index = int(spec.get("button", 0)); event = mouse
		"joypad_button":
			var button := InputEventJoypadButton.new(); button.button_index = int(spec.get("button", 0)); button.device = int(spec.get("device", -1)); event = button
		"joypad_motion":
			var motion := InputEventJoypadMotion.new(); motion.axis = int(spec.get("axis", 0)); motion.axis_value = float(spec.get("axis_value", 0)); motion.device = int(spec.get("device", -1)); event = motion
		_: return _fail("event_type", "Неподдерживаемый InputEvent")
	return {"ok": true, "value": event}


func _semantic_hash(state: Dictionary) -> String:
	var rows: Array[String] = []
	for key in state:
		var item: Dictionary = state[key]
		rows.append("%s|%s|%s" % [key, bool(item.get("present", false)), var_to_str(item.get("value"))])
	rows.sort()
	return HashingContext.hash(HashingContext.HASH_SHA256, "\n".join(rows).to_utf8_buffer()).hex_encode()


func _file_hash() -> String:
	return HashingContext.hash(HashingContext.HASH_SHA256, FileAccess.get_file_as_bytes("res://project.godot")).hex_encode()


func _with_hash(result: Dictionary) -> Dictionary:
	result["project_hash"] = _file_hash()
	return result


func _fail(code: String, message: String) -> Dictionary:
	return {"ok": false, "code": code, "error": message}
