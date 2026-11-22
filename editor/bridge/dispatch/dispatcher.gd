# editor/bridge/dispatch/dispatcher.gd - приём примитива и передача исполнителю.
# Приём примитива и вызов обработчика: единственное место, где решается
# «неизвестный примитив», «не тот аргумент» и «обработчик упал».
@tool
extends RefCounted

const ErrorCodes := preload("error_codes.gd")

var _router


func _init(router) -> void:
	_router = router


func handle(request: Dictionary) -> Dictionary:
	var verb := str(request.get("verb", ""))
	if not _router.has(verb):
		return ErrorCodes.payload(ErrorCodes.UNKNOWN_VERB,
			"мост не знает примитив %s" % verb)
	var args = request.get("args", {})
	if typeof(args) != TYPE_DICTIONARY:
		args = {}
	var result = _router.handler(verb).call(args)
	if typeof(result) != TYPE_DICTIONARY:
		return ErrorCodes.payload(ErrorCodes.TRUNCATED,
			"обработчик %s вернул не словарь" % verb)
	return result


func verbs() -> Array:
	return _router.verbs()
