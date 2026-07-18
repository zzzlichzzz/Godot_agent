@tool
extends Control

# ---------------------------------------------------------------------------
# Стартовый экран агента.
# Главная: две кнопки делят экран по вертикали — сверху «Загрузиться»
# (список сохранённых чатов), снизу «Новый чат» (список сайтов-нейросетей).
# Наружу отдаёт сигналы, а данные получает через set_chats()/set_sites().
# Локализация RU/EN — agent_locale.gd; переключатель языка — справа сверху.
# Блок «Поддержать автора»: для русского языка — CloudTips + Boosty,
# для английского — только Boosty (CloudTips не принимает зарубежные карты).
# ---------------------------------------------------------------------------

signal new_chat_requested(site_id)
signal load_chat_requested(chat_id)
signal sites_tab_requested()
signal chats_tab_requested()
signal language_changed()

const URL_BOOSTY := "https://boosty.to/zzzlichzzz"
const URL_TIPS := "https://pay.cloudtips.ru/p/50d418af"
const SPIN_FRAMES := ["|", "/", "-", "\\"]

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
var _loc = null


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_build()
	show_home()


# ---------------- Локализация ----------------

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


func _lang() -> String:
	var l = _locale()
	if l:
		return l.get_lang()
	return "ru"


func _on_lang_selected(idx: int) -> void:
	var l = _locale()
	if l:
		l.set_lang("en" if idx == 1 else "ru")
	language_changed.emit()
	_rebuild_ui()


func _rebuild_ui() -> void:
	# Полная пересборка интерфейса (используется после смены языка).
	_stop_loading_visual()
	for ch in get_children():
		ch.queue_free()
	_built = false
	_home = null
	_chats_view = null
	_sites_view = null
	_chats_list = null
	_sites_list = null
	_status = null
	_loading_view = null
	_loading_spinner = null
	_loading_label = null
	_spin_timer = null
	_build()
	show_home()


# ---------------- Построение интерфейса ----------------

func _build() -> void:
	if _built:
		return
	_built = true
	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(root)

	# Верхняя строка: заголовок + переключатель языка.
	var top := HBoxContainer.new()
	root.add_child(top)
	var top_spacer := Control.new()
	top_spacer.size_flags_horizontal = SIZE_EXPAND_FILL
	top.add_child(top_spacer)
	var lang_lbl := Label.new()
	lang_lbl.text = _t("lang_label")
	top.add_child(lang_lbl)
	var lang_btn := OptionButton.new()
	lang_btn.add_item("Русский", 0)
	lang_btn.add_item("English", 1)
	lang_btn.select(1 if _lang() == "en" else 0)
	lang_btn.item_selected.connect(_on_lang_selected)
	top.add_child(lang_btn)
	var title := Label.new()
	title.text = _t("title")
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.size_flags_horizontal = SIZE_EXPAND_FILL
	title.add_theme_font_size_override("font_size", 20)
	root.add_child(title)

	# ---- ГЛАВНАЯ: две большие кнопки, сверху и снизу ----
	_home = VBoxContainer.new()
	_home.size_flags_horizontal = SIZE_EXPAND_FILL
	_home.size_flags_vertical = SIZE_EXPAND_FILL
	root.add_child(_home)
	var hint := Label.new()
	hint.text = _t("hint")
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_home.add_child(hint)
	# Вертикальное деление экрана: верхняя кнопка и нижняя кнопка.
	var split := VBoxContainer.new()
	split.size_flags_horizontal = SIZE_EXPAND_FILL
	split.size_flags_vertical = SIZE_EXPAND_FILL
	_home.add_child(split)
	var b_load := Button.new()
	b_load.text = _t("btn_load")
	b_load.size_flags_horizontal = SIZE_EXPAND_FILL
	b_load.size_flags_vertical = SIZE_EXPAND_FILL
	b_load.pressed.connect(func(): chats_tab_requested.emit())
	split.add_child(b_load)
	var b_new := Button.new()
	b_new.text = _t("btn_new")
	b_new.size_flags_horizontal = SIZE_EXPAND_FILL
	b_new.size_flags_vertical = SIZE_EXPAND_FILL
	b_new.pressed.connect(func(): sites_tab_requested.emit())
	split.add_child(b_new)

	# ---- Блок «Поддержать автора» (маленькая строка под кнопками) ----
	var support := HBoxContainer.new()
	support.alignment = BoxContainer.ALIGNMENT_CENTER
	_home.add_child(support)
	var sup_lbl := Label.new()
	sup_lbl.text = _t("support")
	support.add_child(sup_lbl)
	if _lang() != "en":
		var tips_btn := LinkButton.new()
		tips_btn.text = _t("support_tips")
		tips_btn.uri = URL_TIPS
		tips_btn.tooltip_text = URL_TIPS
		support.add_child(tips_btn)
		var sep := Label.new()
		sep.text = " · "
		support.add_child(sep)
	var boosty_btn := LinkButton.new()
	boosty_btn.text = _t("support_boosty")
	boosty_btn.uri = URL_BOOSTY
	boosty_btn.tooltip_text = URL_BOOSTY
	support.add_child(boosty_btn)

	# ---- СПИСОК ЧАТОВ ----
	_chats_view = VBoxContainer.new()
	_chats_view.size_flags_horizontal = SIZE_EXPAND_FILL
	_chats_view.size_flags_vertical = SIZE_EXPAND_FILL
	_chats_view.visible = false
	root.add_child(_chats_view)
	_chats_view.add_child(_make_header(_t("hdr_chats")))
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
	_sites_view.add_child(_make_header(_t("hdr_sites")))
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
	back.text = _t("back")
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
		empty.text = _t("no_chats")
		_chats_list.add_child(empty)
		return
	for c in _chats_data:
		if typeof(c) != TYPE_DICTIONARY:
			continue
		var btn := Button.new()
		var t := str(c.get("title", _t("untitled")))
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
		empty.text = _t("sites_empty")
		_sites_list.add_child(empty)
		return
	for s in _sites_data:
		if typeof(s) != TYPE_DICTIONARY:
			continue
		var btn := Button.new()
		btn.text = str(s.get("name", _t("site_fallback")))
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		btn.size_flags_horizontal = SIZE_EXPAND_FILL
		btn.pressed.connect(_pick_site.bind(str(s.get("id", ""))))
		_sites_list.add_child(btn)
	# ЗАГОТОВКА: кнопка «добавить свою страницу» (универсальный парсер) — позже.
	var add_own := Button.new()
	add_own.text = _t("add_own")
	add_own.disabled = true
	add_own.tooltip_text = _t("add_own_tip")
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
