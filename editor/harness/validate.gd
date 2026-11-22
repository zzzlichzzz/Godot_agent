# editor/harness/validate.gd - SceneTree-скрипт для headless-прогона:
# читает manifest.json, грузит цели, пишет result.json (из agent_headless_validator.gd).
# Тонкий harness: читает manifest.json, грузит цели, пишет result.json.
# Правила: R-14 (без логики проверок), needs_live: в CI живого Godot нет, вердикт
# харнесса - доказательство для человека, приёмкой не считается.
extends SceneTree

const DEFAULT_MANIFEST := "res://harness_manifest.json"
const RESULT := "user://godot_agent/harness_result.json"


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var path := DEFAULT_MANIFEST if args.is_empty() else str(args[0])
	var manifest := _read_json(path)
	var targets: Array = manifest.get("targets", [])
	var problems: Array = []
	for target in targets:
		if not ResourceLoader.exists(str(target)):
			problems.append("нет ресурса: %s" % target)
	var out := {"ok": problems.is_empty(), "manifest": path,
		"checked": targets.size(), "problems": problems}
	_write_json(out)
	print(JSON.stringify(out))
	quit(0 if problems.is_empty() else 1)


func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var handle := FileAccess.open(path, FileAccess.READ)
	if handle == null:
		return {}
	var parsed = JSON.parse_string(handle.get_as_text())
	handle.close()
	return parsed if typeof(parsed) == TYPE_DICTIONARY else {}


func _write_json(payload: Dictionary) -> void:
	DirAccess.make_dir_recursive_absolute(
		ProjectSettings.globalize_path("user://godot_agent"))
	var handle := FileAccess.open(RESULT, FileAccess.WRITE)
	if handle == null:
		return
	handle.store_string(JSON.stringify(payload))
	handle.close()
