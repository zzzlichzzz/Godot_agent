extends Node

const NAMESPACE := "godot_agent_runtime"
const PROTOCOL := 1
const MAX_TREE_NODES := 256
const MAX_TREE_DEPTH := 12
const MAX_PROPERTIES := 32
const MAX_EVENTS := 100
const MAX_SAFE_VALUES := 512
const MAX_SAFE_CHARS := 65536
const MAX_SNAPSHOT_BYTES := 64 * 1024

var _enabled := false
var _events: Array[Dictionary] = []
var _errors: Array[Dictionary] = []


func _enter_tree() -> void:
	_enabled = OS.is_debug_build() and EngineDebugger.is_active()
	if not _enabled:
		return
	EngineDebugger.register_message_capture(NAMESPACE, Callable(self, "_capture_message"))
	EngineDebugger.send_message(NAMESPACE + ":ready", [{"protocol": PROTOCOL}])


func _exit_tree() -> void:
	if _enabled and EngineDebugger.is_active():
		EngineDebugger.unregister_message_capture(NAMESPACE)
	_enabled = false


func _capture_message(verb: String, data: Array) -> bool:
	if not _enabled:
		return false
	if verb == "hello":
		EngineDebugger.send_message(NAMESPACE + ":ready", [{"protocol": PROTOCOL}])
		return true
	if verb != "inspect":
		return false
	if data.size() != 1 or not data[0] is Dictionary:
		return true
	var request := data[0] as Dictionary
	var snapshot := _capture_snapshot(request)
	var status := "ok"
	if JSON.stringify(snapshot).to_utf8_buffer().size() > MAX_SNAPSHOT_BYTES:
		status = "response_too_large"
		snapshot = {}
	EngineDebugger.send_message(NAMESPACE + ":snapshot", [{
		"protocol": PROTOCOL,
		"status": status,
		"request_id": str(request.get("request_id", "")),
		"run_id": str(request.get("run_id", "")),
		"snapshot": snapshot,
	}])
	return true


func emit_event(name: String, payload = null, severity: String = "info") -> void:
	if not _enabled or name.length() > 96 or not severity in ["info", "warning", "error"]:
		return
	_events.append({"id": Time.get_ticks_usec(), "ticks_ms": Time.get_ticks_msec(),
		"frame": Engine.get_process_frames(), "name": name, "severity": severity,
		"payload": _safe_value(payload, 0, [MAX_SAFE_VALUES, 8192])})
	if _events.size() > MAX_EVENTS:
		_events.pop_front()


func report_error(message: String, source: Dictionary = {}, stack: Array = []) -> void:
	if not _enabled:
		return
	_errors.append({"id": Time.get_ticks_usec(), "ticks_ms": Time.get_ticks_msec(),
		"severity": "error", "message": message.left(2048),
		"source": _safe_value(source, 0, [MAX_SAFE_VALUES, 4096]),
		"stack": _safe_value(stack.slice(0, 16), 0, [MAX_SAFE_VALUES, 8192])})
	if _errors.size() > MAX_EVENTS:
		_errors.pop_front()


func _capture_snapshot(request: Dictionary) -> Dictionary:
	var sections: Array = request.get("sections", [])
	var root := get_tree().current_scene
	var out := {"protocol": PROTOCOL, "captured_at_ticks_ms": Time.get_ticks_msec()}
	var safe_budget := [MAX_SAFE_VALUES, MAX_SAFE_CHARS]
	if "active_scene" in sections:
		out["active_scene"] = _node_summary(root, ".", 0) if root else null
	if "tree" in sections:
		out["tree"] = _capture_tree(root)
	if "properties" in sections:
		out["properties"] = _capture_properties(root, request.get("properties", []), safe_budget)
	if "errors" in sections:
		out["errors"] = {"items": _safe_value(_errors.slice(maxi(0, _errors.size() - 25)), 0, safe_budget), "dropped": maxi(0, _errors.size() - 25), "source": "custom_bridge"}
	if "events" in sections:
		out["events"] = {"items": _safe_value(_events.slice(maxi(0, _events.size() - 25)), 0, safe_budget), "dropped": maxi(0, _events.size() - 25)}
	if "metrics" in sections:
		out["metrics"] = _capture_metrics()
	return out


func _capture_tree(root: Node) -> Dictionary:
	var nodes: Array = []
	var reasons: Array[String] = []
	if root:
		_walk_tree(root, root, 0, nodes, reasons)
	return {"nodes": nodes, "truncated": not reasons.is_empty(), "truncation_reasons": reasons}


func _walk_tree(node: Node, root: Node, depth: int, out: Array, reasons: Array[String]) -> void:
	if out.size() >= MAX_TREE_NODES:
		if not "node_limit" in reasons: reasons.append("node_limit")
		return
	if depth > MAX_TREE_DEPTH:
		if not "depth_limit" in reasons: reasons.append("depth_limit")
		return
	var path := "." if node == root else str(root.get_path_to(node))
	out.append(_node_summary(node, path, depth))
	var children := node.get_children(false)
	if children.size() > 64 and not "children_limit" in reasons:
		reasons.append("children_limit")
	for child in children.slice(0, 64):
		_walk_tree(child, root, depth + 1, out, reasons)


func _node_summary(node: Node, path: String, depth: int) -> Dictionary:
	var script_path := ""
	var script = node.get_script()
	if script is Script:
		script_path = script.resource_path
	return {"path": path, "name": node.name, "type": node.get_class(), "script": script_path,
		"scene_file_path": node.scene_file_path, "depth": depth, "child_count": node.get_child_count(false)}


func _capture_properties(root: Node, selectors: Array, safe_budget: Array) -> Array:
	var out: Array = []
	if root == null:
		return out
	for selector in selectors:
		if not selector is Dictionary:
			continue
		var path := str(selector.get("node", ""))
		var node := root if path == "." else root.get_node_or_null(NodePath(path))
		for property_name in selector.get("names", []):
			if out.size() >= MAX_PROPERTIES:
				return out
			out.append(_read_property(node, path, str(property_name), safe_budget))
	return out


func _read_property(node: Node, path: String, property_name: String, safe_budget: Array) -> Dictionary:
	if node == null:
		return {"node": path, "name": property_name, "ok": false, "error": "node_not_found"}
	var declared_type := TYPE_NIL
	var found := false
	# ClassDB avoids project-defined _get_property_list() and dynamic _get().
	for info in ClassDB.class_get_property_list(node.get_class()):
		if str(info.get("name", "")) == property_name:
			declared_type = int(info.get("type", TYPE_NIL))
			found = true
			break
	if not found:
		return {"node": path, "name": property_name, "ok": false, "error": "property_not_found"}
	if declared_type in [TYPE_OBJECT, TYPE_CALLABLE, TYPE_SIGNAL, TYPE_RID]:
		return {"node": path, "name": property_name, "ok": false, "error": "unsafe_property_type"}
	return {"node": path, "name": property_name, "ok": true,
		"value": _safe_value(node.get(property_name), 0, safe_budget)}


func _capture_metrics() -> Dictionary:
	return {"fps": Performance.get_monitor(Performance.TIME_FPS),
		"process_seconds": Performance.get_monitor(Performance.TIME_PROCESS),
		"physics_process_seconds": Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS),
		"node_count": Performance.get_monitor(Performance.OBJECT_NODE_COUNT),
		"orphan_node_count": Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT),
		"render_objects": Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME),
		"render_primitives": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),
		"draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)}


func _safe_value(value, depth: int, budget: Array):
	if budget[0] <= 0 or budget[1] <= 0:
		return "<value budget limit>"
	budget[0] -= 1
	if depth > 4:
		return "<depth limit>"
	if value == null or value is bool or value is int or value is float:
		return value
	if value is String or value is StringName or value is NodePath:
		var text := str(value).left(mini(2048, budget[1]))
		budget[1] -= text.length()
		return text
	if value is Vector2 or value is Vector2i:
		return {"type": type_string(typeof(value)), "value": [value.x, value.y]}
	if value is Vector3 or value is Vector3i:
		return {"type": type_string(typeof(value)), "value": [value.x, value.y, value.z]}
	if value is Color:
		return {"type": "Color", "value": [value.r, value.g, value.b, value.a]}
	if value is Array:
		var arr: Array = []
		for item in value.slice(0, 64): arr.append(_safe_value(item, depth + 1, budget))
		return arr
	if value is Dictionary:
		var out := {}
		for key in value.keys().slice(0, 32): out[str(key).left(96)] = _safe_value(value[key], depth + 1, budget)
		return out
	return "<unsupported>"
