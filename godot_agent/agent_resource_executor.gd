@tool
extends RefCounted

var _plugin: EditorPlugin


func configure(plugin: EditorPlugin) -> void:
	_plugin = plugin


func prepare(action: Dictionary, expected_hash: String) -> Dictionary:
	var opened := _open_target(action, expected_hash)
	if not bool(opened.get("ok", false)):
		return opened
	var resource: Resource = opened.resource
	var before_semantic := _semantic_hash(resource, action.get("operations", []), str(action.get("resource", "")))
	var changes: Array[String] = []
	var applied := _apply_operations(resource, action.get("operations", []), changes)
	if not bool(applied.get("ok", false)):
		return applied
	var semantic_hash := _semantic_hash(resource, action.get("operations", []), str(action.get("resource", "")))
	if semantic_hash == before_semantic:
		return _fail("no_changes", "Операции не изменяют семантическое состояние ресурса")
	_queue_edited_preview(resource, action.get("action_id", ""))
	return {"ok": true, "changes": changes,
		"semantic_hash": semantic_hash,
		"dependency_fingerprint": _dependency_fingerprint(action),
		"preview_status": "requested"}


func execute(action: Dictionary, expected_hash: String) -> Dictionary:
	var opened := _open_target(action, expected_hash)
	if not bool(opened.get("ok", false)):
		return opened
	var resource: Resource = opened.resource
	var changes: Array[String] = []
	var applied := _apply_operations(resource, action.get("operations", []), changes)
	if not bool(applied.get("ok", false)):
		return applied
	var semantic_hash := _semantic_hash(resource, action.get("operations", []), str(action.get("resource", "")))
	if semantic_hash != str(action.get("_expected_semantic_hash", "")):
		return _fail("preview_mismatch", "Результат выполнения отличается от предпросмотра")
	if _dependency_fingerprint(action) != str(action.get("_expected_dependency_fingerprint", "")):
		return _fail("dependency_changed", "Импортируемая зависимость изменилась после предпросмотра")
	var path := str(action.get("resource", ""))
	var uid_before := ResourceLoader.get_resource_uid(path)
	var temporary_path := path.get_basename() + ".agent-resource-%s.tmp.tres" % str(Time.get_ticks_usec())
	var save_error := ResourceSaver.save(resource, temporary_path)
	if save_error != OK:
		return _fail("save_failed", "ResourceSaver.save вернул ошибку %s" % save_error)
	var temporary_resource = ResourceLoader.load(temporary_path, "", ResourceLoader.CACHE_MODE_IGNORE)
	if not temporary_resource is Resource:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(temporary_path))
		return _fail("temporary_reload_failed", "Временный ресурс не загружается")
	if _semantic_hash(temporary_resource, action.get("operations", []), path) != str(action.get("_expected_semantic_hash", "")):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(temporary_path))
		return _fail("temporary_semantic_mismatch", "Временный ресурс отличается от предпросмотра")
	temporary_resource = null
	resource = null
	var replace_error := _replace_resource_file(temporary_path, path)
	if replace_error != OK:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(temporary_path))
		return _post_save_fail("replace_failed", "Не удалось атомарно заменить ресурс: %s" % replace_error, path)
	var reloaded = ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE)
	if not reloaded is Resource:
		return _post_save_fail("reload_failed", "Сохранённый ресурс не загружается", path)
	var uid_after := ResourceLoader.get_resource_uid(path)
	if uid_before != uid_after:
		return _post_save_fail("uid_changed", "UID существующего ресурса изменился при сохранении", path)
	var reloaded_semantic := _semantic_hash(reloaded, action.get("operations", []), path)
	if reloaded_semantic != str(action.get("_expected_semantic_hash", "")):
		return _post_save_fail("saved_semantic_mismatch",
			"Сохранённый ресурс отличается от подтверждённого предпросмотра", path)
	var filesystem := _plugin.get_editor_interface().get_resource_filesystem()
	if filesystem and filesystem.has_method("update_file"):
		filesystem.update_file(path)
	var previewer = _plugin.get_editor_interface().get_resource_previewer()
	if previewer:
		previewer.check_for_invalidation(path)
		previewer.queue_resource_preview(path, self, "_on_preview_ready", action.get("action_id", ""))
	return {"ok": true, "resource_hash": _file_hash(path), "semantic_hash": semantic_hash,
		"preview_status": "requested"}


func reload_after_recovery(path: String) -> void:
	if _plugin == null:
		return
	var filesystem := _plugin.get_editor_interface().get_resource_filesystem()
	if filesystem and filesystem.has_method("update_file"):
		filesystem.update_file(path)
	ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_REPLACE)


func _open_target(action: Dictionary, expected_hash: String) -> Dictionary:
	if _plugin == null:
		return _fail("editor_unavailable", "EditorPlugin недоступен")
	if _plugin.get_editor_interface().is_playing_scene():
		return _fail("game_running", "Остановите запущенную игру перед изменением ресурса")
	var path := str(action.get("resource", ""))
	if not path.begins_with("res://") or not path.to_lower().ends_with(".tres"):
		return _fail("invalid_path", "Поддерживаются только существующие res://*.tres")
	if _file_hash(path) != expected_hash:
		return _fail("stale_resource", "Ресурс изменился после подготовки")
	var edited := _plugin.get_editor_interface().get_inspector().get_edited_object() as Resource
	if edited and edited.resource_path == path:
		return _fail("resource_open", "Закройте ресурс в Inspector перед изменением")
	var filesystem := _plugin.get_editor_interface().get_resource_filesystem()
	if filesystem and filesystem.is_scanning():
		return _fail("import_not_ready", "Godot ещё импортирует ресурсы; повторите после завершения")
	for dependency_path in action.get("wait_for_import", []):
		if not ResourceLoader.exists(str(dependency_path)):
			return _fail("import_not_ready", "Ресурс ещё не импортирован: %s" % dependency_path)
		if ResourceLoader.load(str(dependency_path), "", ResourceLoader.CACHE_MODE_IGNORE) == null:
			return _fail("import_failed", "Импортированный ресурс не загружается: %s" % dependency_path)
	var loaded = ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE)
	if not loaded is Resource:
		return _fail("load_failed", "ResourceLoader не смог загрузить ресурс")
	return {"ok": true, "resource": loaded}


func _apply_operations(resource: Resource, operations: Array, changes: Array[String]) -> Dictionary:
	for operation in operations:
		var result := _apply_operation(resource, operation as Dictionary, changes)
		if not bool(result.get("ok", false)):
			return result
	return {"ok": true}


func _apply_operation(root: Resource, operation: Dictionary, changes: Array[String]) -> Dictionary:
	match str(operation.get("op", "")):
		"set_property":
			return _set_property(root, operation, changes)
		"replace_reference":
			return _replace_reference(root, operation, changes)
		"animation_add_value_track":
			return _animation_add_value_track(root, operation, changes)
		"sprite_frames_add_animation":
			return _sprite_frames_add_animation(root, operation, changes)
		"theme_set_item":
			return _theme_set_item(root, operation, changes)
		"tileset_add_atlas_source":
			return _tileset_add_atlas_source(root, operation, changes)
	return _fail("unknown_operation", "Неизвестная операция ресурса")


func _resolve_target(root: Resource, path: Array) -> Dictionary:
	var current := root
	for raw_name in path:
		var name := str(raw_name)
		var info := _property_info(current, name)
		if info.is_empty() or not _is_stored(info):
			return _fail("invalid_target", "Свойство target не существует или не сохраняется: %s" % name)
		var next = current.get(name)
		if not next is Resource:
			return _fail("invalid_target", "target проходит не через Resource: %s" % name)
		var next_path := str((next as Resource).resource_path)
		if next_path != "" and not next_path.begins_with(root.resource_path + "::"):
			return _fail("external_target", "Нельзя изменять внешний ресурс через target")
		current = next
	return {"ok": true, "resource": current}


func _set_property(root: Resource, operation: Dictionary, changes: Array[String]) -> Dictionary:
	var target_result := _resolve_target(root, operation.get("target", []))
	if not bool(target_result.get("ok", false)):
		return target_result
	var target: Resource = target_result.resource
	var property_name := str(operation.get("property", ""))
	if property_name in ["resource_path", "resource_name", "resource_scene_unique_id", "script"]:
		return _fail("property_denied", "Служебное свойство ресурса изменять нельзя")
	var info := _property_info(target, property_name)
	if info.is_empty() or not _is_stored(info):
		return _fail("property_missing", "Свойство не существует или не сохраняется: %s" % property_name)
	var decoded := _decode_value(operation.get("value", {}))
	if not bool(decoded.get("ok", false)):
		return decoded
	var value = decoded.value
	if not _value_matches_property(value, info):
		return _fail("type_mismatch", "Тип значения не совпадает со свойством %s" % property_name)
	target.set(property_name, value)
	if not _values_equivalent(target.get(property_name), value):
		return _fail("property_rejected", "Ресурс отклонил значение свойства %s" % property_name)
	changes.append("Свойство %s изменено" % property_name)
	return {"ok": true}


func _replace_reference(root: Resource, operation: Dictionary, changes: Array[String]) -> Dictionary:
	var target_result := _resolve_target(root, operation.get("target", []))
	if not bool(target_result.get("ok", false)):
		return target_result
	var replacement = ResourceLoader.load(str(operation.new), "", ResourceLoader.CACHE_MODE_IGNORE)
	if not replacement is Resource:
		return _fail("reference_load_failed", "Новая ссылка не загружается")
	var visited := {}
	var count := _replace_in_resource(target_result.resource, str(operation.old), replacement, root.resource_path, visited)
	if count != int(operation.expected_count):
		return _fail("reference_count", "Найдено ссылок %d, ожидалось %d" % [count, operation.expected_count])
	changes.append("Заменено ссылок: %d" % count)
	return {"ok": true}


func _replace_in_resource(resource: Resource, old_path: String, replacement: Resource,
		root_path: String, visited: Dictionary) -> int:
	var id := resource.get_instance_id()
	if visited.has(id):
		return 0
	visited[id] = true
	var count := 0
	for info in resource.get_property_list():
		if not _is_stored(info):
			continue
		var name := str(info.name)
		var value = resource.get(name)
		if value is Resource:
			var child := value as Resource
			if child.resource_path == old_path:
				resource.set(name, replacement)
				count += 1
			elif child.resource_path == "" or child.resource_path.begins_with(root_path + "::"):
				count += _replace_in_resource(child, old_path, replacement, root_path, visited)
		elif value is Array:
			var changed := false
			for index in range(value.size()):
				if value[index] is Resource:
					var child := value[index] as Resource
					if child.resource_path == old_path:
						value[index] = replacement
						count += 1
						changed = true
					elif child.resource_path == "" or child.resource_path.begins_with(root_path + "::"):
						count += _replace_in_resource(child, old_path, replacement, root_path, visited)
			if changed:
				resource.set(name, value)
		elif value is Dictionary:
			var changed := false
			for key in value.keys():
				if value[key] is Resource:
					var child := value[key] as Resource
					if child.resource_path == old_path:
						value[key] = replacement
						count += 1
						changed = true
					elif child.resource_path == "" or child.resource_path.begins_with(root_path + "::"):
						count += _replace_in_resource(child, old_path, replacement, root_path, visited)
			if changed:
				resource.set(name, value)
	return count


func _animation_add_value_track(root: Resource, operation: Dictionary, changes: Array[String]) -> Dictionary:
	if not root is Animation:
		return _fail("wrong_resource_type", "Операция требует корневой Animation")
	var animation := root as Animation
	var track_path := NodePath(str(operation.path))
	if animation.find_track(track_path, Animation.TYPE_VALUE) >= 0:
		return _fail("track_exists", "Animation уже содержит такой value track")
	var index := animation.add_track(Animation.TYPE_VALUE)
	animation.track_set_path(index, track_path)
	var interpolation = {"nearest": Animation.INTERPOLATION_NEAREST,
		"linear": Animation.INTERPOLATION_LINEAR, "cubic": Animation.INTERPOLATION_CUBIC}
	var update = {"continuous": Animation.UPDATE_CONTINUOUS,
		"discrete": Animation.UPDATE_DISCRETE, "capture": Animation.UPDATE_CAPTURE}
	animation.track_set_interpolation_type(index, interpolation[str(operation.interpolation)])
	animation.value_track_set_update_mode(index, update[str(operation.update_mode)])
	for key in operation["keys"]:
		if float(key.time) > animation.length:
			return _fail("key_out_of_range", "Ключ Animation находится после конца анимации")
		var decoded := _decode_value(key.value)
		if not bool(decoded.get("ok", false)):
			return decoded
		animation.track_insert_key(index, float(key.time), decoded.value, float(key.transition))
	changes.append("Добавлен value track %s" % track_path)
	return {"ok": true}


func _sprite_frames_add_animation(root: Resource, operation: Dictionary, changes: Array[String]) -> Dictionary:
	if not root is SpriteFrames:
		return _fail("wrong_resource_type", "Операция требует корневой SpriteFrames")
	var frames := root as SpriteFrames
	var animation_name := StringName(str(operation.name))
	if frames.has_animation(animation_name):
		return _fail("animation_exists", "SpriteFrames уже содержит эту анимацию")
	frames.add_animation(animation_name)
	frames.set_animation_speed(animation_name, float(operation.fps))
	frames.set_animation_loop(animation_name, bool(operation.loop))
	for frame in operation.frames:
		var decoded := _decode_value(frame.texture)
		if not bool(decoded.get("ok", false)) or not decoded.value is Texture2D:
			return _fail("texture_type", "Кадр SpriteFrames требует Texture2D")
		frames.add_frame(animation_name, decoded.value, float(frame.duration))
	changes.append("Добавлена анимация SpriteFrames %s" % animation_name)
	return {"ok": true}


func _theme_set_item(root: Resource, operation: Dictionary, changes: Array[String]) -> Dictionary:
	if not root is Theme:
		return _fail("wrong_resource_type", "Операция требует корневой Theme")
	var theme := root as Theme
	var data_type := str(operation.data_type)
	var item := StringName(str(operation.name))
	var theme_type := StringName(str(operation.theme_type))
	var method_suffix = {"color": "color", "constant": "constant", "font": "font",
		"font_size": "font_size", "icon": "icon", "stylebox": "stylebox"}[data_type]
	if not bool(operation.overwrite) and theme.call("has_" + method_suffix, item, theme_type):
		return _fail("theme_item_exists", "Theme item уже существует")
	var decoded := _decode_value(operation.value)
	if not bool(decoded.get("ok", false)):
		return decoded
	var expected_classes = {"font": "Font", "icon": "Texture2D", "stylebox": "StyleBox"}
	if data_type == "color" and not (decoded.value is Color):
		return _fail("theme_value_type", "Theme color требует Color")
	if data_type in ["constant", "font_size"] and not (decoded.value is int):
		return _fail("theme_value_type", "Theme constant/font_size требует int")
	if expected_classes.has(data_type) and (not (decoded.value is Resource) or
			not (decoded.value as Resource).is_class(expected_classes[data_type])):
		return _fail("theme_value_type", "Theme %s требует %s" % [data_type, expected_classes[data_type]])
	theme.call("set_" + method_suffix, item, theme_type, decoded.value)
	if not theme.call("has_" + method_suffix, item, theme_type):
		return _fail("theme_item_rejected", "Theme не сохранил item")
	var stored = theme.call("get_" + method_suffix, item, theme_type)
	if not _values_equivalent(stored, decoded.value):
		return _fail("theme_item_rejected", "Theme сохранил другое значение item")
	changes.append("Theme %s/%s/%s изменён" % [theme_type, data_type, item])
	return {"ok": true}


func _tileset_add_atlas_source(root: Resource, operation: Dictionary, changes: Array[String]) -> Dictionary:
	if not root is TileSet:
		return _fail("wrong_resource_type", "Операция требует корневой TileSet")
	var tileset := root as TileSet
	var source_id := int(operation.source_id)
	if tileset.has_source(source_id):
		return _fail("source_exists", "TileSet source_id уже существует")
	var decoded := _decode_value(operation.texture)
	if not bool(decoded.get("ok", false)) or not decoded.value is Texture2D:
		return _fail("texture_type", "TileSet atlas требует Texture2D")
	var source := TileSetAtlasSource.new()
	source.texture = decoded.value
	source.texture_region_size = Vector2i(int(operation.texture_region_size[0]), int(operation.texture_region_size[1]))
	for tile in operation.tiles:
		var coordinates := Vector2i(int(tile[0]), int(tile[1]))
		if not source.has_room_for_tile(
				coordinates, Vector2i.ONE, 1, Vector2i.ZERO, 1, Vector2i(-1, -1)):
			return _fail("tile_out_of_bounds", "В atlas нет места для tile %s" % coordinates)
		source.create_tile(coordinates)
		if not source.has_tile(coordinates):
			return _fail("tile_create_failed", "TileSetAtlasSource не создал tile %s" % coordinates)
	tileset.add_source(source, source_id)
	changes.append("Добавлен TileSet atlas source %d" % source_id)
	return {"ok": true}


func _decode_value(tagged: Dictionary) -> Dictionary:
	var kind := str(tagged.get("type", ""))
	var raw = tagged.get("value")
	match kind:
		"Nil": return {"ok": true, "value": null}
		"bool": return {"ok": true, "value": bool(raw)}
		"int": return {"ok": true, "value": int(raw)}
		"float": return {"ok": true, "value": float(raw)}
		"String": return {"ok": true, "value": str(raw)}
		"StringName": return {"ok": true, "value": StringName(str(raw))}
		"NodePath": return {"ok": true, "value": NodePath(str(raw))}
		"Vector2": return {"ok": true, "value": Vector2(float(raw[0]), float(raw[1]))}
		"Vector2i": return {"ok": true, "value": Vector2i(int(raw[0]), int(raw[1]))}
		"Vector3": return {"ok": true, "value": Vector3(float(raw[0]), float(raw[1]), float(raw[2]))}
		"Vector3i": return {"ok": true, "value": Vector3i(int(raw[0]), int(raw[1]), int(raw[2]))}
		"Color": return {"ok": true, "value": Color(float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))}
		"ResourcePath":
			var loaded = ResourceLoader.load(str(raw), "", ResourceLoader.CACHE_MODE_IGNORE)
			return {"ok": true, "value": loaded} if loaded is Resource else _fail("resource_load_failed", "ResourcePath не загружается")
		"NewSubresource":
			var resource_class := str(tagged.get("class", ""))
			if not ClassDB.class_exists(resource_class) or not ClassDB.can_instantiate(resource_class) or not ClassDB.is_parent_class(resource_class, "Resource"):
				return _fail("invalid_resource_class", "Класс NewSubresource недоступен")
			var instance = ClassDB.instantiate(resource_class)
			if not instance is Resource:
				return _fail("invalid_resource_class", "NewSubresource не является Resource")
			for item in tagged.get("properties", []):
				var info := _property_info(instance, str(item.property))
				if info.is_empty() or not _is_stored(info):
					return _fail("property_missing", "Свойство NewSubresource не сохраняется")
				var decoded := _decode_value(item.value)
				if not bool(decoded.get("ok", false)) or not _value_matches_property(decoded.value, info):
					return _fail("type_mismatch", "Неверный тип свойства NewSubresource")
				instance.set(str(item.property), decoded.value)
				if not _values_equivalent(instance.get(str(item.property)), decoded.value):
					return _fail("property_rejected", "NewSubresource отклонил свойство")
			return {"ok": true, "value": instance}
	return _fail("unsupported_value", "Неподдерживаемый tagged Variant")


func _property_info(object: Object, property_name: String) -> Dictionary:
	for info in object.get_property_list():
		if str(info.name) == property_name:
			return info
	return {}


func _is_stored(info: Dictionary) -> bool:
	return (int(info.get("usage", 0)) & PROPERTY_USAGE_STORAGE) != 0


func _value_matches_type(value, expected: int) -> bool:
	if value == null:
		return expected in [TYPE_NIL, TYPE_OBJECT]
	if expected == TYPE_FLOAT and value is int:
		return true
	return typeof(value) == expected


func _value_matches_property(value, info: Dictionary) -> bool:
	if not _value_matches_type(value, int(info.get("type", TYPE_NIL))):
		return false
	if value == null or not (value is Resource):
		return true
	var expected_class := str(info.get("class_name", ""))
	if expected_class == "" and int(info.get("hint", PROPERTY_HINT_NONE)) == PROPERTY_HINT_RESOURCE_TYPE:
		expected_class = str(info.get("hint_string", "")).split(",", false, 1)[0]
	return expected_class == "" or (value as Resource).is_class(expected_class)


func _values_equivalent(left, right) -> bool:
	return left == right


func _semantic_hash(root: Resource, operations: Array, canonical_path: String = "") -> String:
	var rows: Array[String] = [root.get_class()]
	for operation in operations:
		rows.append(JSON.stringify(operation, "", true))
	var root_path := canonical_path if canonical_path != "" else root.resource_path
	rows.append(_resource_projection(root, root_path, {}, 0, true))
	return ("\n".join(rows)).sha256_text()


func _resource_projection(resource: Resource, root_path: String, visited: Dictionary, depth: int,
		is_root: bool = false) -> String:
	if depth > 6 or visited.has(resource.get_instance_id()):
		return "<cycle>"
	visited[resource.get_instance_id()] = true
	var stable_path := root_path if is_root else resource.resource_path
	var rows: Array[String] = [resource.get_class(), stable_path]
	for info in resource.get_property_list():
		if not _is_stored(info):
			continue
		var name := str(info.name)
		var value = resource.get(name)
		if value is Resource and ((value as Resource).resource_path == "" or (value as Resource).resource_path.begins_with(root_path + "::")):
			rows.append(name + "=" + _resource_projection(value, root_path, visited, depth + 1))
		else:
			rows.append(name + "=" + var_to_str(value))
	rows.sort()
	return "{" + "|".join(rows) + "}"


func _dependency_fingerprint(action: Dictionary) -> String:
	var rows: Array[String] = []
	for raw_path in action.get("wait_for_import", []):
		var path := str(raw_path)
		rows.append(path + ":" + _file_hash(path))
		var import_path := path + ".import"
		if FileAccess.file_exists(import_path):
			rows.append(import_path + ":" + _file_hash(import_path))
	rows.sort()
	return ("\n".join(rows)).sha256_text()


func _queue_edited_preview(resource: Resource, token) -> void:
	if _plugin == null:
		return
	var previewer = _plugin.get_editor_interface().get_resource_previewer()
	if previewer:
		previewer.queue_edited_resource_preview(resource, self, "_on_preview_ready", token)


func _on_preview_ready(_path: String, _preview: Texture2D, _thumbnail: Texture2D, _userdata) -> void:
	pass


func _file_hash(path: String) -> String:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return ""
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(file.get_buffer(file.get_length()))
	file.close()
	return context.finish().hex_encode()


func _fail(code: String, message: String) -> Dictionary:
	return {"ok": false, "code": code, "error": message}


func _post_save_fail(code: String, message: String, path: String) -> Dictionary:
	var result := _fail(code, message)
	result["resource_hash"] = _file_hash(path)
	return result


func _replace_resource_file(source: String, target: String) -> Error:
	var source_absolute := ProjectSettings.globalize_path(source)
	var target_absolute := ProjectSettings.globalize_path(target)
	var backup_absolute := target_absolute + ".agent-backup"
	DirAccess.remove_absolute(backup_absolute)
	var backup_error := DirAccess.rename_absolute(target_absolute, backup_absolute)
	if backup_error != OK:
		return backup_error
	var replace_error := DirAccess.rename_absolute(source_absolute, target_absolute)
	if replace_error != OK:
		var restore_error := DirAccess.rename_absolute(backup_absolute, target_absolute)
		return restore_error if restore_error != OK else replace_error
	DirAccess.remove_absolute(backup_absolute)
	return OK
