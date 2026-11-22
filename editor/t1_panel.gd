@tool
extends VBoxContainer
# Transport and UI only. Python owns planning, policy, approval, WAL and rollback.
var _request: HTTPRequest
var _output: RichTextLabel
var _input: TextEdit
var _confirm: Button
var _reject: Button
var _rollback: Button
var _pending: Dictionary = {}
var _last: Dictionary = {}
var _route := ""
var _base := ""
var _token := ""

func _load_profile() -> void:
	_base = ""
	_token = ""
	var profile := OS.get_environment("GODOT_AGENT_STATE_DIR")
	if profile.is_empty() or not profile.is_absolute_path(): return
	profile = profile.simplify_path().replace("\\", "/").trim_suffix("/")
	var project := ProjectSettings.globalize_path("res://").simplify_path().replace("\\", "/").trim_suffix("/")
	if profile.to_lower() == project.to_lower() or profile.to_lower().begins_with(project.to_lower() + "/"): return
	var current := profile
	for _index in range(64):
		var parent := DirAccess.open(current.get_base_dir())
		if parent == null or parent.is_link(current.get_file()): return
		var next := current.get_base_dir()
		if next == current or next.get_file().is_empty(): break
		current = next
	var directory := DirAccess.open(profile)
	if directory == null or directory.is_link("http_endpoint.json") or directory.is_link("godot_agent_token.txt"): return
	var endpoint := FileAccess.open(profile.path_join("http_endpoint.json"), FileAccess.READ)
	if endpoint == null or endpoint.get_length() > 4096: return
	var record = JSON.parse_string(endpoint.get_as_text())
	endpoint.close()
	if not record is Dictionary or record.get("host", "") != "127.0.0.1": return
	var port = record.get("port")
	if not (port is int or port is float): return
	if port < 1024 or port > 65535 or port != int(port): return
	var identity := str(record.get("session_id", ""))
	if identity.length() != 32 or not identity.is_valid_hex_number(false): return
	var file := FileAccess.open(profile.path_join("godot_agent_token.txt"), FileAccess.READ)
	if file == null or file.get_length() > 4096: return
	_token = file.get_as_text().strip_edges()
	file.close()
	if _token.is_empty(): return
	_base = "http://127.0.0.1:%d" % int(port)

func _ready() -> void:
	_load_profile()
	name = "Godot Agent"
	custom_minimum_size = Vector2(320, 280)
	var title := Label.new()
	title.text = "Godot Agent — подтверждённые изменения"
	add_child(title)
	_output = RichTextLabel.new()
	_output.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_output.custom_minimum_size.y = 180
	_output.selection_enabled = true
	_output.text = "Запустите локальный сервер. Провайдер настраивается в /api/settings/set.\n"
	add_child(_output)
	_input = TextEdit.new()
	_input.custom_minimum_size.y = 90
	_input.placeholder_text = "Задача агенту…"
	add_child(_input)
	var buttons := HBoxContainer.new()
	add_child(buttons)
	var send := Button.new()
	send.text = "Отправить"
	send.pressed.connect(_send)
	buttons.add_child(send)
	_confirm = Button.new()
	_confirm.text = "Применить"
	_confirm.disabled = true
	_confirm.pressed.connect(func(): _call("/chat/confirm", {"approved": true, "plan_id": _pending.get("plan_id", ""), "digest": _pending.get("digest", "")}))
	buttons.add_child(_confirm)
	_reject = Button.new()
	_reject.text = "Отказаться"
	_reject.disabled = true
	_reject.pressed.connect(func(): _call("/chat/confirm", {"approved": false, "plan_id": _pending.get("plan_id", ""), "digest": _pending.get("digest", "")}))
	buttons.add_child(_reject)
	_rollback = Button.new()
	_rollback.text = "Откатить"
	_rollback.disabled = true
	_rollback.pressed.connect(func(): _call("/chat/rollback", {}))
	buttons.add_child(_rollback)
	_request = HTTPRequest.new()
	_request.timeout = 180.0
	_request.request_completed.connect(_completed)
	add_child(_request)

func _send() -> void:
	if _input.text.strip_edges().is_empty(): return
	_call("/chat", {"text": _input.text, "max_turns": 8})

func _call(route: String, payload: Dictionary) -> void:
	if _route != "": return
	_load_profile()
	if _base.is_empty() or _token.is_empty():
		_output.text += "Настройте внешний GODOT_AGENT_STATE_DIR и локальный HTTP-сервис.\n"
		return
	_route = route
	var headers := PackedStringArray(["Content-Type: application/json", "X-Agent-Token: " + _token])
	var error := _request.request(_base + route, headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		_route = ""
		_output.text += "Локальный сервер недоступен.\n"

func _completed(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var route := _route
	_route = ""
	if _result != HTTPRequest.RESULT_SUCCESS or body.size() > 1000000:
		_output.text += "Локальный запрос не завершён.\n"
		return
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		_output.text += "Сервер вернул неверный JSON.\n"
		return
	if code < 200 or code >= 300:
		_output.text += str(parsed.get("error", parsed.get("message", "Запрос отклонён"))) + "\n"
		return
	if parsed.get("ok", true) != true:
		_output.text += "Запрос отклонён; состояние подтверждения сохранено.\n"
		return
	if route == "/chat":
		_output.text += str(parsed.get("text", "")) + "\n"
		var preview = parsed.get("preview", {})
		_pending = preview if preview is Dictionary and parsed.get("pending_confirmation", false) and not str(preview.get("plan_id", "")).is_empty() and str(preview.get("digest", "")).length() == 64 else {}
		for diff in _pending.get("diffs", []):
			_output.text += "\n" + str(diff.get("path", "")) + "\nДо:\n" + str(diff.get("before", "")) + "\nПосле:\n" + str(diff.get("after", "")) + "\n"
	elif route == "/chat/confirm":
		_pending = {}
		if parsed.get("state", "") == "COMMITTED":
			_last = parsed
			_output.text += "Изменения применены через журнал; доступен откат.\n"
		else: _output.text += "План отклонён: файлы не изменены.\n"
	elif route == "/chat/rollback":
		if parsed.get("state", "") != "ROLLED_BACK":
			_output.text += "Откат не подтверждён; журнал сохранён.\n"
			return
		_last = {}
		_output.text += "Откат завершён.\n"
	_confirm.disabled = _pending.is_empty()
	_reject.disabled = _pending.is_empty()
	_rollback.disabled = _last.is_empty()
