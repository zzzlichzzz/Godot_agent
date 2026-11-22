# editor/bridge/dispatch/router.gd - таблица primitive -> обработчик.
# Таблица «примитив → обработчик». Имена примитивов приходят из словаря
# `contract/editor_verbs.json`; обработчики объявляют себя маркером `# verb:`.
@tool
extends RefCounted

var _table: Dictionary = {}
var _owners: Array = []


func register(verb: String, handler: Callable) -> void:
	_table[verb] = handler
	# `Callable` не держит владельца-`RefCounted`: без явной ссылки обработчик
	# `editor_verbs.gd` освобождается и при вызове становится `null`
	# («Attempt to call function 'null::ping'» — поймано живым прогоном A.1).
	var owner = handler.get_object()
	if owner != null and not _owners.has(owner):
		_owners.append(owner)


func has(verb: String) -> bool:
	return _table.has(verb)


func handler(verb: String) -> Callable:
	return _table.get(verb, Callable())


func verbs() -> Array:
	var names := _table.keys()
	names.sort()
	return names
