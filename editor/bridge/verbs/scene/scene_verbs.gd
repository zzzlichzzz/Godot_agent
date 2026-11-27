# editor/bridge/verbs/scene/scene_verbs.gd - примитивы сцены: план и применение.
# Обработчики `editor_scene_plan` (dry-run, ничего не пишет) и
# `editor_scene_apply` (один undo-шаг на батч) и `editor_scene_undo` (откат
# истории) из словаря
# `contract/editor_verbs.json`; маркер `# verb: <name>` читает
# `tools/gen_contract.py --check`. Исполнитель живёт здесь: `router` держит
# владельца обработчиков, а undo-история редактора ссылается на тот же объект.
@tool
extends RefCounted

const SceneExecutor := preload("scene_executor.gd")

var _executor = SceneExecutor.new()


# verb: editor_scene_plan
func scene_plan(args: Dictionary) -> Dictionary:
	return _executor.plan(args)


# verb: editor_scene_apply
func scene_apply(args: Dictionary) -> Dictionary:
	return _executor.apply(args)


# verb: editor_scene_undo
func scene_undo(args: Dictionary) -> Dictionary:
	return _executor.undo(args)


func register(router) -> void:
	router.register("editor_scene_plan", scene_plan)
	router.register("editor_scene_apply", scene_apply)
	router.register("editor_scene_undo", scene_undo)
