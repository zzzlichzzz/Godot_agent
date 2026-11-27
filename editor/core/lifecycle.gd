# editor/core/lifecycle.gd - жизненный цикл плагина: старт и стоп моста.
# Правила: R-14 (мост - руки, не голова), R-11 (редактор не знает про домен).
# Один экземпляр: повторный `start()` возвращает уже поднятый сервер, второй
# слушающий сокет не создаётся (SEC-03). Адрес, токен и `port.json` - целиком
# в `bridge/server/socket_server.gd`; здесь только жизненный цикл.
@tool
extends Node

const SocketServerScript := preload("res://addons/godot_agent/editor/bridge/server/socket_server.gd")

var _server = null


func start() -> Dictionary:
	if _server != null:
		return {"ok": true, "port": int(_server.port()), "reused": true}
	_server = SocketServerScript.new()
	add_child(_server)
	var started: Dictionary = _server.start()
	if not bool(started.get("ok", false)):
		_server.queue_free()
		_server = null
		return started
	print("godot_agent: bridge on 127.0.0.1:%d" % int(started.get("port", 0)))
	return started


func stop() -> void:
	if _server == null:
		return
	_server.stop()
	_server.queue_free()
	_server = null


func port() -> int:
	return 0 if _server == null else int(_server.port())


func running() -> bool:
	return _server != null

