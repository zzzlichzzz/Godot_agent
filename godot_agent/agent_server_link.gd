@tool
extends Node
# agent_server_link.gd — вся связь панели с локальным сервером (v16).
# Здесь живут: очередь запросов /chats/*, /sites/*, /browser/status,
# различие «сервер занят» / «сервер не запущен», автозапуск
# godot_agent_server.exe (с кулдауном от лишних окон), ожидание старта
# и повтор отложенного действия пользователя.
#
# Панель (agent_panel.gd) общается с этим узлом только так:
#   request(kind, extra)              — отправить запрос серверу;
#   is_inflight()                     — идёт ли сейчас запрос;
# сигналы:
#   chats_response(kind, json, extra) — успешный ответ (весь UI рисует панель);
#   link_status(text, kind)           — статус/ошибка/успех (панель -> _notify);
#   show_loading_requested(text)      — показать экран загрузки;
#   hide_loading_requested()          — скрыть экран загрузки, если показан.

signal chats_response(kind: String, json: Dictionary, extra: Dictionary)
signal link_status(text: String, kind: String)
signal show_loading_requested(text: String)
signal hide_loading_requested()
signal server_state_changed(running: bool)

const HOST = "127.0.0.1:5000"
const CHATS_LIST_URL = "http://" + HOST + "/chats/list"
const CHATS_NEW_URL = "http://" + HOST + "/chats/new"
const CHATS_OPEN_URL = "http://" + HOST + "/chats/open"
const CHATS_RENAME_URL = "http://" + HOST + "/chats/rename"
const CHATS_DELETE_URL = "http://" + HOST + "/chats/delete"
const SITES_LIST_URL = "http://" + HOST + "/sites/list"
const BROWSER_STATUS_URL = "http://" + HOST + "/browser/status"
const MINILICH_STATUS_URL = "http://" + HOST + "/minilich/status"
const MINILICH_SET_URL = "http://" + HOST + "/minilich/set"
const SERVER_PATH_CACHE := "user://godot_agent_server_path.txt"

var _http: HTTPRequest = null
var _inflight: bool = false
var _queue: Array = []
var _kind: String = ""
var _extra: Dictionary = {}
var _autostart_ok: bool = true
var _server_start_attempted: bool = false
var _server_wait_timer: Timer = null
var _server_wait_left: int = 0
var _retry_after_server: Array = []
var _last_server_launch_msec: int = 0
var _loc = null


func _locale():
	if _loc == null:
		var sc := get_script() as Script
		if sc:
			var lp := sc.resource_path.get_base_dir() + "/agent_locale.gd"
			if FileAccess.file_exists(lp):
				_loc = load(lp)
	return _loc


func _t(key: String) -> String:
	var l = _locale()
	if l:
		return l.t(key)
	return key


func _ready() -> void:
	if _http == null:
		_http = HTTPRequest.new()
		_http.timeout = 180.0
		add_child(_http)
		_http.request_completed.connect(_on_response)


func is_inflight() -> bool:
	return _inflight


func request(kind: String, extra: Dictionary, allow_autostart: bool = true) -> void:
	if _http == null:
		return
	# На одном HTTPRequest-узле одновременно может идти только один запрос —
	# остальные ставим в очередь, иначе второй падает с ERR_BUSY.
	if _inflight:
		_queue.append({"kind": kind, "extra": extra, "allow_autostart": allow_autostart})
		return
	_fire(kind, extra, allow_autostart)


func _fire(kind: String, extra: Dictionary, allow_autostart: bool = true) -> void:
	if _http == null:
		return
	var body = {
		"user_data_dir": OS.get_user_data_dir(),
		"project_root": ProjectSettings.globalize_path("res://"),
	}
	for k in extra:
		body[k] = extra[k]
	var url := CHATS_LIST_URL
	match kind:
		"new": url = CHATS_NEW_URL
		"open": url = CHATS_OPEN_URL
		"rename": url = CHATS_RENAME_URL
		"delete": url = CHATS_DELETE_URL
		"sites": url = SITES_LIST_URL
		"status": url = BROWSER_STATUS_URL
		"minilich_status": url = MINILICH_STATUS_URL
		"minilich_set": url = MINILICH_SET_URL
	_kind = kind
	_extra = extra
	_autostart_ok = allow_autostart
	_inflight = true
	_http.set_http_proxy("", 0)
	var err = _http.request(url, ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		_kind = ""
		_inflight = false
		_drain_queue()


func _drain_queue() -> void:
	if _inflight:
		return
	if _queue.is_empty():
		return
	var next = _queue.pop_front()
	_fire(str(next.get("kind", "list")), next.get("extra", {}), bool(next.get("allow_autostart", true)))


func _on_response(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var kind := _kind
	var extra := _extra
	var autostart_ok := _autostart_ok
	_kind = ""
	_extra = {}
	_inflight = false
	_drain_queue()
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		# Таймаут = сервер жив, но занят; остальные ошибки = сервер не отвечает.
		# По этому сигналу панель показывает/прячет кнопку ручного запуска.
		server_state_changed.emit(result == HTTPRequest.RESULT_TIMEOUT)
		if kind == "status":
			return
		if kind == "minilich_status" or kind == "minilich_set":
			# Отдельная ветка: клик по галочке не должен незаметно пытаться
			# автозапускать вторую копию сервера — важнее сразу показать панели
			# ошибку (раньше это молча уходило в автозапуск, и галочка просто
			# зависала в непонятном состоянии).
			chats_response.emit(kind, {"error": _t("srv_no_response") + " (HTTP " + str(response_code) + ")"}, extra)
			return
		if result == HTTPRequest.RESULT_TIMEOUT:
			# Сервер жив, но занят долгой операцией (например, открывает
			# страницу в браузере). НЕ запускаем новые копии сервера.
			hide_loading_requested.emit()
			link_status.emit(_t("srv_busy"), "error")
			return
		if not autostart_ok:
			# Фоновый запрос (авто-обновление списка чатов/сайтов при открытии панели).
			# Не запускаем сервер просто от того, что открылся Godot — только по
			# реальному действию пользователя (новый/открытый чат, отправка сообщения).
			return
		if kind == "new" or kind == "open":
			# Запоминаем действие пользователя и повторим его после запуска сервера.
			_retry_after_server = [{"kind": kind, "extra": extra}]
		_maybe_autostart_server()
		return
	var json = JSON.parse_string(body.get_string_from_utf8())
	if json == null or typeof(json) != TYPE_DICTIONARY:
		return
	server_state_changed.emit(true)
	_on_server_alive()
	chats_response.emit(kind, json, extra)


# ---------------------------------------------------------------------------
# Автозапуск сервера и ожидание его готовности.
# ---------------------------------------------------------------------------

func _maybe_autostart_server() -> void:
	if _server_wait_left > 0:
		link_status.emit(_t("srv_wait_boot"), "status")
		return
	if _last_server_launch_msec > 0 and Time.get_ticks_msec() - _last_server_launch_msec < 10000:
		# Совсем недавно уже запускали exe — не плодим окна сервера.
		# (Раньше здесь была блокировка на 60 с после любой попытки и ВЕЧНАЯ
		# блокировка после неудачного ожидания — из-за них повторные нажатия
		# подолгу «искали» сервер, хотя сам exe стартует быстро.)
		link_status.emit(_t("srv_wait_boot"), "status")
		return
	_server_start_attempted = true
	show_loading_requested.emit(_t("srv_search"))
	link_status.emit(_t("srv_search"), "status")
	var t0 := Time.get_ticks_msec()
	if not _launch_server_process():
		hide_loading_requested.emit()
		link_status.emit(_t("srv_not_found"), "error")
		return
	print("[agent] Поиск и запуск сервера занял %d мс" % (Time.get_ticks_msec() - t0))
	show_loading_requested.emit(_t("srv_start"))
	_last_server_launch_msec = Time.get_ticks_msec()
	link_status.emit(_t("srv_start"), "status")
	# 220 тиков по 0.5 с = 110 с ожидания. Раньше бюджет был 40 с — на медленных
	# машинах (антивирус сканирует распакованный onefile-exe, холодный старт
	# браузера внутри сервера) реальный старт занимал больше минуты, и бюджет
	# заканчивался раньше, чем exe успевал поднять порт — панель показывала ложную
	# ошибку запуска, хотя сервер всё равно бы поднялся через несколько секунд.
	_server_wait_left = 220
	if _server_wait_timer == null:
		_server_wait_timer = Timer.new()
		_server_wait_timer.wait_time = 0.5
		_server_wait_timer.one_shot = false
		add_child(_server_wait_timer)
		_server_wait_timer.timeout.connect(_on_server_wait_tick)
	_server_wait_timer.start()


func _on_server_wait_tick() -> void:
	if _server_wait_left <= 0:
		if _server_wait_timer: _server_wait_timer.stop()
		_server_start_attempted = false  # разрешаем новую попытку запуска следующим кликом
		_last_server_launch_msec = 0
		hide_loading_requested.emit()
		link_status.emit(_t("srv_fail"), "error")
		return
	_server_wait_left -= 1
	link_status.emit(_t("srv_connecting_n") % int(ceil(_server_wait_left * 0.5)), "status")
	if _inflight:
		return
	request("list", {})


func _on_server_alive() -> void:
	# Любой успешный ответ сервера: если ждали запуска — сообщаем, обновляем
	# списки чатов/сайтов и повторяем отложенное действие пользователя.
	if _server_wait_left > 0:
		_server_wait_left = 0
		if _server_wait_timer:
			_server_wait_timer.stop()
		_server_start_attempted = false
		link_status.emit(_t("srv_alive"), "success")
		if _last_server_launch_msec > 0:
			print("[agent] Сервер ответил через %d мс после запуска exe" % (Time.get_ticks_msec() - _last_server_launch_msec))
		request("sites", {})
		request("list", {})
		var pending: Array = _retry_after_server
		_retry_after_server = []
		var replayed := false
		for r in pending:
			if typeof(r) != TYPE_DICTIONARY:
				continue
			var rk := str(r.get("kind", ""))
			if rk != "":
				replayed = true
				link_status.emit(_t("replay_action"), "status")
				request(rk, r.get("extra", {}))
		if not replayed:
			hide_loading_requested.emit()


# ---------------------------------------------------------------------------
# Поиск и запуск godot_agent_server.exe (или python main.py).
# ---------------------------------------------------------------------------

func find_server_exe_path() -> String:
	# Ищет exe сервера БЕЗ запуска — те же шаги, что у _launch_server_process.
	var link_file: String = get_script().resource_path.get_base_dir() + "/server_path.txt"
	if FileAccess.file_exists(link_file):
		var lf := FileAccess.open(link_file, FileAccess.READ)
		if lf != null:
			var manual := lf.get_as_text().strip_edges()
			lf.close()
			if manual != "" and FileAccess.file_exists(manual):
				return manual
	var cached := _prefer_onedir(_load_cached_server_path())
	if cached != "" and FileAccess.file_exists(cached):
		return cached
	var priority_paths: Array = [
		ProjectSettings.globalize_path("res://addons/Godot_agent/godot_agent/python/dist/godot_agent_server/godot_agent_server.exe"),
		ProjectSettings.globalize_path("res://addons/godot_agent/python/dist/godot_agent_server/godot_agent_server.exe"),
		ProjectSettings.globalize_path("res://addons/Godot_agent/godot_agent/python/dist/godot_agent_server.exe"),
		ProjectSettings.globalize_path("res://addons/godot_agent/python/dist/godot_agent_server.exe"),
	]
	for pth in priority_paths:
		if FileAccess.file_exists(String(pth)):
			return String(pth)
	var addons_root := ProjectSettings.globalize_path("res://addons")
	var exe := _prefer_onedir(_find_server_file(addons_root, "godot_agent_server.exe", 0))
	if exe != "":
		return exe
	var project_root := ProjectSettings.globalize_path("res://")
	for n in ["dist/godot_agent_server/godot_agent_server.exe", "python/dist/godot_agent_server/godot_agent_server.exe", "godot_agent_server.exe", "server/godot_agent_server.exe", "dist/godot_agent_server.exe", "python/dist/godot_agent_server.exe"]:
		var p: String = project_root.path_join(String(n))
		if FileAccess.file_exists(p):
			return p
	return ""


func open_server_folder() -> String:
	# Открывает проводник на папке с exe сервера (в Godot 4.2+ файл будет
	# сразу выделен). Возвращает найденный путь или "".
	var exe := find_server_exe_path()
	if exe == "":
		return ""
	if OS.has_method("shell_show_in_file_manager"):
		# Вызов через call(), чтобы скрипт парсился и на Godot < 4.2.
		OS.call("shell_show_in_file_manager", exe, true)
	else:
		OS.shell_open(exe.get_base_dir())
	return exe


func _load_cached_server_path() -> String:
	# Запомненный ранее успешный путь к exe (если раньше нашли его только после полного поиска по addons/).
	if not FileAccess.file_exists(SERVER_PATH_CACHE):
		return ""
	var f := FileAccess.open(SERVER_PATH_CACHE, FileAccess.READ)
	if f == null:
		return ""
	var p := f.get_as_text().strip_edges()
	f.close()
	return p


func _save_cached_server_path(path: String) -> void:
	var f := FileAccess.open(SERVER_PATH_CACHE, FileAccess.WRITE)
	if f == null:
		return
	f.store_string(path)
	f.close()


func _prefer_onedir(path: String) -> String:
	# Если рядом со старым одиночным exe появилась быстрая onedir-сборка —
	# запускаем её: старый onefile распаковывается при КАЖДОМ старте 10-30 с.
	if path == "" or not path.ends_with("godot_agent_server.exe"):
		return path
	var candidate := path.get_base_dir().path_join("godot_agent_server/godot_agent_server.exe")
	if FileAccess.file_exists(candidate):
		return candidate
	return path


func _launch_server_process() -> bool:
	# -1) Файл-ссылка: server_path.txt рядом с аддоном, внутри — полный путь к exe.
	#     Позволяет указать сервер вручную и вообще не искать его по папкам.
	var link_file: String = get_script().resource_path.get_base_dir() + "/server_path.txt"
	if FileAccess.file_exists(link_file):
		var lf := FileAccess.open(link_file, FileAccess.READ)
		if lf != null:
			var manual := lf.get_as_text().strip_edges()
			lf.close()
			if manual != "" and FileAccess.file_exists(manual):
				var pidm := OS.create_process(manual, [], true)
				if pidm > 0:
					print("[agent] Запустил сервер (по server_path.txt): " + manual)
					return true
				print("[agent] server_path.txt: не удалось запустить " + manual)
			elif manual != "":
				print("[agent] server_path.txt указывает на несуществующий файл: " + manual)
	# 0) Сначала пробуем запомненное расположение exe — это быстрее всего.
	var cached := _prefer_onedir(_load_cached_server_path())
	if cached != "" and FileAccess.file_exists(cached):
		var pidc := OS.create_process(cached, [], true)
		if pidc > 0:
			print("[agent] Запустил сервер (по запомненному ранее пути): " + cached)
			_save_cached_server_path(cached)  # путь мог обновиться на быструю onedir-сборку
			return true

	# 1) Два самых типовых расположения exe — мгновенно, без обхода папок.
	var priority_paths: Array = [
		# Новая быстрая сборка (onedir — exe внутри папки, стартует за 1-2 с):
		ProjectSettings.globalize_path("res://addons/Godot_agent/godot_agent/python/dist/godot_agent_server/godot_agent_server.exe"),
		ProjectSettings.globalize_path("res://addons/godot_agent/python/dist/godot_agent_server/godot_agent_server.exe"),
		# Старая сборка одним файлом (медленный старт, но поддерживаем):
		ProjectSettings.globalize_path("res://addons/Godot_agent/godot_agent/python/dist/godot_agent_server.exe"),
		ProjectSettings.globalize_path("res://addons/godot_agent/python/dist/godot_agent_server.exe"),
	]
	for pth in priority_paths:
		if FileAccess.file_exists(String(pth)):
			var pid0 := OS.create_process(String(pth), [], true)
			if pid0 > 0:
				print("[agent] Запустил сервер: " + String(pth))
				_save_cached_server_path(String(pth))
				return true

	# 2) Не нашли по типовым путям — рекурсивно ищем по всей папке addons/ (любые имена папок).
	var addons_root := ProjectSettings.globalize_path("res://addons")
	var exe := _prefer_onedir(_find_server_file(addons_root, "godot_agent_server.exe", 0))
	if exe != "":
		var pid := OS.create_process(exe, [], true)
		if pid > 0:
			print("[agent] Запустил сервер: " + exe)
			_save_cached_server_path(exe)
			return true

	# 3) Корень проекта — частые ручные расположения.
	var project_root := ProjectSettings.globalize_path("res://")
	for n in ["dist/godot_agent_server/godot_agent_server.exe", "python/dist/godot_agent_server/godot_agent_server.exe", "godot_agent_server.exe", "server/godot_agent_server.exe", "dist/godot_agent_server.exe", "python/dist/godot_agent_server.exe"]:
		var p: String = project_root.path_join(String(n))
		if FileAccess.file_exists(p):
			var pid2 := OS.create_process(p, [], true)
			if pid2 > 0:
				print("[agent] Запустил сервер: " + p)
				_save_cached_server_path(p)
				return true

	# 4) Последний вариант — python main.py (сначала в addons/, потом в корне).
	var py_path := _find_server_file(addons_root, "main.py", 0)
	if py_path == "":
		for n2 in ["python/main.py", "server/main.py", "main.py"]:
			var p2: String = project_root.path_join(String(n2))
			if FileAccess.file_exists(p2):
				py_path = p2
				break
	if py_path != "":
		for interp in ["python", "py"]:
			var pid3 := OS.create_process(interp, [py_path], true)
			if pid3 > 0:
				print("[agent] Запустил сервер: " + str(interp) + " " + py_path)
				return true
	return false


func _find_server_file(dir_path: String, file_name: String, depth: int) -> String:
	# Рекурсивный поиск файла (пропускаем скрытые папки, __pycache__ и build).
	if depth > 6:
		return ""
	var dir := DirAccess.open(dir_path)
	if dir == null:
		return ""
	var subdirs: Array = []
	dir.list_dir_begin()
	var entry := dir.get_next()
	while entry != "":
		if dir.current_is_dir():
			if not entry.begins_with(".") and entry != "__pycache__" and entry != "build":
				subdirs.append(dir_path + "/" + entry)
		elif entry == file_name:
			dir.list_dir_end()
			return dir_path + "/" + entry
		entry = dir.get_next()
	dir.list_dir_end()
	for sd in subdirs:
		var found := _find_server_file(String(sd), file_name, depth + 1)
		if found != "":
			return found
	return ""
