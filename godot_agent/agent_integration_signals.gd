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


func _on_scene_changed(_root: Node) -> void:
	pass


func _on_scene_saved(_path: String) -> void:
	pass


func _on_resource_saved(_resource: Resource) -> void:
	pass


func _on_project_settings_changed() -> void:
	pass


func _on_editor_state_changed() -> void:
	pass