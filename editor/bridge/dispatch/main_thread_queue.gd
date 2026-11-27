# editor/bridge/dispatch/main_thread_queue.gd - очередь выполнения в главном потоке.
# Очередь вызовов в главном потоке: сцена и выделение читаются только из него
# (`EditorInterface` не потокобезопасен). Сокет читает сессия, а исполняет - эта
# очередь через `call_deferred` (R-14: транспорт отдельно от смысла).
extends Node

var _pending: Array[Callable] = []
var _scheduled := false


func push(work: Callable) -> void:
	_pending.append(work)
	if not _scheduled:
		_scheduled = true
		call_deferred("_flush")


func pending() -> int:
	return _pending.size()


func _flush() -> void:
	_scheduled = false
	while not _pending.is_empty():
		var work: Callable = _pending.pop_front()
		work.call()
