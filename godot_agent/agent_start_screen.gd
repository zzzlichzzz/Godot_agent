@tool
extends Control

# ---------------------------------------------------------------------------
# Стартовый экран агента.
# Главная: две кнопки делят экран по вертикали — сверху «Загрузиться»
# (список сохранённых чатов), снизу «Новый чат» (список сайтов-нейросетей).
# Наружу отдаёт сигналы, а данные получает через set_chats()/set_sites().
# ---------------------------------------------------------------------------

signal new_chat_requested(site_id)
signal load_chat_requested(chat_id)
signal sites_tab_requested()
signal chats_tab_requested()

var _home: VBoxContainer = null
var _chats_view: VBoxContainer = null
var _sites_view: VBoxContainer = null
var _chats_list: VBoxContainer = null
var _sites_list: VBoxContainer = null
var _chats_data: Array = []
var _sites_data: Array = []
var _built: bool = false
var _status: Label = null
var _loading_view: VBoxContainer = null
var _loading_spinner: Label = null
var _loading_label: Label = null
var _spin_timer: Timer = null
var _spin_idx: int = 0
var _return_view: String = "home"
const SPIN_FRAMES := ["|", "/", "-", "\\"]


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_build()
	show_home()


func _build() -> void:
	if _built:
		return
	_built = true
	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(root)

	var title := Label.new()
	title.text = "Браузерный ИИ-Агент"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 20)
	root.add_child(title)

	# ---- ГЛАВНАЯ: две большие кнопки, сверху и снизу ----
	_home = VBoxContainer.new()
	_home.size_flags_horizontal = SIZE_EXPAND_FILL
	_home.size_flags_vertical = SIZE_EXPAND_FILL
	root.add_child(_home)
	var hint := Label.new()
	hint.text = "С чего начнём?"
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_home.add_child(hint)
	# Вертикальное деление экрана: верхняя кнопка и нижняя кнопка.
	var split := VBoxContainer.new()
	split.size_flags_horizontal = SIZE_EXPAND_FILL
	split.size_flags_vertical = SIZE_EXPAND_FILL
	_home.add_child(split)
	var b_load := Button.new()
	b_load.text = "Загрузиться"
	b_load.size_flags_horizontal = SIZE_EXPAND_FILL
	b_load.size_flags_vertical = SIZE_EXPAND_FILL
	b_load.pressed.connect(func(): chats_tab_requested.emit())
	split.add_child(b_load)
	var b_new := Button.new()
	b_new.text = "Новый чат"
	b_new.size_flags_horizontal = SIZE_EXPAND_FILL
	b_new.size_flags_vertical = SIZE_EXPAND_FILL
	b_new.pressed.connect(func(): sites_tab_requested.emit())
	split.add_child(b_new)

	# ---- СПИСОК ЧАТОВ ----
	_chats_view = VBoxContainer.new()
	_chats_view.size_flags_horizontal = SIZE_EXPAND_FILL
	_chats_view.size_flags_vertical = SIZE_EXPAND_FILL
	_chats_view.visible = false
	root.add_child(_chats_view)
	_chats_view.add_child(_make_header("Сохранённые чаты"))
	var ch_scroll := ScrollContainer.new()
	ch_scroll.size_flags_horizontal = SIZE_EXPAND_FILL
	ch_scroll.size_flags_vertical = SIZE_EXPAND_FILL
	_chats_view.add_child(ch_scroll)
	_chats_list = VBoxContainer.new()
	_chats_list.size_flags_horizontal = SIZE_EXPAND_FILL
	ch_scroll.add_child(_chats_list)

	# ---- СПИСОК САЙТОВ (нейросетей) ----
	_sites_view = VBoxContainer.new()
	_sites_view.size_flags_horizontal = SIZE_EXPAND_FILL
	_sites_view.size_flags_vertical = SIZE_EXPAND_FILL
	_sites_view.visible = false
	root.add_child(_sites_view)
	_sites_view.add_child(_make_header("Выберите сайт (нейросеть)"))
	var st_scroll := ScrollContainer.new()
	st_scroll.size_flags_horizontal = SIZE_EXPAND_FILL
	st_scroll.size_flags_vertical = SIZE_EXPAND_FILL
	_sites_view.add_child(st_scroll)
	_sites_list = VBoxContainer.new()
	_sites_list.size_flags_horizontal = SIZE_EXPAND_FILL
	st_scroll.add_child(_sites_list)

	# ---- СТАТУСНАЯ СТРОКА (запуск сервера, загрузка страниц и т.п.) ----
	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.visible = false
	root.add_child(_status)

	_loading_view = VBoxContainer.new()
	_loading_view.size_flags_horizontal = SIZE_EXPAND_FILL
	_loading_view.size_flags_vertical = SIZE_EXPAND_FILL
	_loading_view.alignment = BoxContainer.ALIGNMENT_CENTER
	_loading_view.visible = false
	root.add_child(_loading_view)
	_loading_spinner = Label.new()
	_loading_spinner.text = "|"
	_loading_spinner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_loading_spinner.add_theme_font_size_override("font_size", 32)
	_loading_view.add_child(_loading_spinner)
	_loading_label = Label.new()
	_loading_label.text = "..."
	_loading_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_loading_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_loading_view.add_child(_loading_label)
	_spin_timer = Timer.new()
	_spin_timer.wait_time = 0.12
	_spin_timer.one_shot = false
	add_child(_spin_timer)
	_spin_timer.timeout.connect(_on_spin_tick)


func _make_header(text: String) -> HBoxContainer:
	var head := HBoxContainer.new()
	var back := Button.new()
	back.text = "Назад"
	back.pressed.connect(show_home)
	head.add_child(back)
	var lbl := Label.new()
	lbl.text = text
	lbl.size_flags_horizontal = SIZE_EXPAND_FILL
	head.add_child(lbl)
	return head


func set_chats(arr) -> void:
	if typeof(arr) == TYPE_ARRAY:
		_chats_data = arr
	_rebuild_chats()


func set_sites(arr) -> void:
	if typeof(arr) == TYPE_ARRAY:
		_sites_data = arr
	_rebuild_sites()


func _clear_container(c: Node) -> void:
	if c == null:
		return
	for ch in c.get_children():
		ch.queue_free()


func _rebuild_chats() -> void:
	if _chats_list == null:
		return
	_clear_container(_chats_list)
	if _chats_data.is_empty():
		var empty := Label.new()
		empty.text = "Пока нет сохранённых чатов. Начните новый!"
		_chats_list.add_child(empty)
		return
	for c in _chats_data:
		if typeof(c) != TYPE_DICTIONARY:
			continue
		var btn := Button.new()
		var t := str(c.get("title", "Без названия"))
		var sname := str(c.get("site_name", ""))
		btn.text = t if sname == "" else (t + "   — " + sname)
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		btn.size_flags_horizontal = SIZE_EXPAND_FILL
		btn.pressed.connect(_pick_chat.bind(str(c.get("id", ""))))
		_chats_list.add_child(btn)


func _rebuild_sites() -> void:
	if _sites_list == null:
		return
	_clear_container(_sites_list)
	if _sites_data.is_empty():
		var empty := Label.new()
		empty.text = "Список сайтов пуст (сервер запущен?)."
		_sites_list.add_child(empty)
		return
	for s in _sites_data:
		if typeof(s) != TYPE_DICTIONARY:
			continue
		var btn := Button.new()
		btn.text = str(s.get("name", "Сайт"))
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		btn.size_flags_horizontal = SIZE_EXPAND_FILL
		btn.pressed.connect(_pick_site.bind(str(s.get("id", ""))))
		_sites_list.add_child(btn)
	# ЗАГОТОВКА: кнопка «добавить свою страницу» (универсальный парсер) — позже.
	var add_own := Button.new()
	add_own.text = "Добавить свою страницу (скоро)"
	add_own.disabled = true
	add_own.tooltip_text = "В разработке: универсальный парсер подберёт алгоритм чтения страницы."
	add_own.size_flags_horizontal = SIZE_EXPAND_FILL
	_sites_list.add_child(add_own)


func _pick_chat(chat_id: String) -> void:
	if chat_id != "":
		load_chat_requested.emit(chat_id)


func _pick_site(site_id: String) -> void:
	if site_id != "":
		new_chat_requested.emit(site_id)


func show_home() -> void:
	_stop_loading_visual()
	if _home: _home.visible = true
	if _chats_view: _chats_view.visible = false
	if _sites_view: _sites_view.visible = false


func show_chats() -> void:
	_stop_loading_visual()
	_rebuild_chats()
	if _home: _home.visible = false
	if _chats_view: _chats_view.visible = true
	if _sites_view: _sites_view.visible = false


func show_sites() -> void:
	_stop_loading_visual()
	_rebuild_sites()
	if _home: _home.visible = false
	if _sites_view: _sites_view.visible = true
	if _chats_view: _chats_view.visible = false


func set_status(text: String, kind: String = "info") -> void:
	# Статус внизу экрана: виден из любого подраздела стартового экрана.
	if _status == null:
		return
	_status.text = text
	_status.visible = text != ""
	var color := Color(0.85, 0.85, 0.85)
	if kind == "success":
		color = Color(0.49, 0.99, 0.6)
	elif kind == "error":
		color = Color(1.0, 0.54, 0.5)
	elif kind == "status":
		color = Color(1.0, 0.84, 0.4)
	_status.add_theme_color_override("font_color", color)


func show_loading(text: String) -> void:
	if not is_loading():
		if _sites_view and _sites_view.visible:
			_return_view = "sites"
		elif _chats_view and _chats_view.visible:
			_return_view = "chats"
		else:
			_return_view = "home"
	if _home: _home.visible = false
	if _chats_view: _chats_view.visible = false
	if _sites_view: _sites_view.visible = false
	if _loading_view: _loading_view.visible = true
	if _loading_label: _loading_label.text = text
	if _spin_timer: _spin_timer.start()


func set_loading_text(text: String) -> void:
	if _loading_view and _loading_view.visible and _loading_label:
		_loading_label.text = text


func is_loading() -> bool:
	return _loading_view != null and _loading_view.visible


func hide_loading() -> void:
	_stop_loading_visual()
	match _return_view:
		"sites":
			show_sites()
		"chats":
			show_chats()
		_:
			show_home()


func _stop_loading_visual() -> void:
	if _spin_timer: _spin_timer.stop()
	if _loading_view: _loading_view.visible = false


func _on_spin_tick() -> void:
	_spin_idx = (_spin_idx + 1) % SPIN_FRAMES.size()
	if _loading_spinner:
		_loading_spinner.text = SPIN_FRAMES[_spin_idx]
