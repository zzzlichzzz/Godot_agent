extends SceneTree

# Живой синтетический тест ЗАДАЧИ 1: перезагрузка сцены не должна терять
# несохранённые правки пользователя.
#
# Панель создаётся через .new() БЕЗ добавления в дерево — её _ready() рассчитан
# на сборку кодом в доке плагина и без $VBoxContainer/$ChatLog сыплет ошибки.
# Проверяемые функции _auto_reload_changed_scene и его помощники ходят только в
# EditorInterface, поэтому дерево им не нужно.

const SENTINEL = "SCENE_RELOAD_GUARD_RESULTS "
const SCENE_PATH := "res://guard_scene.tscn"

var failures: Array[String] = []
var completed: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _check(ok: bool, case_name: String) -> void:
	completed.append(case_name)
	if not ok:
		failures.append(case_name)


func _run() -> void:
	await process_frame
	await process_frame
	while EditorInterface.get_resource_filesystem().is_scanning():
		await process_frame

	var panel = load("res://addons/godot_agent/agent_panel.gd").new()
	# Настоящий EditorPlugin нужен ради сигнала scene_saved: панель на него
	# подписывается, чтобы знать версию истории на момент последнего сохранения.
	panel.set_editor_plugin(EditorPlugin.new())

	# open_scene_from_path() возвращает void — результат не проверяем,
	# открытие подтверждает следующая проверка edited_scene_root_exists.
	EditorInterface.open_scene_from_path(SCENE_PATH)
	await process_frame
	await process_frame
	completed.append("scene_opened")

	# 1. Свежеоткрытая сцена без единой правки обязана считаться чистой,
	#    иначе агент перестанет перечитывать сцену после своей же записи.
	_check(not panel._scene_reload_would_lose_edits(SCENE_PATH),
		  "clean_open_scene_is_reloadable")

	# 2. Одна отменяемая правка — и сцена уже не чистая.
	var root := EditorInterface.get_edited_scene_root()
	_check(root != null, "edited_scene_root_exists")
	if root != null:
		var undo := EditorInterface.get_editor_undo_redo()
		# custom_context = корень сцены: действие попадает в историю СЦЕНЫ,
		# а не в общую историю редактора.
		undo.create_action("Synthetic probe", UndoRedo.MERGE_DISABLE, root)
		undo.add_do_method(root, "set_name", root.name)
		undo.commit_action()
		await process_frame
		_check(panel._scene_reload_would_lose_edits(SCENE_PATH),
			  "undoable_edit_marks_scene_dirty")

		# 3. Ctrl+S переводит сцену в сохранённое состояние — повторная
		#    перезагрузка снова становится безопасной.
		EditorInterface.save_scene()
		await process_frame
		await process_frame
		# Говорим панели ровно то, что сделал бы движок: под --script плагин
		# не зарегистрирован, и вручную созданный EditorPlugin сигнала
		# scene_saved не получит.
		panel._on_editor_scene_saved(SCENE_PATH)
		_check(not panel._scene_reload_would_lose_edits(SCENE_PATH),
			  "save_clears_dirty_state")

		# 4. Главный сценарий задачи: пользователь правит сцену, НЕ сохраняет,
		#    агент меняет файл — узел пользователя обязан уцелеть.
		var marker := Node.new()
		marker.name = "UnsavedUserNode"
		root.add_child(marker)
		undo.create_action("Synthetic probe 2", UndoRedo.MERGE_DISABLE, root)
		undo.add_do_method(root, "set_name", root.name)
		undo.commit_action()
		await process_frame
		_check(panel._scene_reload_would_lose_edits(SCENE_PATH),
			  "second_edit_marks_scene_dirty_again")

		panel._auto_reload_changed_scene(SCENE_PATH)
		await process_frame
		await process_frame
		var after := EditorInterface.get_edited_scene_root()
		_check(after != null and after.get_node_or_null("UnsavedUserNode") != null,
			  "dirty_scene_is_not_reloaded")

		# 5. Обратная сторона: когда сцена гарантированно чиста, решение о
		#    перезагрузке обязано быть положительным - иначе пользователь после
		#    каждой правки агента вручную переоткрывал бы сцену.
		#    Сам reload_scene_from_path() здесь НЕ зовём: в headless-редакторе он
		#    обрывает скрипт (доказано пробой без кода агента).
		panel._mark_scene_clean(SCENE_PATH)
		_check(not panel._scene_reload_would_lose_edits(SCENE_PATH),
			  "marked_scene_is_reloadable")

	# 6. Сцена не открыта — вопрос о несохранённых правках неуместен.
	_check(not panel._scene_reload_would_lose_edits("res://not_open_at_all.tscn"),
		  "unopened_scene_is_reloadable")

	panel.free()
	await process_frame
	await process_frame
	print(SENTINEL + JSON.stringify({"completed": completed, "failures": failures}))
	quit(0 if failures.is_empty() else 1)
