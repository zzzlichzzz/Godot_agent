@tool
class_name AgentServer
extends RefCounted

# ============================================================================
# AGENT SERVER — единственное место, где плагин знает про локальный сервер.
#
# Зачем файл существует. Адрес сервера был объявлен дважды: в agent_panel.gd
# и в agent_server_link.gd. Смена порта требовала правки в двух местах, а
# забытая половина выглядит как «плагин перестал видеть сервер». Логика
# заголовков тоже была в трёх копиях (панель, транспорт, agent_updater),
# причём копии различались поведением.
#
# Здесь — адрес, реестр маршрутов, токен проекта и заголовки. Никаких
# HTTPRequest: сам транспорт (очередь, таймаут, автозапуск) остаётся в
# agent_server_link.gd и использует адреса отсюда.
#
# Реестр сверен с тем, что сервер объявляет сам: main.py (35 маршрутов) и
# server/chat_routes.py (13). Проверка сверки живёт в
# python/tests/test_agent_server_client.py — маршрут, о котором сервер не
# знает, вернёт 404, а забытый маршрут останется без адреса в плагине.
# ============================================================================

const HOST := "127.0.0.1:5000"
const BASE := "http://" + HOST

# Токен, которым панель подтверждает серверу, что запрос от неё и от ЭТОГО
# проекта (см. server_auth.py). Лежит в user:// — то есть в папке
# конкретного проекта, поэтому сервер, привязавшись к первому обратившемуся
# проекту, отклоняет панель другого. От программы под той же учётной записью
# это не защищает: файл читается тем же пользователем.
const TOKEN_FILE := "user://godot_agent_token.txt"
const TOKEN_HEADER := "X-Agent-Token"
const CONTENT_TYPE := "Content-Type: application/json"

# Пути маршрутов. Ключ — путь на сервере, значение — то, чем панель этот
# маршрут называет. Адреса собираются из них функцией url(), поэтому ни
# один файл плагина больше не пишет "http://" + HOST руками.
const ROUTES := {
	"/api/models/refresh": "api_models",
	"/api/models/scan": "api_scan",
	"/api/providers": "api_providers",
	"/api/settings/set": "api_set",
	"/api/test": "api_test",
	"/browser/status": "browser_status",
	"/chats/delete": "chats_delete",
	"/chats/list": "chats_list",
	"/chats/model": "chats_model",
	"/chats/new": "chats_new",
	"/chats/open": "chats_open",
	"/chats/rename": "chats_rename",
	"/chat": "chat",
	"/chat/confirm_action": "chat_confirm",
	"/chat/editor_action/result": "chat_editor_result",
	"/chat/live_input": "chat_live_input",
	"/chat/plan/rollback_chain": "plan_rollback_chain",
	"/chat/plan/step": "plan_step",
	"/chat/plan/stop": "plan_stop",
	"/chat/progress": "chat_progress",
	"/chat/rollback": "rollback",
	"/chat/rollback/preview": "rollback_preview",
	"/chat/runtime_check/bind": "runtime_check_bind",
	"/chat/runtime_check/result": "runtime_check_result",
	"/chat/runtime_inspect/result": "runtime_inspect_result",
	"/chat/stop": "chat_stop",
	"/dashboard": "dashboard",
	"/dashboard/data": "dashboard_data",
	"/init": "init",
	"/librarian/query": "librarian_query",
	"/minilich/github_fetch": "minilich_github",
	"/minilich/set": "minilich_set",
	"/minilich/status": "minilich_status",
	"/project/api_cache_status": "api_cache_status",
	"/project/check_log": "check_log",
	"/project/refactor/file/apply": "refactor_file_apply",
	"/project/refactor/file/post_move_sync": "refactor_file_post_move_sync",
	"/project/refactor/file/preview": "refactor_file_preview",
	"/project/send_log_errors": "send_log_errors",
	"/project/update_api_cache": "update_api_cache",
	"/scene/refactor/node/apply": "refactor_node_apply",
	"/scene/refactor/node/delete/apply": "refactor_node_delete_apply",
	"/scene/refactor/node/delete/preview": "refactor_node_delete_preview",
	"/scene/refactor/node/preview": "refactor_node_preview",
	"/scene/refactor/node/reparent/apply": "refactor_node_reparent_apply",
	"/scene/refactor/node/reparent/preview": "refactor_node_reparent_preview",
	"/server/shutdown": "server_shutdown",
	"/sites/list": "sites_list",
}

# Адреса маршрутов как константы. Именно константы, а не вызов
# url(): вызов функции не является константным выражением GDScript.
const URL_API_MODELS_REFRESH := BASE + "/api/models/refresh"
const URL_API_MODELS_SCAN := BASE + "/api/models/scan"
const URL_API_PROVIDERS := BASE + "/api/providers"
const URL_API_SETTINGS_SET := BASE + "/api/settings/set"
const URL_API_TEST := BASE + "/api/test"
const URL_BROWSER_STATUS := BASE + "/browser/status"
const URL_CHATS_DELETE := BASE + "/chats/delete"
const URL_CHATS_LIST := BASE + "/chats/list"
const URL_CHATS_MODEL := BASE + "/chats/model"
const URL_CHATS_NEW := BASE + "/chats/new"
const URL_CHATS_OPEN := BASE + "/chats/open"
const URL_CHATS_RENAME := BASE + "/chats/rename"
const URL_CHAT := BASE + "/chat"
const URL_CHAT_CONFIRM_ACTION := BASE + "/chat/confirm_action"
const URL_CHAT_EDITOR_ACTION_RESULT := BASE + "/chat/editor_action/result"
const URL_CHAT_LIVE_INPUT := BASE + "/chat/live_input"
const URL_CHAT_PLAN_ROLLBACK_CHAIN := BASE + "/chat/plan/rollback_chain"
const URL_CHAT_PLAN_STEP := BASE + "/chat/plan/step"
const URL_CHAT_PLAN_STOP := BASE + "/chat/plan/stop"
const URL_CHAT_PROGRESS := BASE + "/chat/progress"
const URL_CHAT_ROLLBACK := BASE + "/chat/rollback"
const URL_CHAT_ROLLBACK_PREVIEW := BASE + "/chat/rollback/preview"
const URL_CHAT_RUNTIME_CHECK_BIND := BASE + "/chat/runtime_check/bind"
const URL_CHAT_RUNTIME_CHECK_RESULT := BASE + "/chat/runtime_check/result"
const URL_CHAT_RUNTIME_INSPECT_RESULT := BASE + "/chat/runtime_inspect/result"
const URL_CHAT_STOP := BASE + "/chat/stop"
const URL_DASHBOARD := BASE + "/dashboard"
const URL_DASHBOARD_DATA := BASE + "/dashboard/data"
const URL_INIT := BASE + "/init"
const URL_LIBRARIAN_QUERY := BASE + "/librarian/query"
const URL_MINILICH_GITHUB_FETCH := BASE + "/minilich/github_fetch"
const URL_MINILICH_SET := BASE + "/minilich/set"
const URL_MINILICH_STATUS := BASE + "/minilich/status"
const URL_PROJECT_API_CACHE_STATUS := BASE + "/project/api_cache_status"
const URL_PROJECT_CHECK_LOG := BASE + "/project/check_log"
const URL_PROJECT_REFACTOR_FILE_APPLY := BASE + "/project/refactor/file/apply"
const URL_PROJECT_REFACTOR_FILE_POST_MOVE_SYNC := BASE + "/project/refactor/file/post_move_sync"
const URL_PROJECT_REFACTOR_FILE_PREVIEW := BASE + "/project/refactor/file/preview"
const URL_PROJECT_SEND_LOG_ERRORS := BASE + "/project/send_log_errors"
const URL_PROJECT_UPDATE_API_CACHE := BASE + "/project/update_api_cache"
const URL_SCENE_REFACTOR_NODE_APPLY := BASE + "/scene/refactor/node/apply"
const URL_SCENE_REFACTOR_NODE_DELETE_APPLY := BASE + "/scene/refactor/node/delete/apply"
const URL_SCENE_REFACTOR_NODE_DELETE_PREVIEW := BASE + "/scene/refactor/node/delete/preview"
const URL_SCENE_REFACTOR_NODE_PREVIEW := BASE + "/scene/refactor/node/preview"
const URL_SCENE_REFACTOR_NODE_REPARENT_APPLY := BASE + "/scene/refactor/node/reparent/apply"
const URL_SCENE_REFACTOR_NODE_REPARENT_PREVIEW := BASE + "/scene/refactor/node/reparent/preview"
const URL_SERVER_SHUTDOWN := BASE + "/server/shutdown"
const URL_SITES_LIST := BASE + "/sites/list"

# Токен читается один раз за сессию редактора: он не меняется, а запросов к
# серверу десятки, и чтение файла на каждый из них — лишняя работа.
static var _token_cache: String = ""
## Путь маршрута по имени. Неизвестное имя даёт пустую строку — лучше
## явная пустота, чем молчаливый запрос по неверному адресу.
static func route(name: String) -> String:
	for path in ROUTES:
		if String(ROUTES[path]) == name:
			return String(path)
	return ""


## Полный адрес маршрута.
static func url(path: String) -> String:
	return BASE + path


## Адрес по имени маршрута: url_for("chat").
static func url_for(name: String) -> String:
	var path := route(name)
	if path.is_empty():
		push_error("[Godot Agent] Неизвестный маршрут: " + name)
		return ""
	return url(path)


## Токен проекта: читается из файла, а если его нет — создаётся.
##
## Значение переживает перезапуск редактора: сервер мог уже привязаться к
## прежнему, и смена токена на каждом запуске заставляла бы перезапускать
## сервер.
static func project_token() -> String:
	if _token_cache.length() >= 16:
		return _token_cache
	if FileAccess.file_exists(TOKEN_FILE):
		var f := FileAccess.open(TOKEN_FILE, FileAccess.READ)
		if f:
			var saved := f.get_as_text().strip_edges()
			f.close()
			if saved.length() >= 16:
				_token_cache = saved
				return _token_cache
	var token := ""
	for i in 8:
		# crypto-стойкость здесь не нужна и недостижима (файл всё равно читает
		# тот же пользователь) — достаточно, чтобы значение нельзя было угадать.
		token += "%08x" % (randi() ^ (Time.get_ticks_usec() + i * 7919))
	var w := FileAccess.open(TOKEN_FILE, FileAccess.WRITE)
	if w:
		w.store_string(token)
		w.close()
	_token_cache = token
	return token


## Токен, если он УЖЕ есть. Файл не создаёт: отсутствие токена означает, что
## сервер к нему ещё не привязан и запрос пройдёт и без него.
static func existing_token() -> String:
	if _token_cache.length() >= 16:
		return _token_cache
	if not FileAccess.file_exists(TOKEN_FILE):
		return ""
	var f := FileAccess.open(TOKEN_FILE, FileAccess.READ)
	if f == null:
		return ""
	var saved := f.get_as_text().strip_edges()
	f.close()
	return saved


## Заголовки для запроса к серверу.
##
## require_token = false — поведение, которое раньше было в панели: если
## токена нет, заголовок токена НЕ отправляется. Отправлять "X-Agent-Token: "
## с пустым значением хуже, чем не отправлять вовсе: сервер получает
## заголовок и отвечает 403, хотя запрос без него прошёл бы.
static func json_headers(require_token: bool = true) -> PackedStringArray:
	var token := project_token() if require_token else existing_token()
	if token.is_empty():
		return PackedStringArray([CONTENT_TYPE])
	return PackedStringArray([CONTENT_TYPE, TOKEN_HEADER + ": " + token])