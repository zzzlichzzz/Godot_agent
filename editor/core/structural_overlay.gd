extends SceneTree
# Primitive SDK observer in an exclusive engine overlay, not a project executor.
func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var action: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var kind := str(action.get("action", ""))
	var filename := "agent_scene_executor.gd"
	if kind == "edit_resource": filename = "resource_observer.gd"
	elif kind == "edit_project_settings": filename = "agent_project_settings_executor.gd"
	var executor = load("res://_t1_overlay/" + filename).new()
	var plugin := EditorPlugin.new()
	var filesystem := plugin.get_editor_interface().get_resource_filesystem()
	await process_frame
	await process_frame
	var deadline := Time.get_ticks_msec() + 15000
	while filesystem.is_scanning() and Time.get_ticks_msec() < deadline:
		await process_frame
	executor.configure(plugin)
	var target := str(action.get("resource", action.get("scene", "res://project.godot")))
	var expected := ""
	if FileAccess.file_exists(target):
		var file := FileAccess.open(target, FileAccess.READ)
		var context := HashingContext.new()
		context.start(HashingContext.HASH_SHA256)
		context.update(file.get_buffer(file.get_length()))
		expected = context.finish().hex_encode()
		file.close()
	var preview: Dictionary = executor.prepare(action, expected)
	var result: Dictionary = {}
	if preview.get("ok", false):
		action["_expected_semantic_hash"] = str(preview.get("semantic_hash", ""))
		action["_expected_dependency_fingerprint"] = str(preview.get("dependency_fingerprint", ""))
		result = executor.execute(action, expected)
		if result.get("ok", false) and kind == "create_scene":
			var staged := target + ".agent-create-" + str(action["_create_action_id"]) + ".tmp.tscn"
			DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(target.get_base_dir()))
			if DirAccess.rename_absolute(ProjectSettings.globalize_path(staged), ProjectSettings.globalize_path(target)) != OK:
				result = {"ok": false, "code": "overlay_publish_failed"}
	else:
		result = preview.duplicate(true)
	var report := {"preview": preview, "result": result, "editor_hint": Engine.is_editor_hint(), "editor_interface": true}
	if kind == "edit_resource": report["published_raw"] = Marshalls.raw_to_base64(executor.published_raw)
	var response := FileAccess.open(args[1], FileAccess.WRITE)
	response.store_string(JSON.stringify(report))
	response.close()
	executor = null
	plugin.free()
	quit(0)
