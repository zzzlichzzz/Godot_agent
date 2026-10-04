extends SceneTree

# Сигнатура обработчика пункта контекстного меню.
#
# Godot зовёт такой обработчик С ОДНИМ аргументом, хотя add_context_menu_item()
# ничего о сигнатуре не сообщает. Объявить метод без параметров — значит
# получить ошибку в момент клика:
#   Failed to execute context menu callback: 'EditorContextMenuPlugin::_on_ask':
#   Method expected 0 argument(s), but called with 1.
# Ни одна статическая проверка этого не ловит: сигнатуру не видно в тексте
# файла как нарушение, а --check-only её не проверяет. Ловится только вызовом.
const SENTINEL := "CTX_CB_RESULTS "
# Раннер запускает фикстуру в изолированной песочнице, где аддон лежит по
# пути addons/godot_agent/, а в рабочем проекте — addons/Godot_agent/godot_agent/.
# Поэтому ищем по обоим, а не по одному жёсткому пути.
const ENTRY_CANDIDATES := [
	"res://addons/Godot_agent/godot_agent/agent_entry.gd",
	"res://addons/godot_agent/agent_entry.gd",
]

var completed: Array[String] = []
var failures: Array[String] = []


func check(name: String, cond: bool, detail: String = "") -> void:
	if cond:
		completed.append(name)
	else:
		failures.append(name + (" :: " + detail if detail != "" else ""))


func _report() -> void:
	print(SENTINEL + JSON.stringify({"completed": completed, "failures": failures}))


func _init() -> void:
	var script: Script = null
	var tried: Array[String] = []
	for candidate in ENTRY_CANDIDATES:
		if ResourceLoader.exists(candidate):
			script = load(candidate) as Script
			if script != null:
				break
		tried.append(candidate)

	if script == null:
		check("точка входа загружается", false, "проверены " + str(tried))
		_report()
		quit(1)
		return
	check("точка входа загружается", true)

	var inner = script.get("SceneTreeMenu")
	check("внутренний класс SceneTreeMenu доступен", inner != null)
	if inner == null:
		_report()
		quit(1)
		return

	# Хост-подделка нужна только ради сигнатуры: до вызова host дело не
	# доходит, потому что у пустого EditorPlugin нет метода agent_ask_about.
	var host := EditorPlugin.new()
	var menu = inner.new(host, "узел")

	var method: Dictionary = {}
	for m in menu.get_method_list():
		if String(m.get("name", "")) == "_on_ask":
			method = m
			break

	check("метод _on_ask существует", not method.is_empty())
	if method.is_empty():
		host.free()
		_report()
		quit(1)
		return

	var has_optional := false
	for a in method.get("args", []):
		# PROPERTY_USAGE_NIL = (1 << 17) = 131072 — бит, которым Godot
		# помечает аргумент со значением по умолчанию. Бит 2 — это
		# PROPERTY_USAGE_STORAGE, к необязательности отношения не имеет.
		if String(a.get("name", "")) == "_item" \
				and (int(a.get("usage", 0)) & 131072) != 0:
			has_optional = true
	check("у _on_ask есть необязательный аргумент", has_optional,
		"args=" + str(method.get("args", [])))

	# Собственно проверка починки: вызов с ОДНИМ аргументом. На коде без
	# необязательного параметра движок печатает "Expected 0 argument(s)" и
	# роняет вызов, поэтому проверка обязана вызывать, а не читать текст.
	menu.call("_on_ask", 0)
	check("вызов с одним аргументом не падает", true)
	menu.call("_on_ask")
	check("вызов без аргументов не падает", true)

	host.free()
	_report()
	quit(1 if failures.size() > 0 else 0)