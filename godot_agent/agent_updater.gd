@tool
extends Node

# agent_updater.gd — менеджер проверки и автоматического обновления Godot Agent.
#
# Возможности:
# 1. Проверка наличия новых релизов через GitHub Releases API (с кэшированием на 24 часа).
# 2. Сравнение версий по SemVer (0.8.0 > 0.7.0).
# 3. Скачивание zip-архива обновления в user://.
# 4. Проверка целостности через ZIPReader и безопасная распаковка поверх аддона.
# 5. Остановка локального сервера (освобождение блокировок файлов на Windows).
# 6. Запрос перезапуска редактора через EditorInterface.restart_editor(true).

signal update_available(info: Dictionary)
signal update_progress(phase: String, current: int, total: int)
signal update_completed(restart_needed: bool)
signal update_error(message: String)
signal check_completed(has_update: bool, info: Dictionary)

const REPO := "zzzlichzzz/Godot_agent"
const DEFAULT_API_URL := "https://api.github.com/repos/zzzlichzzz/Godot_agent/releases/latest"
const CACHE_FILE := "user://godot_agent_update_check.json"
const TEMP_ZIP_FILE := "user://godot_agent_update_temp.zip"
const CACHE_TTL_SECONDS := 86400 # 24 часа

var releases_url: String = DEFAULT_API_URL
var _check_http: HTTPRequest = null
var _download_http: HTTPRequest = null
var _progress_timer: Timer = null
var _is_force_check: bool = false
var _is_checking: bool = false
var _is_updating: bool = false
var _latest_release_info: Dictionary = {}


func _ready() -> void:
	_ensure_nodes()


func _ensure_nodes() -> void:
	if _check_http == null:
		_check_http = HTTPRequest.new()
		_check_http.name = "CheckHTTP"
		_check_http.timeout = 10.0
		add_child(_check_http)
		_check_http.request_completed.connect(_on_check_completed)
	if _download_http == null:
		_download_http = HTTPRequest.new()
		_download_http.name = "DownloadHTTP"
		_download_http.timeout = 120.0
		add_child(_download_http)
		_download_http.request_completed.connect(_on_download_completed)
	if _progress_timer == null:
		_progress_timer = Timer.new()
		_progress_timer.name = "ProgressTimer"
		_progress_timer.wait_time = 0.15
		_progress_timer.one_shot = false
		add_child(_progress_timer)
		_progress_timer.timeout.connect(_on_progress_tick)


static func parse_semver(v_str: String) -> Array[int]:
	var cleaned := v_str.strip_edges()
	while cleaned.begins_with("v") or cleaned.begins_with("V"):
		cleaned = cleaned.substr(1)
	var dash_idx := cleaned.find("-")
	if dash_idx != -1:
		cleaned = cleaned.substr(0, dash_idx)
	var plus_idx := cleaned.find("+")
	if plus_idx != -1:
		cleaned = cleaned.substr(0, plus_idx)
	var parts := cleaned.split(".")
	var res: Array[int] = [0, 0, 0]
	for i in range(mini(parts.size(), 3)):
		res[i] = parts[i].to_int()
	return res


static func is_version_newer(current_ver: String, remote_ver: String) -> bool:
	var cur := parse_semver(current_ver)
	var rem := parse_semver(remote_ver)
	for i in range(3):
		if rem[i] > cur[i]:
			return true
		elif rem[i] < cur[i]:
			return false
	return false


func get_current_version() -> String:
	var self_script: Script = get_script() as Script
	var base: String = String(self_script.resource_path if self_script else "").get_base_dir()
	var cfg_path: String = base + "/plugin.cfg"
	if FileAccess.file_exists(cfg_path):
		var cf := ConfigFile.new()
		if cf.load(cfg_path) == OK:
			var ver: String = cf.get_value("plugin", "version", "")
			if ver != "":
				return ver
	return "0.7.0"


func check_for_updates(force: bool = false) -> void:
	if _is_checking:
		return
	_is_force_check = force
	_ensure_nodes()
	if not force:
		if FileAccess.file_exists(CACHE_FILE):
			var f := FileAccess.open(CACHE_FILE, FileAccess.READ)
			if f:
				var text := f.get_as_text()
				f.close()
				var parsed = JSON.parse_string(text)
				if parsed is Dictionary:
					var last_ts: int = parsed.get("last_check_timestamp", 0)
					var cur_ts: int = int(Time.get_unix_time_from_system())
					if cur_ts - last_ts < CACHE_TTL_SECONDS and last_ts > 0:
						var cached_ver: String = parsed.get("version", "")
						_latest_release_info = parsed
						if is_version_newer(get_current_version(), cached_ver):
							update_available.emit(parsed)
							check_completed.emit(true, parsed)
						else:
							check_completed.emit(false, parsed)
						return

	_is_checking = true
	var headers := PackedStringArray([
		"User-Agent: Godot-Agent-Updater",
		"Accept: application/vnd.github.v3+json"
	])
	var err := _check_http.request(releases_url, headers, HTTPClient.METHOD_GET)
	if err != OK:
		_is_checking = false
		if _is_force_check:
			update_error.emit("Failed to send update check request: " + str(err))
		check_completed.emit(false, {})


func _on_check_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_is_checking = false
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
		if _is_force_check:
			var err_detail := ""
			if result != HTTPRequest.RESULT_SUCCESS:
				match result:
					HTTPRequest.RESULT_CANT_RESOLVE:
						err_detail = "Не удалось разрешить адрес сервера (DNS)"
					HTTPRequest.RESULT_CANT_CONNECT:
						err_detail = "Не удалось подключиться к серверу (нет связи)"
					HTTPRequest.RESULT_TLS_HANDSHAKE_ERROR:
						err_detail = "Ошибка TLS/SSL сертификата"
					HTTPRequest.RESULT_TIMEOUT:
						err_detail = "Превышено время ожидания ответа"
					_:
						err_detail = "Сетевая ошибка (код %d)" % result
			elif response_code == 404:
				err_detail = "Релизы не найдены на GitHub (HTTP 404)"
			elif response_code == 403:
				err_detail = "Превышен лимит запросов к GitHub API (HTTP 403)"
			else:
				err_detail = "HTTP %d" % response_code
			update_error.emit(err_detail)
		check_completed.emit(false, {})
		return

	var text := body.get_string_from_utf8()
	var json = JSON.parse_string(text)
	if not (json is Dictionary):
		if _is_force_check:
			update_error.emit("Некорректный ответ от сервера релизов (JSON)")
		check_completed.emit(false, {})
		return

	var tag_name: String = json.get("tag_name", "")
	var clean_ver := tag_name
	while clean_ver.begins_with("v") or clean_ver.begins_with("V"):
		clean_ver = clean_ver.substr(1)
	var html_url: String = json.get("html_url", "")
	var release_body: String = json.get("body", "")
	var published_at: String = json.get("published_at", "")
	var download_url: String = ""

	# Ищем .zip среди прикрепленных ассетов
	var assets = json.get("assets", [])
	if assets is Array:
		for a in assets:
			if a is Dictionary:
				var aname: String = a.get("name", "")
				if aname.ends_with(".zip"):
					download_url = a.get("browser_download_url", "")
					break

	if download_url == "":
		download_url = json.get("zipball_url", "")

	var info: Dictionary = {
		"version": clean_ver,
		"tag": tag_name,
		"html_url": html_url,
		"body": release_body,
		# Готовая разметка для панели. body остаётся как есть: он же уходит в
		# кэш и может пригодиться там, где нужен исходный Markdown.
		"notes": markdown_to_bbcode(release_body),
		"download_url": download_url,
		"published_at": published_at,
		"last_check_timestamp": int(Time.get_unix_time_from_system())
	}

	# Сохраняем в кэш
	var f := FileAccess.open(CACHE_FILE, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(info, "  "))
		f.close()

	_latest_release_info = info
	if is_version_newer(get_current_version(), clean_ver):
		update_available.emit(info)
		check_completed.emit(true, info)
	else:
		check_completed.emit(false, info)


func start_update(target_download_url: String = "") -> void:
	if _is_updating:
		return
	_ensure_nodes()
	var url := target_download_url
	if url == "":
		url = _latest_release_info.get("download_url", "")
	if url == "":
		update_error.emit("No download URL available for update")
		return

	_is_updating = true
	_download_http.download_file = TEMP_ZIP_FILE
	update_progress.emit("downloading", 0, 100)
	_progress_timer.start()

	var headers := PackedStringArray([
		"User-Agent: Godot-Agent-Updater"
	])
	var err := _download_http.request(url, headers, HTTPClient.METHOD_GET)
	if err != OK:
		_is_updating = false
		_progress_timer.stop()
		update_error.emit("Failed to start download: " + str(err))


func cancel_update() -> void:
	if _is_updating:
		_is_updating = false
		if _download_http:
			_download_http.cancel_request()
		if _progress_timer:
			_progress_timer.stop()
		if FileAccess.file_exists(TEMP_ZIP_FILE):
			DirAccess.remove_absolute(TEMP_ZIP_FILE)


func _on_progress_tick() -> void:
	if not _is_updating or _download_http == null:
		return
	var downloaded := _download_http.get_downloaded_bytes()
	var total := _download_http.get_body_size()
	if total > 0:
		var pct := int((float(downloaded) / float(total)) * 100.0)
		update_progress.emit("downloading", mini(pct, 99), 100)


func _on_download_completed(result: int, response_code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
	_is_updating = false
	if _progress_timer:
		_progress_timer.stop()

	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
		update_error.emit("Download failed (HTTP " + str(response_code) + ")")
		if FileAccess.file_exists(TEMP_ZIP_FILE):
			DirAccess.remove_absolute(TEMP_ZIP_FILE)
		return

	update_progress.emit("extracting", 0, 100)
	var res := verify_and_install_zip(TEMP_ZIP_FILE)
	if not res.get("ok", false):
		var err_msg: String = res.get("error", "Installation failed")
		update_error.emit(err_msg)
		if FileAccess.file_exists(TEMP_ZIP_FILE):
			DirAccess.remove_absolute(TEMP_ZIP_FILE)
		return

	update_progress.emit("extracting", 100, 100)
	update_completed.emit(true)


func verify_and_install_zip(zip_path: String) -> Dictionary:
	var reader := ZIPReader.new()
	var err := reader.open(zip_path)
	if err != OK:
		return {"ok": false, "error": "Cannot open zip file (error " + str(err) + ")"}

	var files := reader.get_files()
	if files.is_empty():
		reader.close()
		return {"ok": false, "error": "Zip archive is empty"}

	# Находим plugin.cfg для определения структуры архива
	var plugin_cfg_entry := ""
	for f in files:
		if f.ends_with("plugin.cfg"):
			plugin_cfg_entry = f
			break

	if plugin_cfg_entry == "":
		reader.close()
		return {"ok": false, "error": "Invalid archive: plugin.cfg not found"}

	# Определяем базовую папку и префикс путей внутри архива
	var self_script: Script = get_script() as Script
	var addon_base: String = String(self_script.resource_path if self_script else "").get_base_dir()
	var strip_prefix: String = ""
	var target_base: String = ""

	if plugin_cfg_entry == "plugin.cfg":
		strip_prefix = ""
		target_base = addon_base
	elif plugin_cfg_entry.ends_with("/godot_agent/plugin.cfg"):
		var idx := plugin_cfg_entry.rfind("godot_agent/plugin.cfg")
		strip_prefix = plugin_cfg_entry.substr(0, idx)
		target_base = addon_base.get_base_dir()
	else:
		var last_slash := plugin_cfg_entry.rfind("/")
		if last_slash != -1:
			strip_prefix = plugin_cfg_entry.substr(0, last_slash + 1)
		target_base = addon_base

	# Останавливаем сервер перед перезаписью файлов
	shutdown_server()
	OS.delay_msec(250)

	var user_preserve_files: Array[String] = [
		"godot_agent_server_path.txt",
		"godot_agent_token.txt",
		"godot_agent_lang.txt",
		"godot_agent_update_check.json",
		"server_path.txt"
	]

	var updated_count := 0
	for f_path in files:
		if not f_path.begins_with(strip_prefix):
			continue
		var rel := f_path.substr(strip_prefix.length())
		if rel == "" or rel == "/":
			continue
		if rel.begins_with("/"):
			rel = rel.substr(1)

		# Пропускаем пользовательские настройки
		var base_name := rel.get_file()
		if base_name in user_preserve_files:
			continue

		var dest_res := target_base.path_join(rel)
		var dest_global := ProjectSettings.globalize_path(dest_res)

		if f_path.ends_with("/"):
			DirAccess.make_dir_recursive_absolute(dest_global)
			continue

		# Убеждаемся, что родительский каталог существует
		var parent_dir := dest_global.get_base_dir()
		if not DirAccess.dir_exists_absolute(parent_dir):
			DirAccess.make_dir_recursive_absolute(parent_dir)

		var data := reader.read_file(f_path)
		var file := FileAccess.open(dest_global, FileAccess.WRITE)
		if file == null:
			# Повторная попытка на случай задержки снятия блокировки OS
			OS.delay_msec(200)
			file = FileAccess.open(dest_global, FileAccess.WRITE)
		if file == null:
			# Если файл всё ещё заблокирован, сохраняем рядом как .new
			file = FileAccess.open(dest_global + ".new", FileAccess.WRITE)
			if file == null:
				reader.close()
				return {"ok": false, "error": "Failed to write file: " + rel}

		file.store_buffer(data)
		file.close()
		updated_count += 1

	reader.close()
	if FileAccess.file_exists(zip_path):
		DirAccess.remove_absolute(zip_path)

	return {"ok": true, "updated_files": updated_count}


func _json_headers() -> PackedStringArray:
	var token_file := "user://godot_agent_token.txt"
	var token := ""
	if FileAccess.file_exists(token_file):
		var f := FileAccess.open(token_file, FileAccess.READ)
		if f:
			token = f.get_as_text().strip_edges()
			f.close()
	return PackedStringArray([
		"Content-Type: application/json",
		"X-Agent-Token: " + token,
	])


func shutdown_server() -> void:
	# 1. Посылаем запрос на завершение работы локального сервера
	var http := HTTPRequest.new()
	add_child(http)
	var headers := _json_headers()
	http.request("http://127.0.0.1:5000/server/shutdown", headers, HTTPClient.METHOD_POST, "{}")

	# 2. На Windows принудительно завершаем godot_agent_server.exe, если он активен
	if OS.get_name() == "Windows":
		OS.execute("taskkill", ["/F", "/IM", "godot_agent_server.exe"], [], false, true)

	# Удаляем временный узел через 1 секунду
	var timer := get_tree().create_timer(1.0)
	timer.timeout.connect(http.queue_free)


func restart_editor() -> void:
	if Engine.is_editor_hint():
		var ei = EditorInterface
		if ei != null and ei.has_method("restart_editor"):
			ei.restart_editor(true)
			return
	# Fallback
	OS.create_process(OS.get_executable_path(), OS.get_cmdline_args())
	if get_tree():
		get_tree().quit()


func open_github_release(url: String = "") -> void:
	var target_url := url
	if target_url == "":
		target_url = _latest_release_info.get("html_url", "https://github.com/" + REPO + "/releases/latest")
	OS.shell_open(target_url)


# ---------------------------------------------------------------------------
# Markdown -> BBCode для текста релиза
# ---------------------------------------------------------------------------
#
# ЗАЧЕМ. Описание релиза пишет release_prepare.py в Markdown: его читает
# страница релиза на GitHub. Панель же показывает body в RichTextLabel с
# bbcode_enabled, где «## Заголовок» и «- пункт» выглядели бы как есть, вместе
# с решётками и дефисами. Здесь та же строка переводится в BBCode.
#
# ГРАНИЦА. Поддержано ровно то, что выпускает release_prepare.py: заголовки
# #/##/###, маркеры списка, **жирный**, `код`, [текст](ссылка) и разделитель
# ---. Это НЕ общий Markdown-парсер: вложенность, таблицы и блочные цитаты не
# разбираются и остаются обычным текстом. Курсив подчёркиванием не
# поддерживается намеренно - _ready и _process это обычные имена в GDScript,
# и поддержка превратила бы описание в кашу (то же решение в
# python/server/md_to_bbcode.py).
#
# Ссылки становятся кликабельными [url=...]текст[/url], а не голым текстом:
# у каждого пункта changelog есть адрес коммита, и он должен открываться.

const _LINK_MARK := "\u0001"
const _HR_LINE := "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
const _BULLET := "\u2022"


static func _new_regexes() -> Array:
	# Регекспы собираются на каждый вызов, а не хранятся в константах:
	# константа RegEx в GDScript инициализируется при загрузке скрипта, и
	# один общий экземпляр сделал бы подстановки зависимыми от порядка вызовов.
	var link := RegEx.new()
	link.compile("\\[([^\\]]*)\\]\\(([^)\\s]+)\\)")
	var bold := RegEx.new()
	bold.compile("\\*\\*([^*]+)\\*\\*")
	var code := RegEx.new()
	code.compile("`([^`]+)`")
	var head := RegEx.new()
	head.compile("^\\s*(#{1,6})\\s+(.*)$")
	var bullet := RegEx.new()
	bullet.compile("^(\\s*)[-*+]\\s+(.*)$")
	return [link, bold, code, head, bullet]


static func markdown_to_bbcode(md: String) -> String:
	"""Перевести Markdown-описание релиза в BBCode панели."""
	if md.strip_edges() == "":
		return ""
	var regexes := _new_regexes()
	var link_re: RegEx = regexes[0]
	var bold_re: RegEx = regexes[1]
	var code_re: RegEx = regexes[2]
	var head_re: RegEx = regexes[3]
	var bullet_re: RegEx = regexes[4]

	# 1. Ссылки вынимаются ДО экранирования скобок и прячутся за метки:
	#    иначе экранирование превратило бы их в [lb]text[rb](url), и кликабельной
	#    ссылка не осталась бы.
	#    RegEx.sub() в Godot 4 принимает только String в качестве замены, поэтому
	#    подстановка идёт вручную через search() со смещением курсора.
	var links: Array[String] = []
	var text := _extract_links(md, link_re, links)

	# 2. Остальные скобки экранируются: в описании встречаются литералы вроде
	#    [lb], и без этого RichTextLabel съел бы их как неизвестный тег.
	#    Именно ОДИН проход, а не два replace(): второй проход по "]" испортил бы
	#    скобки, подставленные первым, и "[lb]" превратился бы в "[lb[rb]".
	text = _escape_brackets(text)

	# 3. Построчный разбор блочных элементов.
	var out: Array[String] = []
	for raw_line in text.split("\n"):
		out.append(_convert_release_line(raw_line, bold_re, code_re, head_re, bullet_re))

	# 4. Ссылки возвращаются как [url=...]текст[/url].
	var result := "\n".join(out)
	for i in range(links.size() - 1, -1, -1):
		result = result.replace(_LINK_MARK + str(i) + _LINK_MARK, links[i])
	return result


static func _extract_links(text: String, link_re: RegEx, links: Array[String]) -> String:
	"""Заменить каждую [текст](url) на метку, вернув готовый BBCode в links."""
	var out := ""
	var cursor := 0
	while cursor < text.length():
		var match := link_re.search(text, cursor)
		if match == null:
			break
		out += text.substr(cursor, match.get_start() - cursor)
		links.append("[url=%s]%s[/url]" % [match.get_string(2), match.get_string(1)])
		out += _LINK_MARK + str(links.size() - 1) + _LINK_MARK
		cursor = match.get_end()
	return out + text.substr(cursor)


static func _escape_brackets(text: String) -> String:
	"""За один проход заменить [ на [lb], а ] на [rb]."""
	var out := ""
	for i in range(text.length()):
		var ch := text[i]
		if ch == "[":
			out += "[lb]"
		elif ch == "]":
			out += "[rb]"
		else:
			out += ch
	return out


static func _convert_release_line(raw_line: String, bold_re: RegEx, code_re: RegEx,
		head_re: RegEx, bullet_re: RegEx) -> String:
	var line := raw_line.strip_edges()
	if line == "":
		return ""
	if line.begins_with("---") or line.begins_with("***"):
		return _HR_LINE

	var head := head_re.search(line)
	if head != null:
		var level := head.get_string(1).length()
		var title := _inline(head.get_string(2), bold_re, code_re)
		# Уровни 1-2 крупнее, 4+ - просто жирный: в окне диалога разница в
		# пару пунктов не читается, а мелкий текст нечитаем.
		if level <= 2:
			return "[b][font_size=20]%s[/font_size][/b]" % title
		return "[b]%s[/b]" % title

	# Маркеры ищем в строке БЕЗ обрезки слева: отступ отражает вложенность
	# списка, и strip_edges() его бы стёр. Справа убираем хвост, чтобы \r из
	# CRLF-описания не попал в текст пункта.
	var bullet := bullet_re.search(raw_line.strip_edges(false, true))
	if bullet != null:
		return "%s%s %s" % [bullet.get_string(1), _BULLET,
				_inline(bullet.get_string(2), bold_re, code_re)]

	return _inline(line, bold_re, code_re)


static func _inline(text: String, bold_re: RegEx, code_re: RegEx) -> String:
	# Жирный раньше кода: внутри `кода` двойные звёздочки - часть содержимого.
	var out := bold_re.sub(text, "[b]$1[/b]", true)
	return code_re.sub(out, "[code]$1[/code]", true)
