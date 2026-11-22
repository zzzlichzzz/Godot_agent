# editor/bridge/verbs/editors/context_snapshot.gd - статический снимок редактора:
# открытые сцены, выделение, свойства, скрипт (из agent_editor_context.gd).
# Снимок: читаются только готовые поля редактора (`EditorInterface`), разбора
# `.tscn`/`.gd` здесь нет (R-14). Поля названы как в `result_schema` словаря.
# `revision`/`dirty` ведёт счётчик моста: сигналы редактора подключаются в части B
# (`editor_hooks.gd`), а в части A это значения по умолчанию (живой прогон -
# харнесс `needs_live`, приёмкой не считается).
@tool
extends RefCounted

const MAX_PROPERTIES := 50
const MAX_TEXT := 200

static var _start_ms := Time.get_ticks_msec()
static var _revisions: Dictionary = {}
static var _dirty: Dictionary = {}


static func uptime_s() -> float:
	return float(Time.get_ticks_msec() - _start_ms) / 1000.0


static func has_editor() -> bool:
	# Хост без редактора (`--headless -s`, харнесс `needs_live`) отдаёт заглушку
	# `EditorInterface`: синглтон есть, но у него нет ни одного метода редактора -
	# даже `has_method` («Nonexistent function 'get_current_path'», живой прогон A.1).
	# `ClassDB` признаком не годится: метаданные класса есть в обоих режимах
	# (в 4.6 — 71 метод). Поэтому признак один: мы внутри редактора.
	if not Engine.is_editor_hint():
		return false
	return EditorInterface != null and EditorInterface.has_method("get_open_scenes")


static func project_hash() -> String:
	return ProjectSettings.globalize_path("res://").md5_text()


static func mark_changed(path: String, is_dirty: bool) -> void:
	if is_dirty and not bool(_dirty.get(path, false)):
		_revisions[path] = int(_revisions.get(path, 0)) + 1
	_dirty[path] = is_dirty


static func revision_of(path: String) -> int:
	# Ревизия сцены: та же, что отдаёт `editor_state`, — на неё опирается
	# `expected_revision` батча (`scene_executor.gd`).
	return int(_revisions.get(path, 0))


static func bump(path: String) -> void:
	# Один применённый батч - одна ревизия, независимо от числа операций.
	_revisions[path] = int(_revisions.get(path, 0)) + 1
	# Сцена изменена: `dirty` читается клиентом как «есть несохранённое».
	_dirty[path] = true


static func scenes() -> Array:
	var out: Array = []
	if not has_editor():
		return out
	var active := EditorInterface.get_current_path()
	for item in EditorInterface.get_open_scenes():
		var path := str(item)
		var dirty := bool(_dirty.get(path, false))
		out.append({"path": path,
			"revision": int(_revisions.get(path, 0)),
			"dirty": dirty,
			"active": path == active,
			"unsaved_changes": 1 if dirty else 0})
	return out


static func state() -> Dictionary:
	if not has_editor():
		return {"open_scenes": [], "active_scene": null,
			"project_hash": project_hash()}
	var active := EditorInterface.get_current_path()
	return {"open_scenes": scenes(),
		"active_scene": null if active.is_empty() else active,
		"project_hash": project_hash()}


static func selection() -> Dictionary:
	if not has_editor():
		return {"node_path": null, "scene": null, "properties": [], "script": null}
	var nodes := EditorInterface.get_selection().get_selected_nodes()
	if nodes.is_empty():
		return {"node_path": null, "scene": null, "properties": [], "script": null}
	var node: Node = nodes[0]
	var root := EditorInterface.get_edited_scene_root()
	var scene: Variant = root.scene_file_path if root != null else null
	return {"node_path": _node_path(node, root),
		"scene": null if scene == null or scene.is_empty() else scene,
		"properties": _properties(node),
		"script": _script(node)}


static func _node_path(node: Node, root: Node) -> String:
	if root == null or node == root:
		return "/root/%s" % (node.name if root == null else root.name)
	return "/root/%s/%s" % [root.name, str(root.get_path_to(node))]


static func _script(node: Node) -> Variant:
	var script = node.get_script()
	if script == null:
		return null
	var path := str(script.resource_path)
	return null if path.is_empty() else path


static func _properties(node: Node) -> Array:
	var out: Array = []
	for info in node.get_property_list():
		if out.size() >= MAX_PROPERTIES:
			break
		var name := str(info.get("name", ""))
		if name.is_empty() or name.begins_with("_") or not (int(info.get("usage", 0)) & PROPERTY_USAGE_EDITOR):
			continue
		out.append({"name": name, "type": type_string(int(info.get("type", TYPE_NIL))),
			"value": _json_safe(node.get(name))})
	return out


static func _json_safe(value: Variant) -> Variant:
	match typeof(value):
		TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT:
			return value
		TYPE_STRING, TYPE_STRING_NAME, TYPE_NODE_PATH:
			var text := str(value)
			return text.substr(0, MAX_TEXT)
		TYPE_VECTOR2, TYPE_VECTOR2I:
			return [value.x, value.y]
		TYPE_VECTOR3, TYPE_VECTOR3I:
			return [value.x, value.y, value.z]
		TYPE_COLOR:
			return [value.r, value.g, value.b, value.a]
		_:
			return str(value).substr(0, MAX_TEXT)
