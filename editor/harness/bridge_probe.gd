# editor/harness/bridge_probe.gd - живой прогон моста без редактора (needs_live).
# Поднимает настоящий `socket_server.gd` (тот же код, что в редакторе), ждёт клиента,
# отвечает на три примитива, пишет `user://godot_agent/harness_result.json` и выходит.
#
# Приёмка — pytest, потому что клиент приходит снаружи:
#   python -m pytest tests/py/live -v     (тест сам поднимает харнесс и зовёт примитивы)
# Одиночный запуск харнесс только слушает и по таймауту честно пишет
# `ok:false / failure.reason = "no_client"` (exit 1) — это норма, а не провал моста:
#   godot --headless --path <проект> -s res://addons/godot_agent/editor/harness/bridge_probe.gd
# Таймаут можно сократить переменной окружения `HARNESS_TIMEOUT_MS` (нужно тесту).
# Правила: R-14 (харнесс ничего не решает), R-22 (доказательство - вывод).
extends SceneTree

const SocketServerScript := preload("res://addons/godot_agent/editor/bridge/server/socket_server.gd")
const RouterScript := preload("res://addons/godot_agent/editor/bridge/dispatch/router.gd")
const DispatcherScript := preload("res://addons/godot_agent/editor/bridge/dispatch/dispatcher.gd")
const VerbsScript := preload("res://addons/godot_agent/editor/bridge/verbs/editors/editor_verbs.gd")
const SessionScript := preload("res://addons/godot_agent/editor/bridge/server/session.gd")

const RESULT := "user://godot_agent/harness_result.json"
const TIMEOUT_MS := 20000
const TIMEOUT_ENV := "HARNESS_TIMEOUT_MS"
const EXPECTED := 3
const NO_CLIENT_HINT := "клиент не подключался: приёмка - `python -m pytest tests/py/live -v`; либо подключись `EditorClient` к порту из BRIDGE_PORT"


class Recorder extends RefCounted:
	# Оборачивает диспетчер: харнесс должен знать, какие примитивы реально обслужены.
	var inner
	var seen: Dictionary = {}

	func _init(dispatcher) -> void:
		inner = dispatcher

	func handle(request: Dictionary) -> Dictionary:
		var answer = inner.handle(request)
		seen[str(request.get("verb", ""))] = answer
		return answer

	func verbs() -> Array:
		return inner.verbs()


var _server
var _recorder
var _scan: Dictionary = {}
var _started := false
var _done := false
var _start_ms := 0
var _timeout_ms := TIMEOUT_MS


func _init() -> void:
	_start_ms = Time.get_ticks_msec()
	_timeout_ms = _timeout_from_env()
	process_frame.connect(_tick)


func _timeout_from_env() -> int:
	# Одиночный прогон в тесте не должен ждать 20 с: `HARNESS_TIMEOUT_MS=1200`.
	var raw := OS.get_environment(TIMEOUT_ENV)
	if raw.is_valid_int():
		return maxi(100, int(raw))
	return TIMEOUT_MS


func _tick() -> void:
	if _done:
		return
	if not _started:
		_start()
		return
	if _recorder.seen.size() >= EXPECTED:
		_finish(true, {})
		return
	if Time.get_ticks_msec() - _start_ms > _timeout_ms:
		var served: Array = _recorder.seen.keys()
		if served.is_empty():
			# Одиночный запуск: клиента не было вовсе. Это не «мост молчал», а
			# «некому было спросить» — причина называется честно.
			_finish(false, {"reason": "no_client", "served": [],
				"hint": NO_CLIENT_HINT})
		else:
			_finish(false, {"reason": "timeout", "served": served,
				"hint": "клиент позвал %d из %d примитивов" % [served.size(), EXPECTED]})
		return


func _start() -> void:
	_started = true
	var scan := _scan_scripts()
	_scan = scan
	var router = RouterScript.new()
	VerbsScript.new().register(router)
	_recorder = Recorder.new(DispatcherScript.new(router))
	_server = SocketServerScript.new()
	get_root().add_child(_server)
	var started: Dictionary = _server.start(_recorder)
	if not bool(started.get("ok", false)):
		_finish(false, {"reason": "listen_failed", "detail": started})
		return
	print("BRIDGE_PORT %s" % JSON.stringify({
		"port": int(started.get("port", 0)), "token": str(_server.token()),
		"result": ProjectSettings.globalize_path(RESULT),
		"verbs": router.verbs(), "scripts": scan}))


func _scan_scripts() -> Dictionary:
	# Мост обязан компилироваться целиком, а не только теми файлами, что тянет
	# сервер. Битым считается и `load() == null`, и скрипт, который грузится, но не
	# инстанцируется (`can_instantiate() == false`): parse-ошибка объект не роняет,
	# поэтому прежняя проверка молчала о дефекте D-1.
	var broken: Array = []
	var total := 0
	var stack: Array = ["res://addons/godot_agent/editor"]
	while not stack.is_empty():
		var here: String = stack.pop_back()
		var dir := DirAccess.open(here)
		if dir == null:
			continue
		for name in dir.get_directories():
			stack.append(here.path_join(str(name)))
		for name in dir.get_files():
			if not str(name).ends_with(".gd"):
				continue
			total += 1
			var script_path := here.path_join(str(name))
			var script = load(script_path)
			if script == null or not script.can_instantiate():
				broken.append(script_path)
	return {"total": total, "broken": broken}


func _finish(ok: bool, extra: Dictionary) -> void:
	if _done:
		return
	_done = true
	# Версия словаря - из сервера (`session.gd`): harness_result.json не должен
	# врать о версии моста (B.1).
	var payload := {"ok": ok, "verbs": {}, "protocol": 1,
			"verbs_version": SessionScript.VERBS_VERSION}
	for verb in _recorder.seen.keys():
		payload["verbs"][verb] = _recorder.seen[verb]
	payload["scripts"] = _scan
	payload["engine"] = str(Engine.get_version_info().get("string", "4"))
	payload["editor_available"] = Engine.is_editor_hint()
	payload["elapsed_s"] = float(Time.get_ticks_msec() - _start_ms) / 1000.0
	if not extra.is_empty():
		payload["failure"] = extra
	if not bool(_scan.get("broken", []).is_empty()):
		payload["ok"] = false
	DirAccess.make_dir_recursive_absolute(
		ProjectSettings.globalize_path("user://godot_agent"))
	var handle := FileAccess.open(RESULT, FileAccess.WRITE)
	if handle != null:
		handle.store_string(JSON.stringify(payload))
		handle.close()
	print("BRIDGE_RESULT %s" % JSON.stringify(payload))
	_server.stop()
	quit(0 if bool(payload["ok"]) else 1)
