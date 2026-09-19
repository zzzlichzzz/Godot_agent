extends SceneTree

const MANIFEST_PATH := "res://.godot_agent_validation/manifest.json"


func _initialize() -> void:
	var diagnostics: Array = []
	var manifest_file := FileAccess.open(MANIFEST_PATH, FileAccess.READ)
	if manifest_file == null:
		_finish([_diagnostic("harness", MANIFEST_PATH, "Не удалось прочитать manifest")])
		return
	var manifest = JSON.parse_string(manifest_file.get_as_text())
	if not manifest is Dictionary:
		_finish([_diagnostic("harness", MANIFEST_PATH, "Manifest содержит не JSON object")])
		return
	for raw_path in manifest.get("targets", []):
		var path := str(raw_path)
		if not path.begins_with("res://"):
			diagnostics.append(_diagnostic("path", path, "Разрешены только res:// targets"))
			continue
		var resource = ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE)
		if resource == null:
			diagnostics.append(_diagnostic("resource_load", path, "Godot не смог загрузить ресурс"))
			continue
		if path.ends_with(".tscn") and not resource is PackedScene:
			diagnostics.append(_diagnostic("scene_load", path, "Ресурс сцены не является PackedScene"))
	_finish(diagnostics)


func _diagnostic(category: String, path: String, message: String) -> Dictionary:
	return {"severity": "error", "category": category, "path": path, "message": message}


func _finish(diagnostics: Array) -> void:
	var result_path := "res://.godot_agent_validation/result.json"
	var output := FileAccess.open(result_path, FileAccess.WRITE)
	if output != null:
		output.store_string(JSON.stringify({"schema_version": 1, "diagnostics": diagnostics}))
	quit(1 if not diagnostics.is_empty() else 0)
