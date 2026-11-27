# editor/bridge/server/endpoints.gd - адреса, токен, pid сервера (из agent_server.gd).
# Сборка адресов моста: таблица примитивов и диспетчер. Новых примитивов здесь
# нет - только объявленные в `contract/editor_verbs.json` (R-14).
@tool
extends RefCounted

const RouterScript := preload("../dispatch/router.gd")
const DispatcherScript := preload("../dispatch/dispatcher.gd")
const VerbsScript := preload("../verbs/editors/editor_verbs.gd")
const SceneVerbsScript := preload("../verbs/scene/scene_verbs.gd")

const PROTOCOL := 1
const VERBS_MARKER := "# verb:"


static func build() -> Dictionary:
	var router = RouterScript.new()
	VerbsScript.new().register(router)
	SceneVerbsScript.new().register(router)
	return {"router": router,
		"dispatcher": DispatcherScript.new(router),
		"verbs": router.verbs()}
