@tool
extends RefCounted

# ============================================================================
# EDITOR SIGNALS — подписка на публичные сигналы редактора.
#
# Зачем этот файл существует. Плагин реагировал на изменения проекта,
# подписываясь на внутренние детали редактора: FileSystemDock искался
# поиском через EditorInterface.get_file_system_dock(), а ScriptEditor
# брался напрямую. Это хрупко — внутренности меняются между версиями
# движка, и поломка выглядит как «агент перестал видеть проект».
#
# Сигналы EditorPlugin — публичный контракт Godot. Здесь все шесть
# подписок собраны в одном месте, с честной отпиской.
#
# Арность обработчика обязана совпадать с сигнатурой сигнала.
# Реальные подписи, снятые с живого экземпляра Godot 4.6.3:
#   script_changed()            — 0 аргументов
#   scene_changed(root: Node)   — 1
#   scene_saved(path: String)   — 1
#   resource_saved(res: Resource) — 1
#   project_settings_changed()  — 0
#   editor_state_changed()      — 0
#
# Лишний параметр не даёт ошибки при подписке — она проходит молча.
# Ошибка всплывает только при первом же emit, в рантайме:
#   "Method expected 1 argument(s), but called with 0."
# Поэтому подписи ниже выровнены по факту, а не по памяти.
#
# Поведение обработчиков впереди: подписка появилась, логика — позже.
# Здесь нет вызовов логики панели, и добавлять её сюда не нужно.
# ============================================================================

## Подписки как пары «сигнал → callable»: без них отписка невозможна,
## а временный Callable теряется вместе с выражением.
var _subscriptions: Array[Dictionary] = []

## ЗАДАЧА 3: перехват переименования узлов человеком. Сигнал Node.renamed не
## несёт прежнего имени (проверено: 0 аргументов), поэтому держим снимок
## {instance_id: имя} каждого узла открытой сцены. Подписки на самих узлах
## нужны для честной отписки при смене сцены.
var _node_handler: Callable = Callable()
var _node_names: Dictionary = {}
var _node_subscriptions: Array[Dictionary] = []

var _plugin: EditorPlugin = null


## Конструктор только запоминает плагина. Подписка начинается в attach() —
## вызов делает владелец в _enter_tree(), иначе «подписка появилась»
## зависела бы от порядка строк в конструкторе.
func _init(plugin: EditorPlugin) -> void:
	_plugin = plugin


## Подписаться. Повторный вызов ничего не меняет: подписка одна и та же.
func attach() -> void:
	if _plugin == null or not _subscriptions.is_empty():
		return
	_bind(_plugin.script_changed, _on_script_changed)
	_bind(_plugin.scene_changed, _on_scene_changed)
	_bind(_plugin.scene_saved, _on_scene_saved)
	_bind(_plugin.resource_saved, _on_resource_saved)
	_bind(_plugin.project_settings_changed, _on_project_settings_changed)
	_bind(_plugin.editor_state_changed, _on_editor_state_changed)
	# Сцена могла быть открыта ДО загрузки плагина: до первого scene_changed
	# снимок имён обязан существовать, иначе первое переименование узла
	# останется незамеченным.
	_on_scene_changed(_edited_scene_root())


## Отписаться. Повторный вызов безопасен.
func detach() -> void:
	for subscription in _subscriptions:
		# Имена `signal` и `object` зарезервированы в GDScript — переменная
		# с таким именем не проходит даже парсер, поэтому здесь `source`.
		var source: Signal = subscription["signal"]
		var handler: Callable = subscription["callable"]
		if source.is_connected(handler):
			source.disconnect(handler)
	_subscriptions.clear()
	_clear_node_watch()


## Сколько подписок держится сейчас. Нужно проверкам и отладке.
func subscription_count() -> int:
	return _subscriptions.size()


func _bind(source: Signal, handler: Callable) -> void:
	if source.is_connected(handler):
		return
	source.connect(handler)
	_subscriptions.append({"signal": source, "callable": handler})


# --- Обработчики сигналов редактора -----------------------------------------
# Подписка появилась, поведение — впереди: каждая функция ниже это точная
# точка, где в будущем инвалидируется то, что могло устареть.

func _on_script_changed() -> void:
	pass


func _on_scene_changed(root: Node) -> void:
	# ЗАДАЧА 3: снимок имён открытой сцены. Пересобирается целиком: узлы
	# прошлой сцены больше не наблюдаются, их объекты могут жить дальше.
	_clear_node_watch()
	if root == null:
		return
	_watch_node(root)
	for child in root.get_children(true):
		_watch_node(child)


# --- ЗАДАЧА 3: перехват переименования узлов человеком -----------------------

## Обработчик панели: (scene_path, old_node_path, old_name, new_name).
func set_node_rename_handler(handler: Callable) -> void:
	_node_handler = handler


func _watch_node(node: Node) -> void:
	if node == null:
		return
	_node_names[node.get_instance_id()] = str(node.name)
	var renamed_cb := _on_node_renamed.bind(node)
	var exiting_cb := _on_node_tree_exiting.bind(node)
	if not node.renamed.is_connected(renamed_cb):
		node.renamed.connect(renamed_cb)
	if not node.tree_exiting.is_connected(exiting_cb):
		node.tree_exiting.connect(exiting_cb)
	_node_subscriptions.append({"signal": node.renamed, "callable": renamed_cb})
	_node_subscriptions.append({"signal": node.tree_exiting, "callable": exiting_cb})


func _clear_node_watch() -> void:
	for subscription in _node_subscriptions:
		var source: Signal = subscription["signal"]
		var handler: Callable = subscription["callable"]
		if source.is_connected(handler):
			source.disconnect(handler)
	_node_subscriptions.clear()
	_node_names.clear()


func _on_node_tree_exiting(node: Node) -> void:
	# Узел покидает сцену: карта не должна расти и держать имена мёртвых
	# узлов. Сами подписки снимет объект при освобождении.
	if node == null:
		return
	_node_names.erase(node.get_instance_id())


func _on_node_renamed(node: Node) -> void:
	if node == null or not is_instance_valid(node):
		return
	var id := node.get_instance_id()
	var old_name := str(_node_names.get(id, ""))
	var new_name := str(node.name)
	_node_names[id] = new_name
	if old_name.is_empty() or old_name == new_name:
		return
	if not _node_handler.is_valid():
		return
	var root := _edited_scene_root()
	if root == null or not (node == root or root.is_ancestor_of(node)):
		return
	var scene_path := str(root.scene_file_path)
	if scene_path.is_empty():
		return
	var new_path := str(root.get_path_to(node))
	var slash := new_path.rfind("/")
	var old_path := (new_path.substr(0, slash + 1) + old_name) if slash >= 0 else old_name
	_node_handler.call(scene_path, old_path, old_name, new_name)


func _edited_scene_root() -> Node:
	if _plugin == null:
		return null
	var interface := _plugin.get_editor_interface()
	return interface.get_edited_scene_root() if interface != null else null


func _on_scene_saved(_path: String) -> void:
	pass


func _on_resource_saved(_resource: Resource) -> void:
	pass


func _on_project_settings_changed() -> void:
	pass


func _on_editor_state_changed() -> void:
	pass