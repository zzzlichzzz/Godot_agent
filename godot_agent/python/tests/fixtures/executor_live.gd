extends SceneTree

const SceneExecutor = preload("res://addons/godot_agent/agent_scene_executor.gd")
const SettingsExecutor = preload("res://addons/godot_agent/agent_project_settings_executor.gd")
const ResourceExecutor = preload("res://addons/godot_agent/agent_resource_executor.gd")
const ResourceFaults = preload("res://executor_resource_faults.gd")
var failures: Array[String] = []
var completed: Array[String] = []
var plugin: EditorPlugin
var scene_executor = SceneExecutor.new()
var settings_executor = SettingsExecutor.new()
var resource_executor = ResourceExecutor.new()
var safety_executors: Array = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	await process_frame
	await process_frame
	while EditorInterface.get_resource_filesystem().is_scanning():
		await process_frame
	plugin = EditorPlugin.new()
	scene_executor.configure(plugin)
	settings_executor.configure(plugin)
	resource_executor.configure(plugin)
	var tests := [_replace_probe, _scene, _settings, _resource_property, _theme, _sprite_frames, _animation, _resource_safety]
	if "--replace-probe-only" in OS.get_cmdline_user_args():
		tests = [_replace_probe]
	for test in tests:
		test.call()
		await process_frame
		while EditorInterface.get_resource_filesystem().is_scanning():
			await process_frame
	# Let queued editor previews complete while their receivers are still alive.
	await create_timer(0.5).timeout
	scene_executor = null
	settings_executor = null
	resource_executor = null
	safety_executors.clear()
	plugin.free()
	await process_frame
	await process_frame
	print("GODOT_EXECUTOR_RESULTS " + JSON.stringify({"completed": completed, "failures": failures}))
	quit(0 if failures.is_empty() else 1)


func check(condition: bool, label: String) -> bool:
	if not condition:
		failures.append(label)
		print("FAIL " + label)
	return condition


func success(result: Dictionary, label: String) -> bool:
	return check(bool(result.get("ok", false)), label + ": " + JSON.stringify(result))


func done(name: String) -> void:
	completed.append(name)
	print("CASE_COMPLETED " + name)


func write_bytes(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if check(file != null, "open fixture file " + path):
		file.store_buffer(bytes)
		file.close()


func _replace_probe() -> void:
	var target := ProjectSettings.globalize_path("res://rename-target.bin")
	var source := ProjectSettings.globalize_path("res://rename-source.bin")
	var backup := source + ".backup"
	write_bytes(target, "original".to_utf8_buffer())
	write_bytes(source, "replacement".to_utf8_buffer())
	check(DirAccess.copy_absolute(target, backup) == OK, "non-destructive original copy")
	check(FileAccess.get_file_as_string(target) == "original", "copy leaves original target present")
	var error := DirAccess.rename_absolute(source, target)
	print("RENAME_OVERWRITE_PROBE " + OS.get_name() + " " + error_string(error))
	check(error == OK, "same-directory rename overwrites existing target")
	check(FileAccess.get_file_as_string(target) == "replacement" and not FileAccess.file_exists(source), "rename publishes source bytes and consumes source")
	check(FileAccess.get_file_as_string(backup) == "original", "rename preserves independent original copy")
	check(DirAccess.rename_absolute(backup, target) == OK, "rename restores over published target")
	check(FileAccess.get_file_as_string(target) == "original", "rename restores exact original bytes")
	if OS.get_name() == "Windows":
		write_bytes(source, "locked source".to_utf8_buffer())
		check(DirAccess.copy_absolute(target, backup) == OK, "retain original for locked-source probe")
		var held := FileAccess.open(source, FileAccess.READ)
		if check(held != null, "hold real Windows source handle"):
			var locked_error := DirAccess.rename_absolute(source, target)
			held.close()
			print("RENAME_LOCKED_SOURCE_PROBE " + error_string(locked_error) + " target_exists=" + str(FileAccess.file_exists(target)))
			check(locked_error != OK and FileAccess.file_exists(source), "locked source prevents move")
			# 4.6.1 deletes the destination before this move fails: overwrite is NOT atomic.
			check(FileAccess.get_file_as_string(backup) == "original", "backup survives failed overwrite even if destination was deleted")
			check(DirAccess.rename_absolute(backup, target) == OK, "restore probe original after failed overwrite")
	done("replace_probe")


func _scene() -> void:
	var path := "res://created.tscn"
	var action := {"action": "create_scene", "scene": path,
		"_create_action_id": "0123456789abcdef0123456789abcdef",
		"root": {"type": "Node2D", "name": "Level", "script": "res://executor_receiver.gd"},
		"operations": [
			{"op": "add_node", "parent": ".", "type": "Node2D", "name": "Group"},
			{"op": "add_node", "parent": "Group", "type": "Timer", "name": "Clock"},
			{"op": "set_node_property", "node": ".", "property": "position", "value": {"type": "Vector2", "value": [12, 34]}},
			{"op": "set_node_property", "node": ".", "property": "score", "value": {"type": "int", "value": 9}},
			{"op": "set_node_property", "node": "Group/Clock", "property": "wait_time", "value": {"type": "float", "value": 2.5}},
			{"op": "connect_signal", "source": "Group/Clock", "signal": "timeout", "target": ".", "method": "on_timeout"}]}
	var preview: Dictionary = scene_executor.prepare(action, "")
	check(not FileAccess.file_exists(path), "scene preview does not write target")
	if success(preview, "scene prepare non-tool script and custom signal receiver"):
		action["_expected_semantic_hash"] = preview.semantic_hash
		var result: Dictionary = scene_executor.execute(action, "")
		if success(result, "scene execute"):
			var staged := path + ".agent-create-%s.tmp.tscn" % action._create_action_id
			check(not FileAccess.file_exists(path) and not result.target_written, "create only stages target")
			check(FileAccess.get_sha256(staged) == result.staged_hash, "scene staged byte hash")
			# The Python transaction normally publishes this staged file.
			check(DirAccess.rename_absolute(staged, path) == OK, "publish staged scene in sandbox")
			var packed := ResourceLoader.load(path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene
			if check(packed != null, "reload PackedScene"):
				var node := packed.instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
				check(node.name == &"Level" and node is Node2D, "scene root name/type")
				var clock := node.get_node_or_null("Group/Clock") as Timer
				if check(clock != null, "scene nested child persists"):
					check(clock.owner == node and clock.get_parent().owner == node, "scene nested ownership persists")
					check(is_equal_approx(clock.wait_time, 2.5), "scene child property persists")
					var connections := clock.get_signal_connection_list("timeout")
					check(connections.size() == 1, "scene signal persists once")
					if connections.size() == 1:
						check(connections[0].callable.get_object() == node and connections[0].callable.get_method() == &"on_timeout" and (int(connections[0].flags) & CONNECT_PERSIST) != 0, "scene signal target/method/persistence")
				check(node.position == Vector2(12, 34) and node.get("score") == 9, "scene built-in and exported properties persist")
				check(node.get_script().resource_path == "res://executor_receiver.gd", "scene script persists")
				check(scene_executor._semantic_hash(node, action.operations) == preview.semantic_hash, "scene semantic hash survives save/reload")
				node.free()
			var edit := {"action": "edit_scene", "scene": path, "operations": [
				{"op": "set_node_property", "node": "Group/Clock", "property": "one_shot", "value": {"type": "bool", "value": true}}]}
			var before := FileAccess.get_sha256(path)
			var edit_preview: Dictionary = scene_executor.prepare(edit, before)
			if success(edit_preview, "closed scene edit prepare through EditorInterface"):
				edit["_expected_semantic_hash"] = edit_preview.semantic_hash
				if success(scene_executor.execute(edit, before), "closed scene edit execute"):
					var edited := (ResourceLoader.load(path, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE_DEEP) as PackedScene).instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
					check(edited.get_node("Group/Clock").one_shot, "closed scene edit persists")
					edited.free()
			check(scene_executor.prepare(edit, "stale").get("code") == "stale_scene", "stale scene rejected")
	done("scene")


func _settings() -> void:
	var old := InputEventKey.new()
	old.physical_keycode = KEY_SPACE
	old.shift_pressed = true
	ProjectSettings.set_setting("input/executor_jump", {"deadzone": 0.37, "events": [old]})
	check(ProjectSettings.save() == OK, "seed existing InputMap setting")
	var action := {"operations": [
		{"op": "add_input_action", "name": "executor_jump", "deadzone": 0.9},
		{"op": "add_input_event", "action": "executor_jump", "event": {"type": "key", "key": "Space", "physical": true, "shift": true}},
		{"op": "add_input_event", "action": "executor_jump", "event": {"type": "key", "key": "J"}},
		{"op": "add_input_event", "action": "executor_jump", "event": {"type": "key", "key": "J"}}]}
	var before := FileAccess.get_sha256("res://project.godot")
	var preview: Dictionary = settings_executor.prepare(action, before)
	if success(preview, "settings prepare"):
		check(preview.effective_operation_count == 1, "only missing event is effective")
		check(FileAccess.get_sha256("res://project.godot") == before, "settings preview is read only")
		action["_expected_semantic_hash"] = preview.semantic_hash
		if success(settings_executor.execute(action, before), "settings execute"):
			var config := ConfigFile.new()
			check(config.load("res://project.godot") == OK, "reload project settings from disk")
			var saved: Dictionary = config.get_value("input", "executor_jump")
			check(is_equal_approx(saved.deadzone, 0.37) and saved.events.size() == 2, "settings preserve deadzone and old event; add only missing")
			check(saved.events[0].is_match(old, true) and saved.events[1].keycode == KEY_J, "settings old/new event payloads persist")
			# Executor deliberately persists settings, with a restart flag, rather than replacing editor shortcuts.
			InputMap.load_from_project_settings()
			check(InputMap.action_get_events("executor_jump").size() == 2 and is_equal_approx(InputMap.action_get_deadzone("executor_jump"), 0.37), "saved bindings load into real InputMap")
			before = FileAccess.get_sha256("res://project.godot")
			var repeated: Dictionary = settings_executor.prepare(action, before)
			if success(repeated, "settings repeat prepare"):
				check(repeated.already_satisfied and repeated.effective_operation_count == 0, "repeat settings preview no-op")
				action["_expected_semantic_hash"] = repeated.semantic_hash
				var result: Dictionary = settings_executor.execute(action, before)
				if success(result, "settings repeat execute"):
					check(result.already_satisfied and not result.requires_editor_restart, "repeat settings execute no-op")
				check(FileAccess.get_sha256("res://project.godot") == before, "repeat settings does not rewrite file")
	check(settings_executor.prepare(action, "stale").get("code") == "stale_project_settings", "stale settings rejected")
	done("settings")


func resource_roundtrip(seed: Resource, name: String, operations: Array) -> Resource:
	var path := "res://%s.tres" % name
	if not check(ResourceSaver.save(seed, path) == OK, name + " seed save"):
		return null
	var uid := ResourceLoader.get_resource_uid(path)
	check(uid != ResourceUID.INVALID_ID, name + " seed has UID")
	var before := FileAccess.get_sha256(path)
	var action := {"resource": path, "operations": operations, "action_id": name, "wait_for_import": []}
	var preview: Dictionary = resource_executor.prepare(action, before)
	check(FileAccess.get_sha256(path) == before, name + " preview leaves disk unchanged")
	if not success(preview, name + " prepare"):
		return null
	# A second preview must not depend on freshly allocated Resource instance IDs.
	var repeated: Dictionary = resource_executor.prepare(action, before)
	check(repeated.get("semantic_hash") == preview.semantic_hash, name + " deterministic preview hash")
	action["_expected_semantic_hash"] = preview.semantic_hash
	action["_expected_dependency_fingerprint"] = preview.dependency_fingerprint
	var result: Dictionary = resource_executor.execute(action, before)
	success(result, name + " execute")
	var reloaded := ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE_DEEP)
	if not check(reloaded != null, name + " disk reload"):
		return null
	check(ResourceLoader.get_resource_uid(path) == uid, name + " UID preserved")
	check(ResourceUID.get_id_path(uid) == path, name + " UID still resolves to target, not staging file")
	check(resource_executor._semantic_hash(reloaded, operations, path) == preview.semantic_hash, name + " semantic hash survives save/reload")
	if result.get("ok", false):
		check(result.resource_hash == FileAccess.get_sha256(path), name + " returned byte hash")
	check(resource_executor.prepare(action, "stale").get("code") == "stale_resource", name + " stale resource rejected")
	return reloaded


func _resource_property() -> void:
	var seed := GradientTexture2D.new()
	seed.gradient = Gradient.new()
	var loaded := resource_roundtrip(seed, "resource_property", [
		{"op": "set_property", "target": [], "property": "width", "value": {"type": "int", "value": 32}},
		{"op": "set_property", "target": ["gradient"], "property": "interpolation_mode", "value": {"type": "int", "value": Gradient.GRADIENT_INTERPOLATE_CONSTANT}}]) as GradientTexture2D
	if loaded:
		check(loaded.width == 32 and loaded.gradient.interpolation_mode == Gradient.GRADIENT_INTERPOLATE_CONSTANT, "root and existing local subresource properties persist")
		var before_hash: String = resource_executor._semantic_hash(loaded, [])
		loaded.gradient.interpolation_mode = Gradient.GRADIENT_INTERPOLATE_LINEAR
		check(resource_executor._semantic_hash(loaded, []) != before_hash, "semantic hash detects local subresource content change")
	done("resource_property")


func _theme() -> void:
	var loaded := resource_roundtrip(Theme.new(), "theme", [
		{"op": "theme_set_item", "data_type": "color", "theme_type": "Button", "name": "font_color", "overwrite": false, "value": {"type": "Color", "value": [0.25, 0.5, 0.75, 1]}},
		{"op": "theme_set_item", "data_type": "stylebox", "theme_type": "Button", "name": "normal", "overwrite": false, "value": {"type": "NewSubresource", "class": "StyleBoxFlat", "properties": [
			{"property": "bg_color", "value": {"type": "Color", "value": [0.5, 0.25, 0.75, 1]}}]}}]) as Theme
	if loaded:
		check(loaded.get_color("font_color", "Button") == Color(0.25, 0.5, 0.75, 1), "Theme color persists")
		check(loaded.has_stylebox("normal", "Button") and loaded.get_stylebox("normal", "Button").bg_color == Color(0.5, 0.25, 0.75, 1), "Theme new local StyleBox persists")
	done("theme")


func _sprite_frames() -> void:
	var loaded := resource_roundtrip(SpriteFrames.new(), "sprite_frames", [
		{"op": "sprite_frames_add_animation", "name": "walk", "fps": 12.0, "loop": false, "frames": [
			{"duration": 2.0, "texture": {"type": "NewSubresource", "class": "GradientTexture2D", "properties": [
				{"property": "width", "value": {"type": "int", "value": 16}},
				{"property": "gradient", "value": {"type": "NewSubresource", "class": "Gradient", "properties": []}}]}}]}]) as SpriteFrames
	if loaded:
		if check(loaded.has_animation("walk"), "SpriteFrames animation persists"):
			check(loaded.get_animation_speed("walk") == 12.0 and not loaded.get_animation_loop("walk"), "SpriteFrames playback settings persist")
			check(loaded.get_frame_count("walk") == 1 and loaded.get_frame_duration("walk", 0) == 2.0, "SpriteFrames frame duration persists")
			var texture := loaded.get_frame_texture("walk", 0) as GradientTexture2D
			check(texture != null and texture.width == 16 and texture.gradient != null, "SpriteFrames nested local resources persist")
	done("sprite_frames")


func _animation() -> void:
	var seed := Animation.new()
	seed.length = 2.0
	var loaded := resource_roundtrip(seed, "animation", [
		{"op": "animation_add_value_track", "path": "Sprite2D:position", "interpolation": "linear", "update_mode": "continuous", "keys": [
			{"time": 0.0, "transition": 1.0, "value": {"type": "Vector2", "value": [0, 0]}},
			{"time": 1.5, "transition": 0.5, "value": {"type": "Vector2", "value": [10, 20]}}]}]) as Animation
	if loaded:
		if check(loaded.get_track_count() == 1, "Animation track persists"):
			check(loaded.track_get_path(0) == NodePath("Sprite2D:position") and loaded.track_get_key_count(0) == 2, "Animation path and keys persist")
			check(loaded.track_get_key_time(0, 1) == 1.5 and loaded.track_get_key_value(0, 1) == Vector2(10, 20) and loaded.track_get_key_transition(0, 1) == 0.5, "Animation typed key/time/transition persist")
	done("animation")


func _resource_safety() -> void:
	for mode in ["sentinel", "stale_preview", "stale_publish", "stale_temp", "backup_collision", "publish_failure", "restore", "restore_conflict", "restore_failure", "save_failure"]:
		var name: String = "resource_safety_" + mode
		var path := "res://%s.tres" % name
		var executor := ResourceFaults.new()
		executor.configure(plugin)
		executor.mode = mode
		safety_executors.append(executor)
		check(ResourceSaver.save(Animation.new(), path) == OK, name + " seed save")
		var original := FileAccess.get_file_as_bytes(path)
		var original_hash := FileAccess.get_sha256(path)
		var original_uid := ResourceLoader.get_resource_uid(path)
		executor.external_bytes = original + "; external edit, must survive\n".to_utf8_buffer()
		var sentinel := path + ".agent-backup"
		write_bytes(sentinel, "unrelated predictable backup".to_utf8_buffer())
		var action := {"resource": path, "action_id": name, "wait_for_import": [], "operations": [
			{"op": "set_property", "target": [], "property": "length", "value": {"type": "float", "value": 2.0}}]}
		var preview: Dictionary = executor.prepare(action, original_hash)
		if not success(preview, name + " prepare"):
			done(name)
			continue
		action["_expected_semantic_hash"] = preview.semantic_hash
		action["_expected_dependency_fingerprint"] = preview.dependency_fingerprint
		if mode == "stale_preview":
			write_bytes(path, executor.external_bytes)
		var result: Dictionary = executor.execute(action, original_hash)
		if executor.held_file != null:
			executor.held_file.close()
			executor.held_file = null
		print("RESOURCE_SAFETY " + mode + " " + JSON.stringify(result))
		check(FileAccess.get_file_as_string(sentinel) == "unrelated predictable backup", name + " never touches predictable sentinel")
		if executor.source_path != "" and mode != "publish_failure":
			check(not FileAccess.file_exists(executor.source_path), name + " temporary file consumed or cleaned")
		var actual := FileAccess.get_file_as_bytes(path) if FileAccess.file_exists(path) else PackedByteArray()
		if mode == "sentinel":
			success(result, name + " execute")
			check(actual != original and ResourceLoader.get_resource_uid(path) == original_uid, name + " publishes content with original UID")
			check(executor.backup_at_validation == original_hash and executor.validation_passed, name + " original retained through real postchecks")
			check(not FileAccess.file_exists(executor.backup_path), name + " own backup cleaned after success")
		else:
			check(not result.get("ok", true), name + " explicit failure")
			var codes := {"stale_preview": "stale_resource", "stale_publish": "stale_resource", "stale_temp": "stale_temporary", "backup_collision": "backup_exists", "publish_failure": "replace_failed", "restore": "saved_semantic_mismatch", "restore_conflict": "recovery_conflict", "restore_failure": "recovery_failed", "save_failure": "save_failed"}
			check(result.get("code") == codes[mode], name + " failure code")
			if mode in ["stale_preview", "stale_publish", "restore_conflict"]:
				check(actual == executor.external_bytes, name + " preserves external edit exactly")
				check(result.get("resource_hash", "") != FileAccess.get_sha256(path), name + " never authorizes server recovery over external bytes")
				if mode == "stale_publish":
					check(executor.boundary_fault_applied, name + " changes target after backup and immediately before final freshness check")
			elif mode == "restore_failure":
				check(actual == executor.published_bytes, name + " failed rename leaves publication present")
			elif mode == "publish_failure":
				check(actual == original or not FileAccess.file_exists(path), name + " failed publication leaves original or absent target")
				check(result.get("temporary_path") == executor.source_path and FileAccess.file_exists(executor.source_path), name + " explicitly retains unpublished candidate")
			else:
				check(actual == original, name + " original bytes preserved/restored exactly")
			if mode in ["restore", "restore_conflict", "restore_failure"]:
				check(executor.validation_passed and executor.backup_at_validation == original_hash, name + " actual postchecks ran with original backup intact")
				check(result.get("validation_code") == "saved_semantic_mismatch", name + " retains validation cause")
				if mode != "restore_conflict":
					check(result.get("resource_hash") == FileAccess.get_sha256(path), name + " reports owned final hash")
				if mode == "restore":
					check(result.get("restored", false), name + " reports successful local recovery")
					check(ResourceLoader.get_resource_uid(path) == original_uid, name + " restores UID")
					check(not FileAccess.file_exists(executor.backup_path) and not FileAccess.file_exists(executor.backup_path + ".restore"), name + " successful recovery cleans own files")
				else:
					check(not result.get("restored", true) and result.has("recovery_error"), name + " explicit recovery failure")
					check(result.get("backup_path") == executor.backup_path and FileAccess.get_file_as_bytes(executor.backup_path) == original, name + " original recovery evidence retained")
					if mode == "restore_failure":
						check(result.get("recovery_path") == executor.backup_path + ".restore" and FileAccess.get_file_as_bytes(executor.backup_path + ".restore") == original, name + " failed rename retains staged recovery evidence")
			elif mode == "backup_collision":
				check(FileAccess.get_file_as_string(executor.backup_path) == "unrelated unique-path sentinel", name + " refuses backup collision without deleting evidence")
			elif mode == "publish_failure":
				check(result.get("backup_path") == executor.backup_path and FileAccess.get_file_as_bytes(executor.backup_path) == original, name + " explicitly retains original after failed publication")
			elif executor.backup_path != "":
				check(not FileAccess.file_exists(executor.backup_path), name + " no backup left before publication")
		done(name)
