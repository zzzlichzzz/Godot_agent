@tool
extends EditorDebuggerPlugin

signal status_changed(status: Dictionary)
signal inspect_completed(result: Dictionary)

const NAMESPACE := "godot_agent_runtime"
const PROTOCOL := 1
const MAX_SESSIONS := 8

var _sessions: Dictionary = {}
var _pending: Dictionary = {}


func _has_capture(capture: String) -> bool:
	return capture == NAMESPACE


func _capture(message: String, data: Array, session_id: int) -> bool:
	if message == NAMESPACE + ":ready":
		if data.size() == 1 and data[0] is Dictionary:
			var state: Dictionary = _sessions.get(session_id, {})
			if not state.is_empty() and int((data[0] as Dictionary).get("protocol", 0)) == PROTOCOL:
				state["bridge_ready"] = true
				_sessions[session_id] = state
				status_changed.emit(get_status())
		return true
	if message == NAMESPACE + ":snapshot":
		if data.size() != 1 or not data[0] is Dictionary:
			return true
		var payload := data[0] as Dictionary
		if _pending.is_empty() or int(_pending.get("session_id", -1)) != session_id:
			return true
		if str(payload.get("request_id", "")) != str(_pending.get("request_id", "")):
			return true
		if str(payload.get("run_id", "")) != str(_pending.get("run_id", "")):
			return true
		_pending = {}
		inspect_completed.emit({"status": str(payload.get("status", "protocol_error")), "session_id": session_id,
			"run_id": str(payload.get("run_id", "")), "request_id": str(payload.get("request_id", "")),
			"snapshot": payload.get("snapshot", {})})
		return true
	return false


func _setup_session(session_id: int) -> void:
	var session := get_session(session_id)
	if session == null:
		return
	session.started.connect(_on_session_started.bind(session_id))
	session.stopped.connect(_on_session_stopped.bind(session_id))
	session.breaked.connect(_on_session_breaked.bind(session_id))
	session.continued.connect(_on_session_continued.bind(session_id))
	_sessions[session_id] = {"session_id": session_id, "run_id": "", "active": false,
		"breaked": false, "debuggable": false, "bridge_ready": false}
	var state: Dictionary = _sessions[session_id]
	state["active"] = session.is_active()
	state["breaked"] = session.is_breaked()
	state["debuggable"] = session.is_debuggable()
	if state["active"]:
		state["run_id"] = "%d-%d" % [session_id, Time.get_ticks_usec()]
	_sessions[session_id] = state
	# If the plugin is reloaded after the debug session started, request a fresh handshake.
	session.send_message(NAMESPACE + ":hello", [{"protocol": PROTOCOL}])
	status_changed.emit(get_status())


func get_status() -> Dictionary:
	var items: Array = []
	var ids := _sessions.keys()
	ids.sort()
	for session_id in ids.slice(0, MAX_SESSIONS):
		items.append((_sessions[session_id] as Dictionary).duplicate(true))
	return {"enabled": true, "protocol": PROTOCOL, "sessions": items}


func inspect(request: Dictionary) -> Dictionary:
	if not _pending.is_empty():
		return {"ok": false, "status": "protocol_error", "error": "runtime request already pending"}
	var session_id := int(request.get("session_id", -1))
	var state: Dictionary = _sessions.get(session_id, {})
	var session := get_session(session_id)
	if state.is_empty() or session == null or not bool(state.get("active")):
		return {"ok": false, "status": "runtime_not_running", "error": "runtime session stopped"}
	if not bool(state.get("bridge_ready")):
		return {"ok": false, "status": "bridge_unavailable", "error": "AgentRuntimeBridge is not ready"}
	if str(state.get("run_id", "")) != str(request.get("run_id", "")):
		return {"ok": false, "status": "stale_runtime_session", "error": "runtime run changed"}
	_pending = request.duplicate(true)
	var runtime_request := {}
	for key in ["protocol", "request_id", "run_id", "sections", "properties", "max_age_ms"]:
		runtime_request[key] = request.get(key)
	session.send_message(NAMESPACE + ":inspect", [runtime_request])
	return {"ok": true}


func cancel_pending(status: String = "session_stopped") -> void:
	if _pending.is_empty():
		return
	var request := _pending
	_pending = {}
	inspect_completed.emit({"status": status, "session_id": int(request.get("session_id", -1)),
		"run_id": str(request.get("run_id", "")), "request_id": str(request.get("request_id", "")),
		"snapshot": {}})


func _on_session_started(session_id: int) -> void:
	var state: Dictionary = _sessions.get(session_id, {"session_id": session_id})
	state.merge({"run_id": "%d-%d" % [session_id, Time.get_ticks_usec()], "active": true,
		"breaked": false, "debuggable": true, "bridge_ready": false}, true)
	_sessions[session_id] = state
	var session := get_session(session_id)
	if session:
		session.send_message(NAMESPACE + ":hello", [{"protocol": PROTOCOL}])
	status_changed.emit(get_status())


func _on_session_stopped(session_id: int) -> void:
	var state: Dictionary = _sessions.get(session_id, {"session_id": session_id})
	state.merge({"active": false, "breaked": false, "bridge_ready": false}, true)
	_sessions[session_id] = state
	if int(_pending.get("session_id", -1)) == session_id:
		cancel_pending("session_stopped")
	status_changed.emit(get_status())


func _on_session_breaked(can_debug: bool, session_id: int) -> void:
	var state: Dictionary = _sessions.get(session_id, {})
	state["breaked"] = true
	state["debuggable"] = can_debug
	_sessions[session_id] = state
	status_changed.emit(get_status())


func _on_session_continued(session_id: int) -> void:
	var state: Dictionary = _sessions.get(session_id, {})
	state["breaked"] = false
	_sessions[session_id] = state
	status_changed.emit(get_status())
