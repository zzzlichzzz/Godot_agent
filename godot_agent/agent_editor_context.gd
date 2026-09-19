@tool
extends RefCounted

const SCHEMA_VERSION := 1
const MAX_OPEN_SCENES := 12
const MAX_OPEN_SCRIPTS := 12
const MAX_SELECTED_NODES := 8
const MAX_GROUPS := 8
const MAX_CODE_CHARS := 6000
const CARET_RADIUS := 24
const PROPERTY_NAMES := {
	"position": true,
	"rotation": true,
	"rotation_degrees": true,
	"scale": true,
	"size": true,
	"visible": true,
	"z_index": true,
	"process_mode": true,
	"disabled": true,
	"monitoring": true,
	"collision_layer": true,
	"collision_mask": true,
}


static func capture() -> Dictionary:
	var snapshot := {"schema_version": SCHEMA_VERSION}
	_put_nonempty(snapshot, "scene", _capture_scenes())
	var root := EditorInterface.get_edited_scene_root()
	_put_nonempty(snapshot, "selection", _capture_selection(root))
	_put_nonempty(snapshot, "script", _capture_script())
	snapshot["run"] = {"playing": EditorInterface.is_playing_scene()}
	return snapshot


static func _capture_scenes() -> Dictionary:
	var result := {}
	var root := EditorInterface.get_edited_scene_root()
	if root != null:
		var active_path := str(root.scene_file_path)
		if active_path.begins_with("res://"):
			result["active"] = active_path
		else:
			result["unsaved"] = true
	var open_scenes := []
	for raw_path in EditorInterface.get_open_scenes():
		var path := str(raw_path)
		if path.begins_with("res://"):
			open_scenes.append(path)
			if open_scenes.size() >= MAX_OPEN_SCENES:
				break
	if not open_scenes.is_empty():
		result["open"] = open_scenes
	return result


static func _capture_selection(root: Node) -> Dictionary:
	var editor_selection := EditorInterface.get_selection()
	if editor_selection == null:
		return {}
	var nodes := []
	for selected in editor_selection.get_selected_nodes():
		var node := selected as Node
		if node == null:
			continue
		var item := {
			"path": _node_path(root, node),
			"type": node.get_class(),
		}
		var script = node.get_script()
		if script is Script and str(script.resource_path).begins_with("res://"):
			item["script"] = str(script.resource_path)
		if node.owner != null:
			item["owner"] = _node_path(root, node.owner)
		var groups := []
		for raw_group in node.get_groups():
			groups.append(str(raw_group))
			if groups.size() >= MAX_GROUPS:
				break
		if not groups.is_empty():
			item["groups"] = groups
		var properties := _capture_properties(node)
		if not properties.is_empty():
			item["properties"] = properties
		nodes.append(item)
		if nodes.size() >= MAX_SELECTED_NODES:
			break
	return {"nodes": nodes} if not nodes.is_empty() else {}


static func _capture_properties(node: Node) -> Dictionary:
	var properties := {}
	for info in node.get_property_list():
		var name := str(info.get("name", ""))
		if not PROPERTY_NAMES.has(name):
			continue
		var value = _json_safe(node.get(name))
		if value != null:
			properties[name] = value
	return properties


static func _capture_script() -> Dictionary:
	var script_editor := EditorInterface.get_script_editor()
	if script_editor == null:
		return {}
	var result := {}
	var current_script := script_editor.get_current_script()
	if current_script is Script and str(current_script.resource_path).begins_with("res://"):
		result["path"] = str(current_script.resource_path)
	var open_scripts := []
	for script in script_editor.get_open_scripts():
		if script is Script:
			var path := str(script.resource_path)
			if path.begins_with("res://"):
				open_scripts.append(path)
				if open_scripts.size() >= MAX_OPEN_SCRIPTS:
					break
	if not open_scripts.is_empty():
		result["open"] = open_scripts
	var current_editor := script_editor.get_current_editor()
	if current_editor == null:
		return result
	var code_edit := current_editor.get_base_editor() as CodeEdit
	if code_edit == null:
		return result
	var caret_line := code_edit.get_caret_line()
	result["caret"] = {
		"line": caret_line + 1,
		"column": code_edit.get_caret_column() + 1,
	}
	result["dirty"] = code_edit.get_version() != code_edit.get_saved_version()
	if code_edit.has_selection() and code_edit.has_method("get_selection_from_line"):
		var selected_text := code_edit.get_selected_text()
		var selection_from_line := code_edit.get_selection_from_line()
		var selection_from_column := code_edit.get_selection_from_column()
		var selection_to_line := code_edit.get_selection_to_line()
		var selection_to_column := code_edit.get_selection_to_column()
		result["selection"] = {
			"from_line": selection_from_line + 1,
			"from_column": selection_from_column + 1,
			"to_line": selection_to_line + 1,
			"to_column": selection_to_column + 1,
			"text": _limit_text(selected_text),
		}
	else:
		var first_line := maxi(0, caret_line - CARET_RADIUS)
		var last_line := mini(code_edit.get_line_count() - 1, caret_line + CARET_RADIUS)
		var lines := PackedStringArray()
		for line_index in range(first_line, last_line + 1):
			lines.append(code_edit.get_line(line_index))
		result["caret_context"] = {
			"start_line": first_line + 1,
			"end_line": last_line + 1,
			"text": _limit_text("\n".join(lines)),
		}
	return result


static func _node_path(root: Node, node: Node) -> String:
	if root == null or node == null:
		return str(node.name) if node != null else ""
	if root == node:
		return str(root.name)
	if root.is_ancestor_of(node):
		return str(root.name) + "/" + str(root.get_path_to(node))
	return str(node.get_path())


static func _json_safe(value: Variant) -> Variant:
	match typeof(value):
		TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING:
			return value
		TYPE_STRING_NAME, TYPE_NODE_PATH:
			return str(value)
		TYPE_VECTOR2, TYPE_VECTOR2I, TYPE_VECTOR3, TYPE_VECTOR3I, TYPE_VECTOR4, TYPE_VECTOR4I, TYPE_COLOR:
			return str(value)
	return null


static func _limit_text(text: String) -> String:
	if text.length() <= MAX_CODE_CHARS:
		return text
	return text.left(MAX_CODE_CHARS) + "\n[context truncated]"


static func _put_nonempty(target: Dictionary, key: String, value: Dictionary) -> void:
	if not value.is_empty():
		target[key] = value
