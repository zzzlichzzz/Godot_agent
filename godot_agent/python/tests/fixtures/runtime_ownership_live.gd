extends SceneTree

class PanelProbe:
	extends "res://addon/agent_panel.gd"
	var result_sends := 0
	func _send_pending_runtime_check_result() -> void:
		result_sends += 1

class ViewProbe:
	extends Node
	var messages: Array[String] = []
	func add_system(message: String) -> void:
		messages.append(message)

class DebuggerProbe:
	extends RefCounted
	var dispatches := 0
	func run_check(_request: Dictionary) -> Dictionary:
		dispatches += 1
		return {"ok": true}
	func cancel_pending(_status: String) -> void:
		pass

var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var version := Engine.get_version_info()
	check(version.major == 4 and version.minor == 6 and version.patch == 1, "Requires audited Godot 4.6.1")
	print("AUDITED ENGINE ", version)
	for api in ["EditorInterface", "EditorDebuggerSession", "EditorDebuggerPlugin"]:
		var methods: Array = []
		for info in ClassDB.class_get_method_list(api, true):
			methods.append(str(info.name))
		print(api, " METHODS ", methods)
		print(api, " PROPERTIES ", ClassDB.class_get_property_list(api, true))
		check(not "get_running_project_pids" in methods, api + " PID API changed; revisit refusal")
		check(not "get_remote_pid" in methods, api + " remote PID API changed; revisit refusal")
	# Check all public editor classes, not just guessed method names.
	for api in ClassDB.get_class_list():
		if not str(api).begins_with("Editor"):
			continue
		for info in ClassDB.class_get_method_list(api, true):
			check(not "pid" in str(info.name) and not "process_id" in str(info.name),
				"Review newly exposed editor process API: " + str(api) + "." + str(info.name))
	check(load("res://addon/agent_runtime_debugger.gd").can_instantiate(), "Debugger parses")
	# Non-tool runtime scripts cannot instantiate in the editor; compile instead.
	check(load("res://addon/agent_runtime_bridge.gd").reload() == OK, "Bridge parses")

	var remote := {"session_id": 0, "run_id": "remote", "active": true,
		"bridge_ready": true, "capabilities": ["run_check_v1"]}
	var replacement := remote.duplicate(true)
	replacement["run_id"] = "replacement"
	# Even plausible self-reported scene/PID evidence cannot authenticate a peer.
	var claimed_local := remote.duplicate(true)
	claimed_local.merge({"pid": OS.get_process_id(), "scene": "res://check.tscn"})
	var scenarios: Array = [[], [remote], [replacement], [remote, replacement], [claimed_local]]
	for sessions in scenarios:
		var panel := PanelProbe.new()
		var view := ViewProbe.new()
		var debugger := DebuggerProbe.new()
		panel._view = view
		panel._runtime_debugger = debugger
		panel._runtime_status = {"sessions": sessions}
		panel._start_runtime_check({"runtime_check_request": {
			"scene": "res://check.tscn", "request_id": "request", "result_token": "token"}})
		var body: Dictionary = panel._pending_runtime_check_result_body
		check(body.get("status") == "bridge_unavailable", "Refuse without ownership")
		check(body.get("session_id") == -1 and body.get("run_id") == "", "Never bind a guessed run")
		check(body.get("request_id") == "request" and body.get("result_token") == "token", "Preserve result routing")
		check(panel.result_sends == 1, "Send refusal through existing result transport")
		check(view.messages.size() == 1 and "ownership" in view.messages[0], "Explain refusal visibly")
		panel._execute_bound_runtime_check({"game_request": {"run_id": "replacement"}})
		check(debugger.dispatches == 0, "Late bind must not dispatch input")
		check(panel._pending_runtime_check_result_body.get("status") == "bridge_unavailable", "Late bind refused")
		panel._exit_tree()
		panel._clear_runtime_check_state()
		check(panel._pending_runtime_check.is_empty(), "Cleanup clears pending check")
		panel._execute_bound_runtime_check({"game_request": {}})
		check(panel._pending_runtime_check_result_body.is_empty(), "Late bind after cleanup ignored")
		panel.free()
		view.free()
	check(not EditorInterface.is_playing_scene(), "No game launched")

	var screenshot_probe = load("res://screenshot_probe.gd").new()
	var sizes: Array = [
		[1920, 1080, 480, 270, 480, 270],
		[1080, 1920, 480, 270, 151, 270],
		[1000, 1000, 480, 270, 270, 270],
		[1000, 100, 480, 270, 480, 48],
		[100, 1000, 480, 270, 27, 270],
		[320, 200, 480, 270, 320, 200],
		[1, 1000, 480, 270, 1, 270],
		[1920, 1080, 320, 200, 320, 180],
	]
	for size in sizes:
		screenshot_probe.source_image = Image.create(size[0], size[1], false, Image.FORMAT_RGB8)
		var shot: Dictionary = screenshot_probe._capture_check_screenshot(
			{"when": "always", "max_width": size[2], "max_height": size[3]}, {})
		check(shot.get("ok", false), "Screenshot encoded")
		var decoded := Image.new()
		check(decoded.load_jpg_from_buffer(Marshalls.base64_to_raw(shot.get("data", ""))) == OK, "Valid JPEG")
		check(decoded.get_width() == size[4] and decoded.get_height() == size[5], "Uniform scale: " + str(size))
	print("RUNTIME_OWNERSHIP_RESULTS ", JSON.stringify({"failures": failures,
		"refusals": scenarios.size(), "screenshots": sizes.size(), "api_audit": true}))
	quit(0 if failures.is_empty() else 1)
