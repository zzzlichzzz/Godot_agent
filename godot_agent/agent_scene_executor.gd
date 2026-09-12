@tool
extends RefCounted

# Executes the normalized edit_scene protocol on Godot's main editor thread.
# Python validates JSON and coordinates history; only Godot touches PackedScene.

var _plugin: EditorPlugin


func configure(plugin: EditorPlugin) -> void:
	_plugin = plugin


func prepare(action: Dictionary, expected_hash: String) -> Dictionary:
	var target := _open_target(action, expected_hash, true)
	if not bool(target.get("ok", false)):
		return target
	var root := target.get("root") as Node
	var changes: Array[String] = []
	var applied := _apply_operations(root, action.get("operations", []), changes)
	var semantic_hash := _semantic_hash(root, action.get("operations", [])) if bool(applied.get("ok", false)) else ""
	if root and bool(target.get("detached", false)):
		root.free()
	if not bool(applied.get("ok", false)):
		return applied
	return {"ok": true, "mode": target.get("mode", "closed"), "changes": changes,
		"semantic_hash": semantic_hash}


func execute(action: Dictionary, expected_hash: String) -> Dictionary:
	var target := _open_target(action, expected_hash, false)
	if not bool(target.get("ok", false)):
		return _with_hash(target, str(action.get("scene", "")))
	var root := target.get("root") as Node
	var changes: Array[String] = []
	var applied := _apply_operations(root, action.get("operations", []), changes)
	if not bool(applied.get("ok", false)):
		if root and bool(target.get("detached", false)):
			root.free()
		elif not bool(target.get("detached", false)):
			# Validation was already performed on a detached copy, but the live
			# editor tree can still diverge without changing the disk hash.
			# Never leave a partially mutated active scene after such a failure.
			reload_after_recovery(str(action.get("scene", "")))
		return _with_hash(applied, str(action.get("scene", "")))
	var semantic_hash := _semantic_hash(root, action.get("operations", []))
	var expected_semantic_hash := str(action.get("_expected_semantic_hash", ""))
	if expected_semantic_hash != "" and semantic_hash != expected_semantic_hash:
		if root and bool(target.get("detached", false)):
			root.free()
		elif not bool(target.get("detached", false)):
			reload_after_recovery(str(action.get("scene", "")))
		return _with_hash(_fail("preview_mismatch", "Результат больше не совпадает с подтверждённым предпросмотром"), str(action.get("scene", "")))
	var scene_path := str(action.get("scene", ""))
	var save_error := OK
	if bool(target.get("detached", false)):
		var packed := PackedScene.new()
		save_error = packed.pack(root)
		if save_error == OK:
			save_error = ResourceSaver.save(packed, scene_path)
		root.free()
	else:
		var editor := _editor_interface()
		if editor == null or not editor.has_method("save_scene"):
			return _with_hash(_fail("editor_api_unsupported", "Godot не предоставляет save_scene"), scene_path)
		if editor.has_method("mark_scene_as_unsaved"):
			editor.call("mark_scene_as_unsaved")
		var result = editor.call("save_scene")
		if result is int:
			save_error = int(result)
	if save_error != OK:
		return _with_hash(_fail("save_failed", "Godot не смог сохранить сцену: %s" % error_string(save_error)), scene_path)
	return {"ok": true, "mode": target.get("mode", "closed"), "changes": changes,
		"scene_hash": _file_hash(scene_path)}


func reload_after_recovery(scene_path: String) -> void:
	var editor := _editor_interface()
	if editor and scene_path in Array(editor.get_open_scenes()):
		editor.reload_scene_from_path(scene_path)


func _editor_interface() -> EditorInterface:
	return _plugin.get_editor_interface() if _plugin else null


func _open_target(action: Dictionary, expected_hash: String, for_preview: bool) -> Dictionary:
	var scene_path := str(action.get("scene", ""))
	if not scene_path.begins_with("res://") or not scene_path.to_lower().ends_with(".tscn"):
		return _fail("scene_path", "Godot executor принимает только res://*.tscn")
	if scene_path == "" or not FileAccess.file_exists(scene_path):
		return _fail("scene_missing", "Сцена не найдена: " + scene_path)
	if _file_hash(scene_path) != expected_hash:
		return _fail("stale_scene", "Сцена изменилась после подготовки действия")
	var editor := _editor_interface()
	if editor == null:
		return _fail("editor_unavailable", "EditorInterface недоступен")
	var open_scenes := Array(editor.get_open_scenes())
	var active := editor.get_edited_scene_root()
	var active_path := str(active.scene_file_path) if active else ""
	if scene_path in open_scenes and active_path != scene_path:
		return _fail("scene_open_inactive", "Сцена открыта в другой вкладке; сделайте её активной или закройте")
	if active_path == scene_path:
		if editor.is_playing_scene():
			return _fail("game_running", "Остановите запущенную игру перед изменением активной сцены")
		if editor.has_method("get_unsaved_scenes"):
			var unsaved = editor.call("get_unsaved_scenes")
			if unsaved is PackedStringArray or unsaved is Array:
				if scene_path in Array(unsaved):
					return _fail("scene_dirty", "Сначала сохраните активную сцену")
		elif editor.has_method("is_scene_unsaved"):
			if bool(editor.call("is_scene_unsaved")):
				return _fail("scene_dirty", "Сначала сохраните активную сцену")
		else:
			return _fail("editor_api_unsupported", "Эта версия Godot не позволяет надёжно проверить несохранённую сцену")
		if for_preview:
			return _load_detached(scene_path, "active")
		return {"ok": true, "root": active, "detached": false, "mode": "active"}
	return _load_detached(scene_path, "closed")


func _load_detached(scene_path: String, mode: String) -> Dictionary:
	var resource = ResourceLoader.load(scene_path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE)
	if not resource is PackedScene:
		return _fail("load_failed", "Ресурс не является PackedScene")
	var root := (resource as PackedScene).instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	if root == null:
		return _fail("instantiate_failed", "Godot не смог инстанцировать сцену")
	return {"ok": true, "root": root, "detached": true, "mode": mode}


func _apply_operations(root: Node, operations: Array, changes: Array[String]) -> Dictionary:
	for index in range(operations.size()):
		var operation = operations[index]
		if not operation is Dictionary:
			return _fail("invalid_operation", "Операция %d не является объектом" % (index + 1))
		var result := _apply_operation(root, operation as Dictionary)
		if not bool(result.get("ok", false)):
			result["operation_index"] = index + 1
			return result
		changes.append(str(result.get("summary", operation.get("op", ""))))
	var packed := PackedScene.new()
	var pack_error := packed.pack(root)
	if pack_error != OK:
		return _fail("pack_failed", "PackedScene.pack отклонил результат: %s" % error_string(pack_error))
	return {"ok": true}


func _apply_operation(root: Node, operation: Dictionary) -> Dictionary:
	match str(operation.get("op", "")):
		"add_node":
			return _add_node(root, operation)
		"set_node_property":
			return _set_node_property(root, operation)
		"attach_script":
			return _attach_script(root, operation)
		"connect_signal":
			return _connect_signal(root, operation)
		"reparent_node":
			return _reparent_node(root, operation)
	return _fail("unknown_operation", "Неизвестная структурная операция")


func _node(root: Node, path: String) -> Node:
	if path == ".":
		return root
	return root.get_node_or_null(NodePath(path))


func _is_local(root: Node, node: Node) -> bool:
	return node == root or node.owner == root


func _add_node(root: Node, operation: Dictionary) -> Dictionary:
	var parent := _node(root, str(operation.get("parent", "")))
	if parent == null or not _is_local(root, parent):
		return _fail("invalid_parent", "Родитель не найден или принадлежит инстанцированной подсцене")
	var name := str(operation.get("name", ""))
	if parent.has_node(NodePath(name)):
		return _fail("node_exists", "Узел уже существует: " + name)
	var class_name := str(operation.get("type", ""))
	if not ClassDB.class_exists(class_name) or not ClassDB.can_instantiate(class_name) or not ClassDB.is_parent_class(class_name, "Node"):
		return _fail("invalid_node_type", "Класс нельзя создать как Node: " + class_name)
	var created = ClassDB.instantiate(class_name)
	if not created is Node:
		return _fail("invalid_node_type", "ClassDB не создал Node")
	var node := created as Node
	node.name = name
	parent.add_child(node)
	node.owner = root
	return {"ok": true, "summary": "Добавлен %s %s" % [class_name, _path(root, node)]}


func _set_node_property(root: Node, operation: Dictionary) -> Dictionary:
	var node := _node(root, str(operation.get("node", "")))
	if node == null or not _is_local(root, node):
		return _fail("node_not_local", "Узел не найден или не принадлежит этой сцене")
	var property_name := str(operation.get("property", ""))
	if property_name in ["owner", "name", "script", "scene_file_path"]:
		return _fail("property_forbidden", "Свойство меняется только специальной операцией: " + property_name)
	var property_info: Dictionary = {}
	for raw_info in node.get_property_list():
		if str(raw_info.get("name", "")) == property_name:
			property_info = raw_info
			break
	if property_info.is_empty() or (int(property_info.get("usage", 0)) & PROPERTY_USAGE_STORAGE) == 0:
		return _fail("property_missing", "Сохраняемое свойство не найдено: " + property_name)
	var decoded := _decode_variant(operation.get("value", {}))
	if not bool(decoded.get("ok", false)):
		return decoded
	var value = decoded.get("value")
	var expected_type := int(property_info.get("type", TYPE_NIL))
	if value != null and typeof(value) != expected_type:
		if expected_type == TYPE_FLOAT and typeof(value) == TYPE_INT:
			value = float(value)
		else:
			return _fail("property_type", "Тип значения не совпадает со свойством %s" % property_name)
	node.set(property_name, value)
	return {"ok": true, "summary": "Изменено %s.%s" % [_path(root, node), property_name]}


func _attach_script(root: Node, operation: Dictionary) -> Dictionary:
	var node := _node(root, str(operation.get("node", "")))
	if node == null or not _is_local(root, node):
		return _fail("node_not_local", "Узел не найден или не принадлежит этой сцене")
	if node.get_script() != null and not bool(operation.get("replace_existing", false)):
		return _fail("script_exists", "У узла уже есть скрипт; replace_existing не разрешён")
	var script_path := str(operation.get("script", ""))
	var script = ResourceLoader.load(script_path, "Script", ResourceLoader.CACHE_MODE_IGNORE)
	if not script is Script:
		return _fail("script_missing", "Скрипт не загружен: " + script_path)
	var base_type := str((script as Script).get_instance_base_type())
	if base_type != "" and node.get_class() != base_type and not ClassDB.is_parent_class(node.get_class(), base_type):
		return _fail("script_base_mismatch", "Скрипт %s несовместим с %s" % [base_type, node.get_class()])
	node.set_script(script)
	return {"ok": true, "summary": "Скрипт %s назначен %s" % [script_path, _path(root, node)]}


func _connect_signal(root: Node, operation: Dictionary) -> Dictionary:
	var source := _node(root, str(operation.get("source", "")))
	var target := _node(root, str(operation.get("target", "")))
	if source == null or target == null or not _is_local(root, source) or not _is_local(root, target):
		return _fail("node_not_local", "Источник или получатель сигнала не принадлежит сцене")
	var signal_name := StringName(str(operation.get("signal", "")))
	var method_name := StringName(str(operation.get("method", "")))
	if not source.has_signal(signal_name):
		return _fail("signal_missing", "Сигнал не найден: " + str(signal_name))
	if not target.has_method(method_name):
		return _fail("method_missing", "Метод получателя не найден: " + str(method_name))
	var callable := Callable(target, method_name)
	if source.is_connected(signal_name, callable):
		return _fail("connection_exists", "Такое подключение сигнала уже существует")
	var error := source.connect(signal_name, callable, Object.CONNECT_PERSIST)
	if error != OK:
		return _fail("connect_failed", "Godot отклонил подключение: " + error_string(error))
	return {"ok": true, "summary": "Подключён %s.%s -> %s.%s" % [
		_path(root, source), signal_name, _path(root, target), method_name]}


func _reparent_node(root: Node, operation: Dictionary) -> Dictionary:
	var node := _node(root, str(operation.get("node", "")))
	var new_parent := _node(root, str(operation.get("new_parent", "")))
	if node == null or new_parent == null or node == root:
		return _fail("reparent_invalid", "Узел или новый родитель не найден")
	if not _is_local(root, node) or not _is_local(root, new_parent) or node.is_ancestor_of(new_parent):
		return _fail("reparent_ownership", "Нельзя менять ownership или создавать цикл")
	if new_parent.has_node(NodePath(str(node.name))):
		return _fail("node_exists", "У нового родителя уже есть узел с таким именем")
	var old_path := _path(root, node)
	node.reparent(new_parent, bool(operation.get("keep_global_transform", true)))
	node.owner = root
	return {"ok": true, "summary": "Перемещён %s -> %s" % [old_path, _path(root, node)]}


func _decode_variant(tagged) -> Dictionary:
	if not tagged is Dictionary:
		return _fail("value_schema", "Значение свойства не является tagged object")
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
	return _fail("value_type", "Неподдерживаемый tagged Variant: " + kind)


func _path(root: Node, node: Node) -> String:
	return "." if node == root else str(root.get_path_to(node))


func _semantic_hash(root: Node, operations: Array) -> String:
	var rows: Array[String] = []
	_collect_semantic_rows(root, root, rows)
	for operation in operations:
		if operation is Dictionary and str(operation.get("op", "")) == "set_node_property":
			var node := _node(root, str(operation.get("node", "")))
			var property_name := str(operation.get("property", ""))
			if node:
				rows.append("property|%s|%s|%s" % [
					_path(root, node), property_name, var_to_str(node.get(property_name))])
	rows.sort()
	return HashingContext.hash(HashingContext.HASH_SHA256, "\n".join(rows).to_utf8_buffer()).hex_encode()


func _collect_semantic_rows(root: Node, node: Node, rows: Array[String]) -> void:
	if _is_local(root, node):
		var script_path := ""
		var script = node.get_script()
		if script is Script:
			script_path = str((script as Script).resource_path)
		rows.append("node|%s|%s|%s" % [_path(root, node), node.get_class(), script_path])
		for signal_info in node.get_signal_list():
			var signal_name := StringName(str(signal_info.get("name", "")))
			for connection in node.get_signal_connection_list(signal_name):
				var callable = connection.get("callable")
				if callable is Callable and (callable as Callable).get_object() is Node:
					var target := (callable as Callable).get_object() as Node
					if _is_local(root, target):
						rows.append("signal|%s|%s|%s|%s" % [
							_path(root, node), signal_name, _path(root, target),
							(callable as Callable).get_method()])
	for child in node.get_children():
		if child is Node:
			_collect_semantic_rows(root, child as Node, rows)


func _file_hash(path: String) -> String:
	if not FileAccess.file_exists(path):
		return ""
	return HashingContext.hash(HashingContext.HASH_SHA256, FileAccess.get_file_as_bytes(path)).hex_encode()


func _with_hash(result: Dictionary, scene_path: String) -> Dictionary:
	result["scene_hash"] = _file_hash(scene_path)
	return result


func _fail(code: String, message: String) -> Dictionary:
	return {"ok": false, "code": code, "error": message}
