# editor/bridge/verbs/scene/scene_executor.gd - план и применение правок сцены.
# Один батч операций = один undo-шаг (`create_action` → `commit_action` /
# `cancel_action`). План ничего не пишет: прогон идёт на отсоединённой копии.
# Порядок проверок: аргументы, сцена, `expected_revision`, `plan_digest`, затем
# undo; любая ошибка до commit - сцена не изменилась. Правила: R-12, R-14.
@tool
extends RefCounted

const ContextSnapshot := preload(
	"res://addons/godot_agent/editor/bridge/verbs/editors/context_snapshot.gd")
const ErrorCodes := preload("res://addons/godot_agent/editor/bridge/dispatch/error_codes.gd")

const OPS: Array = ["add_node", "set_property", "attach_script", "connect_signal"]
const MAX_OPERATIONS := 64
const MAX_VALUE_BYTES := 4096
const DEFAULT_UNDO_LABEL := "agent: scene_ops"

#: Последний план по сцене: `{digest, revision}`. Пропуск одноразовый.
static var _plans: Dictionary = {}


func plan(args: Dictionary) -> Dictionary:
	var problem := _check(args)
	if not problem.is_empty():
		return problem
	var scene := str(args["scene"])
	var operations: Array = args["operations"]
	var digest := digest_of(scene, int(args["expected_revision"]), operations)
	var probe := _probe(scene)
	if probe == null:
		return _fail(ErrorCodes.SCENE_NOT_FOUND, "сцена не читается: %s" % scene)
	var steps: Array = []
	var would: Array = []
	var warnings: Array = []
	var failed: Dictionary = {}
	for index in range(operations.size()):
		var op: Dictionary = operations[index]
		steps.append({"index": index, "op": str(op["op"]),
			"target_node": _target_of(op), "preview": _preview(op)})
		var outcome := _apply_one(probe, op)
		if not bool(outcome.get("ok", false)):
			failed = outcome
			break
		would.append("%s.%s" % [str(outcome.get("node_path", "")),
			str(outcome.get("field", ""))])
	probe.free()
	if not failed.is_empty():
		return _fail(ErrorCodes.PLAN_INVALID, str(failed.get("reason", "план не сходится")))
	_plans[scene] = {"digest": digest, "revision": int(args["expected_revision"])}
	return {"ok": true, "result": {"scene": scene,
		"revision": ContextSnapshot.revision_of(scene), "plan_digest": digest,
		"steps": steps, "would_change": would, "warnings": warnings}}


func apply(args: Dictionary) -> Dictionary:
	var problem := _check(args)
	if not problem.is_empty():
		return problem
	var scene := str(args["scene"])
	var operations: Array = args["operations"]
	var digest := str(args.get("plan_digest", ""))
	var undo_label := str(args.get("undo_label", "")).strip_edges()
	if undo_label.is_empty():
		undo_label = DEFAULT_UNDO_LABEL
	var root := _edited_root()
	if root == null or str(root.scene_file_path) != scene:
		return _fail(ErrorCodes.SCENE_NOT_FOUND, "сцена не открыта в редакторе: %s" % scene)
	var current := ContextSnapshot.revision_of(scene)
	var expected := int(args["expected_revision"])
	if current != expected:
		return _fail(ErrorCodes.REVISION_MISMATCH,
			"ревизия сцены %d, запрос рассчитывал на %d" % [current, expected])
	var stored: Dictionary = _plans.get(scene, {})
	if str(stored.get("digest", "")) != digest:
		return _fail(ErrorCodes.STALE_PLAN,
			"plan_digest не совпадает с последним планом по %s" % scene)
	if not EditorInterface.has_method("get_editor_undo_redo"):
		return _fail(ErrorCodes.APPLY_FAILED, "у редактора нет undo-менеджера")
	var probe := root.duplicate()
	var receipts: Array = []
	var changes: Array = []
	var failed: Dictionary = {}
	for index in range(operations.size()):
		var op: Dictionary = operations[index]
		var outcome := _apply_one(probe, op)
		if not bool(outcome.get("ok", false)):
			failed = outcome
			break
		receipts.append({"step_id": index, "op": str(op["op"]),
			"node_path": str(outcome.get("node_path", "")), "applied": true})
		changes.append({"node_path": str(outcome.get("node_path", "")),
			"field": str(outcome.get("field", "")), "before": outcome.get("before"),
			"after": outcome.get("after")})
	probe.free()
	if not failed.is_empty():
		return _fail(ErrorCodes.APPLY_FAILED, str(failed.get("reason", "проба не прошла")))
	var undo = EditorInterface.get_editor_undo_redo()
	undo.create_action(undo_label, UndoRedo.MERGE_DISABLE, root)
	for op in operations:
		_register(undo, root, op)
	# `EditorUndoRedoManager.commit_action()` возвращает void — признака отказа у него нет.
	# Проверка шла до commit (проба на копии), а отказ внутри undo-шага откатывает undo-история.
	undo.commit_action()
	_plans.erase(scene)
	ContextSnapshot.bump(scene)
	return {"ok": true, "result": {"scene": scene,
		"applied_revision": ContextSnapshot.revision_of(scene),
		"undo_label": undo_label, "receipts": receipts, "changes": changes}}


func undo(args: Dictionary) -> Dictionary:
	# Откат одного undo-шага: батч `apply` = одно действие истории (ADR-0007).
	# Сам примитив сцену не пишет: состояние меняет история редактора.
	var scene := str(args.get("scene", ""))
	if not scene.begins_with("res://"):
		return _fail(ErrorCodes.INVALID_ARGS, "scene должен быть res://..., получено '%s'" % scene)
	var revision = args.get("expected_revision")
	if typeof(revision) != TYPE_INT and typeof(revision) != TYPE_FLOAT:
		return _fail(ErrorCodes.INVALID_ARGS, "expected_revision должен быть целым")
	var root := _edited_root()
	if root == null or str(root.scene_file_path) != scene:
		return _fail(ErrorCodes.SCENE_NOT_FOUND, "сцена не открыта в редакторе: %s" % scene)
	var current := ContextSnapshot.revision_of(scene)
	if current != int(revision):
		return _fail(ErrorCodes.REVISION_MISMATCH,
			"ревизия сцены %d, запрос рассчитывал на %d" % [current, int(revision)])
	if not EditorInterface.has_method("get_editor_undo_redo"):
		return _fail(ErrorCodes.NOTHING_TO_UNDO, "у редактора нет undo-менеджера")
	var manager = EditorInterface.get_editor_undo_redo()
	var history_id: int = int(manager.get_object_history_id(root))
	if history_id < 0:
		return _fail(ErrorCodes.NOTHING_TO_UNDO, "у сцены нет истории отката: %s" % scene)
	var history = manager.get_history_undo_redo(history_id)
	if history == null or not history.has_undo():
		return _fail(ErrorCodes.NOTHING_TO_UNDO, "в истории сцены нет действий: %s" % scene)
	var label := str(history.get_current_action_name())
	# Версия истории (`UndoRedo.get_version()`): +1 за действие, -1 за откат.
	var before := int(history.get_version())
	history.undo()
	ContextSnapshot.bump(scene)
	return {"ok": true, "result": {"revision": ContextSnapshot.revision_of(scene),
		"undone": true, "undo_label": label, "history_version_before": before,
		"history_version": int(history.get_version())}}


const FIELDS := {
	"add_node": ["parent", "name", "type"],
	"set_property": ["node", "property"],
	"attach_script": ["node", "script"],
	"connect_signal": ["from", "signal", "to", "method"],
}


func _check(args: Dictionary) -> Dictionary:
	# Аргументы проверяются до любого чтения сцены: отказ дешёвый и типизированный.
	var scene := str(args.get("scene", ""))
	if not scene.begins_with("res://"):
		return _fail(ErrorCodes.INVALID_ARGS, "scene должен быть res://..., получено '%s'" % scene)
	var revision = args.get("expected_revision")
	if typeof(revision) != TYPE_INT and typeof(revision) != TYPE_FLOAT:
		return _fail(ErrorCodes.INVALID_ARGS, "expected_revision должен быть целым")
	var operations = args.get("operations")
	if typeof(operations) != TYPE_ARRAY:
		return _fail(ErrorCodes.INVALID_ARGS, "operations должен быть массивом")
	if operations.is_empty() or operations.size() > MAX_OPERATIONS:
		return _fail(ErrorCodes.INVALID_ARGS, "операций %d, допустимо 1..%d"
			% [operations.size(), MAX_OPERATIONS])
	for index in range(operations.size()):
		var op = operations[index]
		if typeof(op) != TYPE_DICTIONARY:
			return _fail(ErrorCodes.INVALID_ARGS, "операция %d - не словарь" % index)
		var name := str(op.get("op", ""))
		if not OPS.has(name):
			return _fail(ErrorCodes.UNKNOWN_OPERATION,
				"операция %d: неизвестное op '%s'" % [index, name])
		for key in FIELDS[name]:
			if not op.has(key):
				return _fail(ErrorCodes.INVALID_ARGS,
					"операция %d (%s): нет поля %s" % [index, name, key])
			if typeof(op[key]) != TYPE_STRING and typeof(op[key]) != TYPE_STRING_NAME:
				return _fail(ErrorCodes.INVALID_ARGS,
					"операция %d (%s): поле %s должно быть строкой" % [index, name, key])
			var empty := str(op[key]).strip_edges().is_empty()
			if empty and not (name == "add_node" and key == "parent"):
				return _fail(ErrorCodes.INVALID_ARGS,
					"операция %d (%s): пустое поле %s" % [index, name, key])
		if name == "set_property":
			var size := _canon(op.get("value")).to_utf8_buffer().size()
			if size > MAX_VALUE_BYTES:
				return _fail(ErrorCodes.INVALID_ARGS,
					"операция %d: значение %d Б больше %d" % [index, size, MAX_VALUE_BYTES])
	return {}


func _fail(reason: String, message: String) -> Dictionary:
	return ErrorCodes.payload(reason, message)


func digest_of(scene: String, revision: int, operations: Array) -> String:
	# Канонический вид один для Python и GDScript: сцена, ревизия, операции по
	# порядку; ключи внутри операции и вложенных словарей сортируются, поэтому
	# перестановка ключей отпечаток не меняет, а перестановка операций - меняет.
	var lines := PackedStringArray(["scene=" + scene, "revision=%d" % revision])
	for op in operations:
		lines.append(_canon(op))
	return "\n".join(lines).sha256_text()


func _canon(value) -> String:
	match typeof(value):
		TYPE_DICTIONARY:
			var keys: Array = value.keys()
			keys.sort()
			var pairs := PackedStringArray()
			for key in keys:
				pairs.append(JSON.stringify(str(key)) + ":" + _canon(value[key]))
			return "{" + ",".join(pairs) + "}"
		TYPE_ARRAY:
			var items := PackedStringArray()
			for item in value:
				items.append(_canon(item))
			return "[" + ",".join(items) + "]"
		TYPE_INT:
			return "%d" % int(value)
		TYPE_FLOAT:
			# JSON кадра приносит числа как float: `3` после разбора это `3.0`.
			# Python печатает целое как `3`, поэтому целые float печатаются так же,
			# иначе `plan_digest` двух реализаций не сходится (дефект D-3).
			var number: float = value
			if number == floor(number) and absf(number) < 1e15:
				return "%d" % int(number)
			return JSON.stringify(number)
		_:
			return JSON.stringify(value)


func _probe(scene: String) -> Node:
	# План и проба apply идут по экземпляру из файла: редакторские узлы не
	# трогаются, поэтому dry-run безопасен и в `-s`-режиме.
	var packed = ResourceLoader.load(scene)
	if packed is PackedScene:
		return (packed as PackedScene).instantiate(PackedScene.GEN_EDIT_STATE_INSTANCE)
	return null


func _edited_root() -> Node:
	if not EditorInterface.has_method("get_edited_scene_root"):
		return null
	return EditorInterface.get_edited_scene_root()


func _apply_one(root: Node, op: Dictionary) -> Dictionary:
	# Одна семантика для плана (копия) и для undo do-метода (настоящее дерево):
	# расхождение между «что показали» и «что сделали» невозможно.
	var name := str(op.get("op", ""))
	match name:
		"add_node":
			var parent := _find(root, str(op.get("parent", "")))
			if parent == null:
				return _no("нет узла-родителя '%s'" % str(op.get("parent", "")))
			var node_name := str(op.get("name", ""))
			if parent.has_node(NodePath(node_name)):
				return _no("узел '%s' уже есть у '%s'" % [node_name, str(op.get("parent", ""))])
			var type_name := str(op.get("type", ""))
			var instance = ClassDB.instantiate(type_name)
			if instance == null or not (instance is Node):
				return _no("неизвестный тип узла '%s'" % type_name)
			var child: Node = instance
			child.name = node_name
			parent.add_child(child)
			return _yes(_path_of(root, child), "node", null, type_name)
		"set_property":
			var node := _find(root, str(op.get("node", "")))
			if node == null:
				return _no("нет узла '%s'" % str(op.get("node", "")))
			var field := str(op.get("property", ""))
			if not _has_property(node, field):
				return _no("у узла '%s' нет свойства '%s'" % [str(op.get("node", "")), field])
			var before = node.get(field)
			node.set(field, op.get("value"))
			return _yes(_path_of(root, node), field, before, node.get(field))
		"attach_script":
			var node := _find(root, str(op.get("node", "")))
			if node == null:
				return _no("нет узла '%s'" % str(op.get("node", "")))
			var script_path := str(op.get("script", ""))
			var script = ResourceLoader.load(script_path)
			if script == null or not (script is Script):
				return _no("нет скрипта '%s'" % script_path)
			var before := ""
			if node.get_script() != null:
				before = str(node.get_script().resource_path)
			node.set_script(script)
			return _yes(_path_of(root, node), "script", before, script_path)
		"connect_signal":
			var from := _find(root, str(op.get("from", "")))
			var to := _find(root, str(op.get("to", "")))
			if from == null or to == null:
				return _no("нет узла связи: '%s' -> '%s'"
					% [str(op.get("from", "")), str(op.get("to", ""))])
			var signal_name := str(op.get("signal", ""))
			var method := str(op.get("method", ""))
			if not from.has_signal(signal_name):
				return _no("у узла '%s' нет сигнала '%s'" % [str(op.get("from", "")), signal_name])
			if not to.has_method(method):
				return _no("у узла '%s' нет метода '%s'" % [str(op.get("to", "")), method])
			from.connect(signal_name, Callable(to, method))
			return _yes(_path_of(root, from), signal_name, false, true)
	return _no("неизвестное op '%s'" % name)


func _register(undo, root: Node, op: Dictionary) -> void:
	var name := str(op.get("op", ""))
	match name:
		"add_node":
			var parent := _find(root, str(op.get("parent", "")))
			var child_path := _join(_path_of(root, parent), str(op.get("name", "")))
			undo.add_do_method(Callable(self, "_run_op").bind(root, op))
			undo.add_undo_method(Callable(self, "_undo_add").bind(root, child_path))
		"set_property":
			var node := _find(root, str(op.get("node", "")))
			if node == null:
				return
			var field := str(op.get("property", ""))
			undo.add_do_property(node, field, op.get("value"))
			undo.add_undo_property(node, field, node.get(field))
		"attach_script":
			var node := _find(root, str(op.get("node", "")))
			undo.add_do_method(Callable(self, "_run_op").bind(root, op))
			undo.add_undo_method(Callable(self, "_undo_attach").bind(root, _path_of(root, node)))
		"connect_signal":
			var from := _find(root, str(op.get("from", "")))
			var to := _find(root, str(op.get("to", "")))
			undo.add_do_method(Callable(self, "_run_op").bind(root, op))
			undo.add_undo_method(Callable(self, "_undo_connect").bind(root,
				_path_of(root, from), str(op.get("signal", "")), _path_of(root, to),
				str(op.get("method", ""))))


func _run_op(root: Node, op: Dictionary) -> void:
	_apply_one(root, op)


func _undo_add(root: Node, node_path: String) -> void:
	var node := _find(root, node_path)
	if node == null or node == root:
		return
	var parent := node.get_parent()
	if parent != null:
		parent.remove_child(node)
	node.queue_free()


func _undo_attach(root: Node, node_path: String) -> void:
	var node := _find(root, node_path)
	if node != null:
		node.set_script(null)


func _undo_connect(root: Node, from_path: String, signal_name: String,
		to_path: String, method: String) -> void:
	var from := _find(root, from_path)
	var to := _find(root, to_path)
	if from == null or to == null:
		return
	if from.is_connected(signal_name, Callable(to, method)):
		from.disconnect(signal_name, Callable(to, method))


func _yes(node_path: String, field: String, before, after) -> Dictionary:
	return {"ok": true, "node_path": node_path, "field": field,
		"before": before, "after": after}


func _no(reason: String) -> Dictionary:
	return {"ok": false, "reason": reason}


func _find(root: Node, path: String) -> Node:
	if root == null:
		return null
	var relative := _normalize(path)
	if relative.is_empty():
		return root
	return root.get_node_or_null(NodePath(relative))


func _normalize(path: String) -> String:
	# Принимает и относительный путь, и абсолютный `/root/<сцена>/...`, и `.`.
	var text := path.strip_edges()
	if text == "/root" or text == ".":
		return ""
	if text.begins_with("/root/"):
		var parts := text.split("/", false, 2)
		text = str(parts[2]) if parts.size() > 2 else ""
	while text.begins_with("./"):
		text = text.substr(2)
	if text == ".":
		return ""
	return text


func _path_of(root: Node, node: Node) -> String:
	if node == null or root == null or node == root:
		return ""
	return str(root.get_path_to(node))


func _join(parent_path: String, node_name: String) -> String:
	if parent_path.is_empty():
		return node_name
	return parent_path + "/" + node_name


func _has_property(node: Node, field: String) -> bool:
	for item in node.get_property_list():
		if str(item.get("name", "")) == field:
			return true
	return false


func _target_of(op: Dictionary):
	match str(op.get("op", "")):
		"set_property", "attach_script":
			return str(op.get("node", ""))
		"connect_signal":
			return str(op.get("from", ""))
	return null


func _preview(op: Dictionary) -> String:
	match str(op.get("op", "")):
		"add_node":
			return "%s -> %s (%s)" % [str(op.get("parent", "")), str(op.get("name", "")),
				str(op.get("type", ""))]
		"set_property":
			return "%s.%s = %s" % [str(op.get("node", "")), str(op.get("property", "")),
				_canon(op.get("value"))]
		"attach_script":
			return "%s: скрипт %s" % [str(op.get("node", "")), str(op.get("script", ""))]
		"connect_signal":
			return "%s.%s -> %s.%s" % [str(op.get("from", "")), str(op.get("signal", "")),
				str(op.get("to", "")), str(op.get("method", ""))]
	return str(op.get("op", ""))
