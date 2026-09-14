@tool
extends "res://addons/godot_agent/agent_resource_executor.gd"

# Faults occur at real save/publication boundaries, not in a fake filesystem.
var mode := ""
var source_path := ""
var target_path := ""
var backup_path := ""
var external_bytes := PackedByteArray()
var backup_at_validation := ""
var validation_passed := false
var published_bytes := PackedByteArray()
var held_file: FileAccess
var boundary_fault_applied := false


func _save_temporary_resource(resource: Resource, path: String) -> Error:
	source_path = path
	var error := super._save_temporary_resource(resource, path)
	# Exercise cleanup with a real file already written by ResourceSaver.
	return ERR_FILE_CANT_WRITE if mode == "save_failure" and error == OK else error


func _replace_resource_file(source: String, target: String, source_hash: String, target_hash: String) -> Dictionary:
	backup_path = source + ".backup"
	target_path = target
	if mode == "stale_temp":
		_write(source, FileAccess.get_file_as_bytes(source) + "; changed staging file\n".to_utf8_buffer())
	elif mode == "backup_collision":
		_write(backup_path, "unrelated unique-path sentinel".to_utf8_buffer())
	elif mode == "publish_failure":
		held_file = FileAccess.open(source, FileAccess.READ)
	return super._replace_resource_file(source, target, source_hash, target_hash)


func _file_hash(path: String) -> String:
	var hash := super._file_hash(path)
	if mode == "stale_publish" and not boundary_fault_applied and path == source_path and backup_path != "" and FileAccess.file_exists(backup_path):
		# Original backup already exists; change target just before its final check.
		boundary_fault_applied = true
		_write(target_path, external_bytes)
	return hash


func _validate_saved_resource(path: String, action: Dictionary, uid_before: int) -> Dictionary:
	backup_at_validation = _file_hash(backup_path)
	var result := super._validate_saved_resource(path, action, uid_before)
	validation_passed = bool(result.get("ok", false))
	if not validation_passed:
		return result
	published_bytes = FileAccess.get_file_as_bytes(path)
	if mode == "restore_conflict":
		_write(path, external_bytes)
	elif mode == "restore_failure":
		# A real Windows read handle prevents replacement while held open.
		held_file = FileAccess.open(path, FileAccess.READ)
	if mode in ["restore", "restore_conflict", "restore_failure"]:
		return _fail("saved_semantic_mismatch", "Injected post-publication semantic rejection")
	return result


func _write(path: String, bytes: PackedByteArray) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("Could not inject resource boundary fault: " + path)
		return
	file.store_buffer(bytes)
	file.close()
