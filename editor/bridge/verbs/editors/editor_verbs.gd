# editor/bridge/verbs/editors/editor_verbs.gd - примитивы открытых редакторов и выделения.
# Обработчики трёх примитивов словаря `contract/editor_verbs.json`.
# Маркер `# verb: <name>` читает `tools/gen_contract.py --check`: имя в маркере
# сверяется с примитивом, забытый маркер -> `missing`, лишний -> `extra`.
@tool
extends RefCounted

const ContextSnapshot := preload("context_snapshot.gd")

const PROTOCOL := 1
const VERBS_VERSION := 3


# verb: editor_ping
func ping(_args: Dictionary) -> Dictionary:
	return {"ok": true, "result": {
		"godot": str(Engine.get_version_info().get("string", "4")),
		"verbs_version": VERBS_VERSION,
		"protocol": PROTOCOL,
		"open_scenes": ContextSnapshot.scenes().size(),
		"uptime_s": ContextSnapshot.uptime_s()}}


# verb: editor_state
func state(_args: Dictionary) -> Dictionary:
	return {"ok": true, "result": ContextSnapshot.state()}


# verb: editor_selection
func selection(_args: Dictionary) -> Dictionary:
	return {"ok": true, "result": ContextSnapshot.selection()}


func register(router) -> void:
	router.register("editor_ping", ping)
	router.register("editor_state", state)
	router.register("editor_selection", selection)
