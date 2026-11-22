# editor/bridge/server/socket_server.gd - приём соединений от Python-части.
# Приём соединений: TCPServer на 127.0.0.1, случайный порт, `port.json` для Python
# (ADR-0007). Слушает только редактор: второй слушающий сокет запрещён (SEC-03).
@tool
extends Node

const HOST := "127.0.0.1"
const DIR := "user://godot_agent"
const PORT_FILE := "user://godot_agent/port.json"

const SessionScript := preload("session.gd")
const EndpointsScript := preload("endpoints.gd")

var _server := TCPServer.new()
var _sessions: Array = []
var _dispatcher
var _token := ""
var _port := 0


func start(custom_dispatcher = null) -> Dictionary:
	# `custom_dispatcher` нужен только харнессу (`editor/harness/bridge_probe.gd`):
	# он оборачивает диспетчер и записывает, какие примитивы реально обслужены.
	if _server.is_listening():
		return {"ok": true, "port": _port}
	var err := _server.listen(0, HOST)
	if err != OK:
		return {"ok": false, "reason": "listen_failed", "message": "listen: %d" % err}
	_port = _server.get_local_port()
	_token = Crypto.new().generate_random_bytes(16).hex_encode()
	_dispatcher = (custom_dispatcher if custom_dispatcher != null
		else EndpointsScript.build()["dispatcher"])
	_write_port_file()
	set_process(true)
	return {"ok": true, "port": _port}


func stop() -> void:
	for session in _sessions:
		session.close()
	_sessions = []
	if _server.is_listening():
		_server.stop()
	if FileAccess.file_exists(PORT_FILE):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(PORT_FILE))


func port() -> int:
	return _port


func token() -> String:
	# Нужен только харнессу (`editor/harness/bridge_probe.gd`): клиент берёт токен
	# из `port.json`, а проба печатает его в stdout для Python-теста.
	return _token


func _process(_delta: float) -> void:
	while _server.is_connection_available():
		var peer := _server.take_connection()
		if peer == null:
			break
		_sessions.append(SessionScript.new(peer, _token, _dispatcher))
	var alive: Array = []
	for session in _sessions:
		if session.poll():
			alive.append(session)
	_sessions = alive


func _write_port_file() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(DIR))
	var handle := FileAccess.open(PORT_FILE, FileAccess.WRITE)
	if handle == null:
		return
	handle.store_string(JSON.stringify({"port": _port, "token": _token,
		"pid": OS.get_process_id(), "protocol": 1, "verbs_version": 3}))
	handle.close()


func _exit_tree() -> void:
	stop()
