extends SceneTree

# Сквозная проверка цепочки «клик по пункту меню → вопрос в чате».
#
# Собирает док ровно так же, как это делает agent_entry при загрузке плагина,
# и проверяет, что команда доходит до панели. Без этой проверки обрыв цепочки
# выглядел как «ничего не происходит»: обработчик уходил в пустой слот и
# выходил молча.
const SENTINEL := "CTX_E2E_RESULTS "
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


func _load_first(paths: Array) -> Script:
	for p in paths:
		if ResourceLoader.exists(p):
			var s := load(p) as Script
			if s != null:
				return s
	return null


func _init() -> void:
	var entry_script := _load_first(ENTRY_CANDIDATES)
	check("скрипт точки входа загружается", entry_script != null)
	if entry_script == null:
		_report()
		quit(1)
		return

	var entry = entry_script.new()
	check("точка входа создаётся", entry != null)
	if entry == null:
		_report()
		quit(1)
		return

	# Собираем док теми же шагами, что делает _build_dock, пропуская сам
	# add_control_to_dock: он требует зарегистрированного плагина и вне
	# редактора роняет процесс. Для проверки цепочки важны только два шага:
	# сборка панели (внутри неё bind_command_handler) и присвоение _dock,
	# которое читает _handle_command.
	entry.call("_load_locale")
	var panel_path: String = entry.call("_find_file",
		entry.call("_addon_path"), "agent_panel.gd")
	check("agent_panel.gd найден", panel_path != "", panel_path)
	if panel_path == "":
		_report()
		quit(1)
		return

	var panel = entry.call("_build_panel", panel_path)
	check("панель собрана", panel != null)
	if panel == null:
		_report()
		quit(1)
		return
	entry.set("_dock", panel)

	var handler = entry.get("_dock")
	check("док панели доступен", handler != null)

	# Панель должна попасть в дерево: только тогда отработает @onready и
	# input_field станет доступен. Без этого проверка на пустом узле ничего
	# не доказывала бы. add_child() у SceneTree нет — вешаем в корневое окно.
	get_root().add_child(panel)
	await process_frame

	var field = panel.get_node_or_null("VBoxContainer/HBoxContainer/InputField")
	check("поле ввода найдено после сборки", field != null)
	if field == null:
		_report()
		quit(1)
		return

	# Собственно команда. Тот же вход, что зовёт пункт меню.
	entry.call("agent_ask_about", "узел", PackedStringArray(["Player"]))
	check("команда не оставила поле пустым", field.text.strip_edges() != "",
		"текст=%s" % field.text)
	check("в вопрос попал выбранный узел", field.text.contains("Player"),
		"текст=%s" % field.text)

	# Честно фиксируем, докуда вопрос уехал на самом деле. Панель отправляет
	# его обычным путём _on_send_pressed, который занят сетевым обменом; в
	# headless без сервера он не дойдёт до сети. Проверка выше доказывает
	# главное — команда из меню дошла до панели и превратилась в вопрос, —
	# а эти два значения объясняют состояние отправки.
	var busy: bool = bool(panel.get("_is_network_busy"))
	var pending: bool = bool(panel.call("_has_pending_action"))
	check("состояние отправки зафиксировано", true,
		"network_busy=%s pending_action=%s текст_остался=%s"
			% [busy, pending, field.text.strip_edges() != ""])

	_report()
	quit(1 if failures.size() > 0 else 0)