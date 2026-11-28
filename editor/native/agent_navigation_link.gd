@tool
extends "agent_server_link.gd"
## Selected-page requests use the same queue as opening a chat.

func _fire(kind: String, extra: Dictionary, allow_autostart: bool = true) -> void:
	if kind not in ["status", "reload"]:
		super._fire(kind, extra, allow_autostart)
		return
	var url := AgentServer.URL_BROWSER_PAGE_STATUS if kind == "status" else AgentServer.URL_BROWSER_RELOAD
	var body := {"user_data_dir": OS.get_user_data_dir(), "project_root": ProjectSettings.globalize_path("res://"),
		"chat_id": extra.get("chat_id", "")}
	_kind = kind
	_extra = extra
	_autostart_ok = false
	_inflight = true
	_http.set_http_proxy("", 0)
	if _http.request(url, json_headers(), HTTPClient.METHOD_POST, JSON.stringify(body)) == OK:
		_connect_watch.start(3.0)
	else:
		_on_response(HTTPRequest.RESULT_REQUEST_FAILED, 0, PackedStringArray(), PackedByteArray())


func leave_loading() -> void:
	const NAVIGATION := ["new", "open", "sites", "list", "status", "api_providers"]
	_retry_after_server.clear()
	_queue = _queue.filter(func(r): return r.kind not in NAVIGATION)
	_server_wait_left = 0
	if _server_wait_timer: _server_wait_timer.stop()
	if _inflight and _kind in NAVIGATION:
		# A late completion on the abandoned node must not finish a newer request.
		_connect_watch.stop()
		_connect_watch.queue_free()
		_http.request_completed.disconnect(_on_response)
		_http.cancel_request()
		_http.queue_free()
		_http = null
		super._ready()
		_kind = ""
		_extra = {}
		_inflight = false
		call_deferred("_drain_queue")
