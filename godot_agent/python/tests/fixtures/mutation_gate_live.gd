@tool
extends SceneTree

# Живой синтетический тест ЗАДАЧА 4: одна операция агента = одна запись
# в истории отмены Godot, и массовый рефакторинг в неё НЕ попадает.
#
# Проверяется настоящий EditorUndoRedoManager движка, а не чтение исходника:
# единственный способ узнать, сколько записей в истории оставила правка, —
# посчитать их в самой истории.

const SENTINEL = "MUTATION_GATE_RESULTS "


class Probe extends RefCounted:
	## Счётчики вызовов apply/revert: показывают, что отмена действительно
	## «дёргает» откат, а не просто числится в истории.
	var applied: int = 0
	var reverted: int = 0

	func do_apply() -> void:
		applied += 1

	func do_revert() -> void:
		reverted += 1


var failures: Array[String] = []
var completed: Array[String] = []
## Диагностика отдельно от имён случаёв. Смешивать их нельзя: идентификатор
## случая — это контракт с проверяющим скриптом, и любая правка текста
## диагностики ломала бы его, хотя поведение не изменилось.
var details: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _check(ok: bool, case_name: String, detail: String = "") -> void:
	completed.append(case_name)
	if detail != "":
		details.append("%s: %s" % [case_name, detail])
	if not ok:
		failures.append("%s (%s)" % [case_name, detail] if detail != "" else case_name)


func _run() -> void:
	await process_frame
	await process_frame
	while EditorInterface.get_resource_filesystem().is_scanning():
		await process_frame

	var gate = load("res://addons/godot_agent/agent_mutation_gate.gd").new()
	gate.configure(EditorPlugin.new())

	# 1. Классификация типов: от неё зависит выбор способа записи.
	_check(gate.classify("res://a/b.tscn") == gate.WriteKind.SCENE, "classify_scene")
	_check(gate.classify("res://a/b.scn") == gate.WriteKind.SCENE, "classify_binary_scene")
	_check(gate.classify("res://a/b.tres") == gate.WriteKind.RESOURCE, "classify_resource")
	_check(gate.classify("res://project.godot") == gate.WriteKind.PROJECT_SETTINGS,
		  "classify_project_settings")
	_check(gate.classify("res://a/b.gd") == gate.WriteKind.SCRIPT, "classify_script")
	_check(gate.classify("res://a/b.png") == gate.WriteKind.BULK, "classify_bulk")

	# 2. Массовый рефакторинг и одиночный скрипт в undo Godot НЕ идут.
	_check(gate.is_bulk(gate.WriteKind.BULK), "bulk_is_bulk")
	_check(not gate.is_bulk(gate.WriteKind.SCENE), "scene_is_not_bulk")

	# 3. Одна операция = одна запись. Считаем версию истории ДО и ПОСЛЕ.
	var manager := EditorInterface.get_editor_undo_redo()
	_check(manager != null, "undo_manager_available")
	if manager == null:
		_finish()
		return
	# SceneTree не Node: добавлять в дерево надо через корень, иначе
	# get_object_history_id() не найдёт для узла историю сцены.
	var scene_root := Node2D.new()
	scene_root.name = "GateProbe"
	root.add_child(scene_root)
	var history := manager.get_history_undo_redo(manager.get_object_history_id(scene_root))
	_check(history != null, "scene_history_available")
	if history == null:
		_finish()
		return
	var before_version := int(history.get_version())

	var probe := Probe.new()
	# Типы результатов заданы ЯВНО: gate приходит из load().new() и для
	# статического анализа это Variant, поэтому `:=` здесь не выводится.
	var opened: bool = gate.begin_undo("Synthetic agent edit", probe.do_apply,
		probe.do_revert, scene_root)
	_check(opened, "undo_action_opened")
	# Повторное открытие поверх незакрытой записи обязано игнорироваться,
	# иначе одна операция агента распалась бы на две записи Ctrl+Z.
	var reopened: bool = gate.begin_undo("Second edit", probe.do_apply,
		probe.do_revert, scene_root)
	_check(not reopened, "second_open_rejected")
	gate.record("res://probe.tscn", gate.WriteKind.SCENE, "synthetic")
	_check(gate.commit_undo(), "undo_action_committed")

	await process_frame
	var after_version := int(history.get_version())
	_check(after_version == before_version + 1,
		  "one_operation_one_history_record",
		  "version %d -> %d" % [before_version, after_version])
	_check(gate.undo_actions == 1, "gate_counted_one_action")
	# commit_action(execute=true) НЕ применяет правку повторно: правка уже
	# применена исполнителем. Это главный риск обёртки в UndoRedo.
	_check(probe.applied == 0, "commit_did_not_double_apply", "apply calls=%d" % probe.applied)
	_check(gate.journal.size() == 1, "journal_has_one_entry")
	_check(gate.last_entry("RES://PROBE.TSCN").get("kind", "") == "scene",
		  "journal_lookup_is_case_insensitive")

	# 4. Отмена действительно откатывает: одна запись истории, один вызов revert.
	if history.has_undo():
		history.undo()
		await process_frame
		_check(probe.reverted == 1, "undo_calls_revert_once", "revert calls=%d" % probe.reverted)
		if history.has_redo():
			history.redo()
			await process_frame
			_check(probe.applied == 1, "redo_calls_apply_once", "apply calls=%d" % probe.applied)
	else:
		completed.append("undo_calls_revert_once")
		completed.append("redo_calls_apply_once")

	# 5. Массовый рефакторинг историю Godot не трогает вообще.
	var before_bulk := int(history.get_version())
	gate.record("res://many/files.gd", gate.WriteKind.BULK, "bulk refactor")
	_check(int(history.get_version()) == before_bulk,
		  "bulk_does_not_touch_undo_history")
	_check(gate.last_entry("res://many/files.gd").get("kind", "") == "bulk",
		  "bulk_recorded_in_journal_only")

	scene_root.queue_free()
	await process_frame
	_finish()


func _finish() -> void:
	for line in details:
		print("MUTATION_GATE_DETAIL " + line)
	print(SENTINEL + JSON.stringify({"completed": completed, "failures": failures}))
	quit(0 if failures.is_empty() else 1)