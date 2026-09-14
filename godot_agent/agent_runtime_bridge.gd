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
const MAX_CHECK_RESULT_BYTES := 160 * 1024

var _enabled := false
var _events: Array[Dictionary] = []
var _errors: Array[Dictionary] = []
var _error_sequence: int = 0
var _check: Dictionary = {}
var _held_actions: Dictionary = {}


func _enter_tree() -> void:
	_enabled = OS.is_debug_build() and EngineDebugger.is_active()
	if not _enabled:
		return
	EngineDebugger.register_message_capture(NAMESPACE, Callable(self, "_capture_message"))
	EngineDebugger.send_message(NAMESPACE + ":ready", [{"protocol": PROTOCOL,
		"capabilities": ["inspect_v1", "run_check_v1"]}])
	set_process(true)


func _exit_tree() -> void:
	if _enabled and EngineDebugger.is_active():
		EngineDebugger.unregister_message_capture(NAMESPACE)
	_release_inputs()
	_enabled = false


func _capture_message(verb: String, data: Array) -> bool:
	if not _enabled:
		return false
	if verb == "hello":
		EngineDebugger.send_message(NAMESPACE + ":ready", [{"protocol": PROTOCOL,
			"capabilities": ["inspect_v1", "run_check_v1"]}])
		return true
	if verb == "cancel_check":
		_finish_check("cancelled")
		return true
	if verb == "run_check":
		if data.size() != 1 or not data[0] is Dictionary or not _check.is_empty():
			return true
		_start_check(data[0] as Dictionary)
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


func _process(_delta: float) -> void:
	if _check.is_empty():
		return
	if Time.get_ticks_msec() > int(_check.get("deadline", 0)):
		_finish_check("timeout")
		return
	if int(_check.get("wait_frames", 0)) > 0:
		_check["wait_frames"] = int(_check["wait_frames"]) - 1
		return
	if Time.get_ticks_msec() < int(_check.get("wait_until", 0)):
		return
	_run_check_steps()


func _start_check(request: Dictionary) -> void:
	_check = {"request": request.duplicate(true), "step": 0, "assertions": [],
		"step_errors": [],
		"error_cursor": _error_sequence,
		"started": Time.get_ticks_msec(),
		"deadline": Time.get_ticks_msec() + clampi(int(request.get("timeout_ms", 12000)), 1000, 20000),
		"wait_frames": 0, "wait_until": 0}
	_run_check_steps()


func _run_check_steps() -> void:
	while not _check.is_empty():
		var request: Dictionary = _check["request"]
		var steps: Array = request.get("steps", [])
		var cursor := int(_check["step"])
		if cursor >= steps.size():
			_finish_check("ok")
			return
		var step = steps[cursor]
		if not step is Dictionary:
			_finish_check("protocol_error")
			return
		_check["step"] = cursor + 1
		var op := str(step.get("op", ""))
		if op == "wait_frames":
			_check["wait_frames"] = clampi(int(step.get("frames", 1)), 1, 600)
			return
		if op == "wait_time":
			_check["wait_until"] = Time.get_ticks_msec() + clampi(int(step.get("ms", 1)), 1, 5000)
			return
		if op == "input_action":
			_apply_input(step)
			continue
		if op.begins_with("assert_"):
			(_check["assertions"] as Array).append(_evaluate_assertion(step))
			continue
		_finish_check("protocol_error")
		return


func _apply_input(step: Dictionary) -> void:
	var action := str(step.get("name", ""))
	if not InputMap.has_action(action):
		(_check["step_errors"] as Array).append({"index": int(step.get("index", -1)),
			"message": "InputMap action not found: " + action})
		return
	var event := InputEventAction.new()
	event.action = action
	event.pressed = bool(step.get("pressed", false))
	event.strength = float(step.get("strength", 1.0 if event.pressed else 0.0))
	Input.parse_input_event(event)
	if event.pressed:
		_held_actions[action] = true
	else:
		_held_actions.erase(action)


func _evaluate_assertion(step: Dictionary) -> Dictionary:
	var index := int(step.get("index", -1))
	var op := str(step.get("op", ""))
	var result := {"index": index, "op": op}
	if op == "assert_no_errors":
		result["actual"] = _errors_since(int(_check.get("error_cursor", 0))).is_empty()
		return result
	var root := get_tree().current_scene
	var path := str(step.get("node", ""))
	var node := root if root and path == "." else (root.get_node_or_null(NodePath(path)) if root else null)
	if op == "assert_node":
		result["actual"] = node != null
		return result
	if op == "assert_property":
		var property_name := str(step.get("property", ""))
		var read := _read_native_property(node, property_name, [MAX_SAFE_VALUES, 8192])
		result["read_ok"] = bool(read.get("ok", false))
		if result["read_ok"]:
			result["actual"] = read.get("value")
		else:
			result["error"] = str(read.get("error", "property_unavailable"))
	return result


func _errors_since(sequence: int) -> Array:
	var result: Array = []
	for item in _errors:
		if int(item.get("sequence", 0)) > sequence:
			result.append(item)
	return result


func _read_native_property(node: Node, property_name: String, safe_budget: Array) -> Dictionary:
	if node == null:
		return {"ok": false, "error": "node_not_found"}
	var declared_type := TYPE_NIL
	var found := false
	for info in ClassDB.class_get_property_list(node.get_class()):
		if str(info.get("name", "")) == property_name:
			declared_type = int(info.get("type", TYPE_NIL))
			found = true
			break
	if not found:
		return {"ok": false, "error": "property_not_found"}
	if declared_type in [TYPE_OBJECT, TYPE_CALLABLE, TYPE_SIGNAL, TYPE_RID]:
		return {"ok": false, "error": "unsafe_property_type"}
	return {"ok": true, "value": _safe_value(node.get(property_name), 0, safe_budget)}


func _finish_check(status: String) -> void:
	if _check.is_empty():
		return
	var request: Dictionary = _check.get("request", {})
	var check_errors: Array = []
	var error_cursor := int(_check.get("error_cursor", _error_sequence))
	for item in _errors:
		if int(item.get("sequence", 0)) > error_cursor:
			check_errors.append(item)
	var result := {"protocol": PROTOCOL,
		"scene": get_tree().current_scene.scene_file_path if get_tree().current_scene else "",
		"duration_ms": Time.get_ticks_msec() - int(_check.get("started", Time.get_ticks_msec())),
		"assertions": _check.get("assertions", []),
		"step_errors": _check.get("step_errors", []),
		"bridge_errors": check_errors}
	if status == "ok":
		var screenshot_options: Dictionary = request.get("screenshot", {})
		# Failure-only screenshots are captured eagerly under the same strict
		# size limits; the server recomputes the outcome and discards them on pass.
		if str(screenshot_options.get("when", "never")) != "never":
			result["screenshot"] = _capture_check_screenshot(screenshot_options, result)
	if JSON.stringify(result).to_utf8_buffer().size() > MAX_CHECK_RESULT_BYTES:
		# A screenshot is optional evidence. Drop it first rather than sending an
		# oversized debugger message; the server will still verify all assertions.
		result["screenshot"] = {"ok": false, "data": "", "error": "response_too_large"}
	if JSON.stringify(result).to_utf8_buffer().size() > MAX_CHECK_RESULT_BYTES:
		status = "response_too_large"
		result = {}
	EngineDebugger.send_message(NAMESPACE + ":check_result", [{"protocol": PROTOCOL,
		"status": status, "request_id": str(request.get("request_id", "")),
		"run_id": str(request.get("run_id", "")), "result": result}])
	_release_inputs()
	_check = {}


func _capture_check_screenshot(options: Dictionary, _result: Dictionary) -> Dictionary:
	if str(options.get("when", "never")) == "never":
		return {"ok": false, "error": "not_requested"}
	var image := get_viewport().get_texture().get_image()
	if image == null or image.is_empty():
		return {"ok": false, "error": "capture_failed"}
	var max_width := clampi(int(options.get("max_width", 480)), 64, 480)
	var max_height := clampi(int(options.get("max_height", 270)), 64, 270)
	if image.get_width() > max_width or image.get_height() > max_height:
		image.resize(max_width, max_height, Image.INTERPOLATE_LANCZOS)
	return {"ok": true, "data": Marshalls.raw_to_base64(
		image.save_jpg_to_buffer(clampf(float(options.get("quality", 0.65)), 0.4, 0.8)))}


func _release_inputs() -> void:
	for action in _held_actions.keys():
		var event := InputEventAction.new()
		event.action = str(action)
		event.pressed = false
		event.strength = 0.0
		Input.parse_input_event(event)
	_held_actions.clear()


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
	_error_sequence += 1
	_errors.append({"id": Time.get_ticks_usec(), "sequence": _error_sequence,
		"ticks_ms": Time.get_ticks_msec(),
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
