extends "res://addons/godot_agent/editor/native/agent_resource_executor.gd"
# Read-only publication witness before unchanged native validation/compensation.
var published_raw := PackedByteArray()
func _validate_saved_resource(path: String, action: Dictionary, uid_before: int) -> Dictionary:
	published_raw = FileAccess.get_file_as_bytes(path)
	return super._validate_saved_resource(path, action, uid_before)
