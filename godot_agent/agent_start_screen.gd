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
signal open_server_requested()
signal settings_requested()
# Работа по ключу API. Панель на эти сигналы дёргает /api/* и возвращает
# результат через set_api_settings() / set_api_models() / set_api_test_result().
signal api_tab_requested()
signal api_settings_save_requested(data: Dictionary)
signal api_models_refresh_requested(provider: String, free_only: bool)
signal api_test_requested(provider: String, model: String)
signal new_api_chat_requested(provider: String, model: String)

const URL_BOOSTY := "https://boosty.to/zzzlichzzz"
const URL_TIPS := "https://pay.cloudtips.ru/p/50d418af"
# Запасной ASCII-спиннер: используется, только если иконки редактора нет.
const SPIN_FRAMES := ["|", "/", "-", "\\"]
# Высота кнопок главного экрана. Раньше кнопки тянулись на всю высоту панели
# и выглядели как две плашки во весь экран — теперь фиксированная высота.
const MAIN_BUTTON_HEIGHT := 42
const SECONDARY_BUTTON_HEIGHT := 30

var _home: VBoxContainer = null
var _chats_view: VBoxContainer = null
var _sites_view: VBoxContainer = null
var _chats_list: VBoxContainer = null
var _sites_list: VBoxContainer = null
var _chats_data: Array = []
var _sites_data: Array = []
var _built: bool = false
var _status: Label = null
var _status_panel: PanelContainer = null
var _api_key_btn: Button = null  # заготовка «Использовать API-ключ»
var _loading_view: VBoxContainer = null
var _loading_spinner: Label = null
var _loading_icon: TextureRect = null
var _loading_label: Label = null
var _spin_timer: Timer = null
var _spin_idx: int = 0
var _return_view: String = "home"
var _loc = null
var _theme_script = null
var _server_btn: Button = null
var _server_hint: Label = null
var _server_running: bool = false  # v41: раньше по умолчанию считали сервер уже запущенным (кнопка скрыта)
var _loading_server_btn: Button = null  # v41: та же кнопка, но продублирована прямо на экране ожидания,
var _loading_server_hint: Label = null  # где её реально видит пользователь, а не только у языковой строки.

# ---- Работа по ключу API ----
var _api_view: VBoxContainer = null
var _api_provider_opt: OptionButton = null
var _api_provider_ids: Array = []
var _api_note: Label = null
var _api_key_edit: LineEdit = null
var _api_key_state: Label = null
var _api_base_row: HBoxContainer = null
var _api_base_edit: LineEdit = null
var _api_model_edit: LineEdit = null
var _api_model_opt: OptionButton = null
var _api_free_only: CheckBox = null
var _api_proxy_on: CheckBox = null
var _api_proxy_host: LineEdit = null
var _api_proxy_port: SpinBox = null
var _api_proxy_user: LineEdit = null
var _api_proxy_pass: LineEdit = null
var _api_test_state: Label = null
var _api_cfg_path: Label = null
var _api_start_btn: Button = null
var _api_data: Dictionary = {}
# Пока форма заполняется ответом сервера, обработчики изменения полей молчат:
# иначе программная установка значений выглядела бы как правка пользователем и
# уходила бы обратно на сервер.
var _api_filling: bool = false


func _T():
	# Единый модуль оформления — тот же, что у карточек чата.
	if _theme_script == null:
		var sc := get_script() as Script
		if sc:
			var p := sc.resource_path.get_base_dir() + "/agent_theme.gd"
			if FileAccess.file_exists(p):
				_theme_script = load(p)
	return _theme_script


func _color(key: String) -> Color:
	var T = _T()
	if T == null:
		return Color.WHITE
	return T.color(key)


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
	_status_panel = null
	_api_key_btn = null
	_loading_view = null
	_loading_spinner = null
	_loading_icon = null
	_loading_label = null
	_spin_timer = null
	_loading_server_btn = null
	_loading_server_hint = null
	_build()
	show_home()


# ---------------- Кнопка ручного запуска сервера ----------------


func set_server_running(running: bool) -> void:
	# вызывается из agent_panel.gd при каждом server_state_changed.
	_server_running = running
	_apply_server_visibility()


func _apply_server_visibility() -> void:
	if _server_btn:
		_server_btn.visible = not _server_running
	if _server_hint:
		_server_hint.visible = not _server_running
	if _loading_server_btn:
		_loading_server_btn.visible = not _server_running
	if _loading_server_hint:
		_loading_server_hint.visible = not _server_running


# ---------------- Построение интерфейса ----------------

func _build() -> void:
	if _built:
		return
	_built = true
	var T = _T()
	var root := VBoxContainer.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 8)
	add_child(root)

	# Отдельная строка НАД языковой (v38): кнопка ручного запуска сервера.
	# В v37 она сидела в одной строке с языковым переключателем и заголовком:
	# вместе они не влезали в узкую пристёгнутую панель (190px под текст-подсказку +
	# кнопка + язык + выпадающий заголовок), и HBoxContainer просто обрезал/сжимал
	# содержимое — кнопку и переключатель языка было не видно. Сейчас кнопка —
	# отдельная полностью своя строка НАД языковой строкой, и постоянная подсказка убрана —
	# объяснение теперь только в tooltip_text кнопки (всё равно видно при наведении). Скрыта
	# (и занимает 0 высоты), когда сервер отвечает — см. _apply_server_visibility().
	var server_row := HBoxContainer.new()
	server_row.alignment = BoxContainer.ALIGNMENT_CENTER
	root.add_child(server_row)
	_server_btn = Button.new()
	_server_btn.text = _t("srv_open_folder_btn")
	_server_btn.tooltip_text = _t("srv_open_folder_tip") + " " + _t("srv_manual_hint")
	_server_btn.pressed.connect(func(): open_server_requested.emit())
	if T:
		T.style_button(_server_btn, "warning")
		_server_btn.icon = T.first_icon(["Load", "Folder"])
	server_row.add_child(_server_btn)
	_server_hint = Label.new()
	_server_hint.text = _t("srv_manual_hint")
	# текст подсказки длинный и без переноса строк вылезал за край узкой панели —
	# переносим часть текста на следующую строку, а не уменьшаем сам текст.
	_server_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_server_hint.size_flags_horizontal = SIZE_EXPAND_FILL
	_server_hint.add_theme_color_override("font_color", _color("dim"))
	server_row.add_child(_server_hint)

	# Верхняя строка: заголовок + переключатель языка (теперь без кнопки сервера —
	# её место выше, чтобы она не спорила место с языковым переключателем в узкой панели).
	var top := HBoxContainer.new()
	root.add_child(top)
	var top_spacer := Control.new()
	top_spacer.size_flags_horizontal = SIZE_EXPAND_FILL
	top.add_child(top_spacer)
	var lang_lbl := Label.new()
	lang_lbl.text = _t("lang_label")
	lang_lbl.add_theme_color_override("font_color", _color("dim"))
	top.add_child(lang_lbl)
	var lang_btn := OptionButton.new()
	lang_btn.add_item("Русский", 0)
	lang_btn.add_item("English", 1)
	lang_btn.select(1 if _lang() == "en" else 0)
	lang_btn.item_selected.connect(_on_lang_selected)
	top.add_child(lang_btn)
	var settings_btn := Button.new()
	settings_btn.name = "MiniLichSettingsBtn"
	settings_btn.tooltip_text = _t("settings_title")
	settings_btn.pressed.connect(func(): settings_requested.emit())
	# Иконка редактора вместо символа «⚙» — как в строке чатов.
	if T:
		T.style_icon_button(settings_btn, ["Tools", "GDScript"], "⚙")
	else:
		settings_btn.text = "⚙"
	top.add_child(settings_btn)

	# Заголовок в карточке-шапке: тот же StyleBoxFlat, что у сообщений чата.
	var title_panel := PanelContainer.new()
	if T:
		title_panel.add_theme_stylebox_override("panel", T.panel_style("agent"))
	var title := Label.new()
	title.text = _t("title")
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.size_flags_horizontal = SIZE_EXPAND_FILL
	title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	title.add_theme_color_override("font_color", _color("accent"))
	title.add_theme_font_size_override("font_size", 20)
	title_panel.add_child(title)
	root.add_child(title_panel)
	_apply_server_visibility()

	# ---- ГЛАВНАЯ: основные действия по центру экрана ----
	# Раньше две кнопки растягивались на всю высоту (SIZE_EXPAND_FILL по
	# вертикали) и выглядели как две огромные плашки — главная страница почти
	# не отличалась от списков чатов/сайтов. Теперь кнопки фиксированной
	# высоты, собраны в карточку по центру и разделены на «основные» и
	# «дополнительные».
	_home = VBoxContainer.new()
	_home.size_flags_horizontal = SIZE_EXPAND_FILL
	_home.size_flags_vertical = SIZE_EXPAND_FILL
	_home.add_theme_constant_override("separation", 10)
	root.add_child(_home)

	# Верхний отступ прижимает блок кнопок к центру.
	var top_pad := Control.new()
	top_pad.size_flags_vertical = SIZE_EXPAND_FILL
	top_pad.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_home.add_child(top_pad)

	var hint := Label.new()
	hint.text = _t("hint")
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.add_theme_color_override("font_color", _color("dim"))
	_home.add_child(hint)

	# Карточка с действиями — тот же стиль, что у сообщений чата.
	var actions_card := PanelContainer.new()
	if T:
		actions_card.add_theme_stylebox_override("panel", T.panel_style("agent"))
	_home.add_child(actions_card)
	var actions := VBoxContainer.new()
	actions.add_theme_constant_override("separation", 8)
	actions_card.add_child(actions)

	var b_new := Button.new()
	b_new.text = _t("btn_new")
	b_new.custom_minimum_size = Vector2(0, MAIN_BUTTON_HEIGHT)
	b_new.size_flags_horizontal = SIZE_EXPAND_FILL
	b_new.pressed.connect(func(): sites_tab_requested.emit())
	# Главное действие — акцентная и не плоская.
	if T:
		T.style_button(b_new, "accent", false)
		b_new.icon = T.first_icon(["Add", "Script"])
	actions.add_child(b_new)

	var b_load := Button.new()
	b_load.text = _t("btn_load")
	b_load.custom_minimum_size = Vector2(0, MAIN_BUTTON_HEIGHT)
	b_load.size_flags_horizontal = SIZE_EXPAND_FILL
	b_load.pressed.connect(func(): chats_tab_requested.emit())
	if T:
		T.style_button(b_load, "neutral", false)
		b_load.icon = T.first_icon(["Load", "Folder"])
	actions.add_child(b_load)

	actions.add_child(HSeparator.new())

	# Работа напрямую через API нейросети вместо браузера.
	_api_key_btn = Button.new()
	_api_key_btn.name = "ApiKeyBtn"
	_api_key_btn.text = _t("btn_api_key")
	_api_key_btn.tooltip_text = _t("btn_api_key_tip")
	_api_key_btn.custom_minimum_size = Vector2(0, SECONDARY_BUTTON_HEIGHT)
	_api_key_btn.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_key_btn.pressed.connect(func(): api_tab_requested.emit())
	if T:
		T.style_button(_api_key_btn, "neutral")
		_api_key_btn.icon = T.first_icon(["Key", "Lock", "Tools"])
	actions.add_child(_api_key_btn)

	# Нижний отступ — вторая половина центрирования.
	var bottom_pad := Control.new()
	bottom_pad.size_flags_vertical = SIZE_EXPAND_FILL
	bottom_pad.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_home.add_child(bottom_pad)

	# ---- Блок «Поддержать автора» (маленькая строка под кнопками) ----
	var support := HBoxContainer.new()
	support.alignment = BoxContainer.ALIGNMENT_CENTER
	_home.add_child(support)
	var sup_lbl := Label.new()
	sup_lbl.text = _t("support")
	sup_lbl.add_theme_color_override("font_color", _color("dim"))
	support.add_child(sup_lbl)
	if _lang() != "en":
		var tips_btn := LinkButton.new()
		tips_btn.text = _t("support_tips")
		tips_btn.uri = URL_TIPS
		tips_btn.tooltip_text = URL_TIPS
		tips_btn.add_theme_color_override("font_color", _color("accent"))
		support.add_child(tips_btn)
		var sep := Label.new()
		sep.text = " · "
		sep.add_theme_color_override("font_color", _color("dim"))
		support.add_child(sep)
	var boosty_btn := LinkButton.new()
	boosty_btn.text = _t("support_boosty")
	boosty_btn.uri = URL_BOOSTY
	boosty_btn.tooltip_text = URL_BOOSTY
	boosty_btn.add_theme_color_override("font_color", _color("accent"))
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

	# ---- НАСТРОЙКИ РАБОТЫ ПО КЛЮЧУ API ----
	_build_api_view(root)

	# ---- СТАТУСНАЯ СТРОКА (запуск сервера, загрузка страниц и т.п.) ----
	# Обёрнута в панель со стилем — как строка статуса в чате.
	_status_panel = PanelContainer.new()
	if T:
		_status_panel.add_theme_stylebox_override("panel", T.panel_style("agent"))
	_status_panel.visible = false
	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status_panel.add_child(_status)
	root.add_child(_status_panel)

	_loading_view = VBoxContainer.new()
	_loading_view.size_flags_horizontal = SIZE_EXPAND_FILL
	_loading_view.size_flags_vertical = SIZE_EXPAND_FILL
	_loading_view.alignment = BoxContainer.ALIGNMENT_CENTER
	_loading_view.add_theme_constant_override("separation", 10)
	_loading_view.visible = false
	root.add_child(_loading_view)

	# Спиннер: вращающаяся иконка редактора, как в AgentStatusBar.
	# ASCII-кадры («|/-\») остаются запасным вариантом, если иконки нет.
	var spin_icon: Texture2D = null
	if T:
		spin_icon = T.first_icon(["Progress1", "ProgressIndicator", "Reload"])
	_loading_icon = TextureRect.new()
	if spin_icon != null:
		_loading_icon.texture = spin_icon
		_loading_icon.custom_minimum_size = Vector2(32, 32)
		_loading_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		_loading_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		_loading_icon.size_flags_horizontal = SIZE_SHRINK_CENTER
		_loading_icon.pivot_offset = Vector2(16, 16)
		_loading_icon.modulate = _color("accent")
	else:
		_loading_icon.visible = false
	_loading_view.add_child(_loading_icon)

	_loading_spinner = Label.new()
	_loading_spinner.text = "|"
	_loading_spinner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_loading_spinner.add_theme_font_size_override("font_size", 32)
	_loading_spinner.add_theme_color_override("font_color", _color("accent"))
	# Текстовый спиннер нужен только когда иконки нет.
	_loading_spinner.visible = spin_icon == null
	_loading_view.add_child(_loading_spinner)

	_loading_label = Label.new()
	_loading_label.text = "..."
	_loading_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_loading_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_loading_label.add_theme_color_override("font_color", _color("text"))
	_loading_view.add_child(_loading_label)
	# v41: дубликат кнопки ручного запуска сервера — прямо на экране ожидания.
	# Верхняя строка (server_row, рядом с языком) в некоторых случаях не была замечена
	# пользователем/не успевала обновиться до первого сигнала от сервера, из-за чего
	# кнопка казалась "пропавшей" именно в момент, когда она нужнее всего — во время
	# ожидания старта сервера. Эта копия живёт внутри _loading_view и управляется тем
	# же _apply_server_visibility(), так что видна ровно тогда же, когда и верхняя.
	var loading_srv_row := HBoxContainer.new()
	loading_srv_row.alignment = BoxContainer.ALIGNMENT_CENTER
	_loading_view.add_child(loading_srv_row)
	_loading_server_btn = Button.new()
	_loading_server_btn.text = _t("srv_open_folder_btn")
	_loading_server_btn.tooltip_text = _t("srv_open_folder_tip") + " " + _t("srv_manual_hint")
	_loading_server_btn.pressed.connect(func(): open_server_requested.emit())
	if T:
		T.style_button(_loading_server_btn, "warning")
		_loading_server_btn.icon = T.first_icon(["Load", "Folder"])
	loading_srv_row.add_child(_loading_server_btn)
	_loading_server_hint = Label.new()
	_loading_server_hint.text = _t("srv_manual_hint")
	# аналогично _server_hint выше — длинный текст подсказки переносится на строки, а не съедается краем экрана.
	_loading_server_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_loading_server_hint.size_flags_horizontal = SIZE_EXPAND_FILL
	_loading_server_hint.add_theme_color_override("font_color", _color("dim"))
	loading_srv_row.add_child(_loading_server_hint)
	_spin_timer = Timer.new()
	_spin_timer.wait_time = 0.12
	_spin_timer.one_shot = false
	add_child(_spin_timer)
	_spin_timer.timeout.connect(_on_spin_tick)


func _api_section(parent: Node, title_key: String) -> VBoxContainer:
	# Блок настроек: подпись-заголовок + вертикальный контейнер под поля.
	var lbl := Label.new()
	lbl.text = _t(title_key)
	lbl.add_theme_color_override("font_color", _color("accent"))
	parent.add_child(lbl)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 4)
	parent.add_child(box)
	return box


func _api_hint(parent: Node, text: String) -> Label:
	var lbl := Label.new()
	lbl.text = text
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lbl.size_flags_horizontal = SIZE_EXPAND_FILL
	lbl.add_theme_color_override("font_color", _color("dim"))
	parent.add_child(lbl)
	return lbl


func _build_api_view(root: Node) -> void:
	var T = _T()
	_api_view = VBoxContainer.new()
	_api_view.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_view.size_flags_vertical = SIZE_EXPAND_FILL
	_api_view.visible = false
	root.add_child(_api_view)
	_api_view.add_child(_make_header(_t("hdr_api")))

	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = SIZE_EXPAND_FILL
	scroll.size_flags_vertical = SIZE_EXPAND_FILL
	_api_view.add_child(scroll)
	var form := VBoxContainer.new()
	form.size_flags_horizontal = SIZE_EXPAND_FILL
	form.add_theme_constant_override("separation", 8)
	scroll.add_child(form)

	# ---- Провайдер ----
	var prov_box := _api_section(form, "api_provider")
	_api_provider_opt = OptionButton.new()
	_api_provider_opt.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_provider_opt.item_selected.connect(_on_api_provider_selected)
	prov_box.add_child(_api_provider_opt)
	_api_note = _api_hint(prov_box, "")

	# ---- Ключ ----
	var key_box := _api_section(form, "api_key")
	var key_row := HBoxContainer.new()
	key_row.size_flags_horizontal = SIZE_EXPAND_FILL
	key_box.add_child(key_row)
	_api_key_edit = LineEdit.new()
	# secret = true: ключ не должен быть виден на экране — в том числе на
	# записи экрана или стриме, где его увидели бы посторонние.
	_api_key_edit.secret = true
	_api_key_edit.placeholder_text = _t("api_key_placeholder")
	_api_key_edit.size_flags_horizontal = SIZE_EXPAND_FILL
	key_row.add_child(_api_key_edit)
	var key_save := Button.new()
	key_save.text = _t("api_key_save")
	key_save.pressed.connect(_on_api_key_save)
	if T:
		T.style_button(key_save, "accent")
		key_save.icon = T.first_icon(["Save", "FileList"])
	key_row.add_child(key_save)
	var key_del := Button.new()
	key_del.text = _t("api_key_delete")
	key_del.tooltip_text = _t("api_key_delete_tip")
	key_del.pressed.connect(_on_api_key_delete)
	if T:
		T.style_button(key_del, "warning")
		key_del.icon = T.first_icon(["Remove", "Close"])
	key_row.add_child(key_del)
	_api_key_state = _api_hint(key_box, "")

	# ---- Свой адрес endpoint'а (только у провайдера «свой адрес») ----
	_api_base_row = HBoxContainer.new()
	_api_base_row.size_flags_horizontal = SIZE_EXPAND_FILL
	key_box.add_child(_api_base_row)
	var base_lbl := Label.new()
	base_lbl.text = _t("api_base_url")
	_api_base_row.add_child(base_lbl)
	_api_base_edit = LineEdit.new()
	_api_base_edit.placeholder_text = "http://127.0.0.1:8080/v1"
	_api_base_edit.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_base_edit.text_submitted.connect(func(_s): _on_api_save_fields())
	_api_base_edit.focus_exited.connect(_on_api_save_fields)
	_api_base_row.add_child(_api_base_edit)

	# ---- Модель ----
	var model_box := _api_section(form, "api_model")
	_api_model_edit = LineEdit.new()
	_api_model_edit.placeholder_text = _t("api_model_placeholder")
	_api_model_edit.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_model_edit.text_submitted.connect(func(_s): _on_api_save_fields())
	_api_model_edit.focus_exited.connect(_on_api_save_fields)
	model_box.add_child(_api_model_edit)
	var model_row := HBoxContainer.new()
	model_row.size_flags_horizontal = SIZE_EXPAND_FILL
	model_box.add_child(model_row)
	_api_model_opt = OptionButton.new()
	_api_model_opt.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_model_opt.item_selected.connect(_on_api_model_picked)
	model_row.add_child(_api_model_opt)
	var refresh := Button.new()
	refresh.text = _t("api_models_refresh")
	refresh.pressed.connect(_on_api_models_refresh)
	if T:
		T.style_button(refresh, "neutral")
		refresh.icon = T.first_icon(["Reload", "Loop"])
	model_row.add_child(refresh)
	_api_free_only = CheckBox.new()
	_api_free_only.text = _t("api_free_only")
	_api_free_only.button_pressed = true
	model_row.add_child(_api_free_only)
	# Идентификаторы моделей у сервисов меняются постоянно, поэтому поле
	# остаётся редактируемым: можно вписать любую модель руками, не дожидаясь
	# обновления плагина.
	_api_hint(model_box, _t("api_model_hint"))

	# ---- Прокси ----
	var proxy_box := _api_section(form, "api_proxy")
	_api_proxy_on = CheckBox.new()
	_api_proxy_on.text = _t("api_proxy_enable")
	_api_proxy_on.toggled.connect(func(_v): _on_api_save_fields())
	proxy_box.add_child(_api_proxy_on)
	var pr_row := HBoxContainer.new()
	pr_row.size_flags_horizontal = SIZE_EXPAND_FILL
	proxy_box.add_child(pr_row)
	var host_lbl := Label.new()
	host_lbl.text = _t("api_proxy_host")
	pr_row.add_child(host_lbl)
	_api_proxy_host = LineEdit.new()
	_api_proxy_host.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_proxy_host.text_submitted.connect(func(_s): _on_api_save_fields())
	_api_proxy_host.focus_exited.connect(_on_api_save_fields)
	pr_row.add_child(_api_proxy_host)
	_api_proxy_port = SpinBox.new()
	_api_proxy_port.min_value = 0
	_api_proxy_port.max_value = 65535
	_api_proxy_port.step = 1
	_api_proxy_port.value = 0
	_api_proxy_port.value_changed.connect(func(_v): _on_api_save_fields())
	pr_row.add_child(_api_proxy_port)
	var auth_row := HBoxContainer.new()
	auth_row.size_flags_horizontal = SIZE_EXPAND_FILL
	proxy_box.add_child(auth_row)
	_api_proxy_user = LineEdit.new()
	_api_proxy_user.placeholder_text = _t("api_proxy_user")
	_api_proxy_user.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_proxy_user.focus_exited.connect(_on_api_save_fields)
	auth_row.add_child(_api_proxy_user)
	_api_proxy_pass = LineEdit.new()
	_api_proxy_pass.secret = true
	_api_proxy_pass.placeholder_text = _t("api_proxy_pass")
	_api_proxy_pass.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_proxy_pass.focus_exited.connect(_on_api_save_fields)
	auth_row.add_child(_api_proxy_pass)
	_api_hint(proxy_box, _t("api_proxy_hint"))

	# ---- Проверка подключения ----
	var test_btn := Button.new()
	test_btn.text = _t("api_test")
	test_btn.tooltip_text = _t("api_test_tip")
	test_btn.size_flags_horizontal = SIZE_EXPAND_FILL
	test_btn.pressed.connect(_on_api_test)
	if T:
		T.style_button(test_btn, "neutral")
		test_btn.icon = T.first_icon(["NetworkConnected", "Play"])
	form.add_child(test_btn)
	_api_test_state = _api_hint(form, "")

	# ---- Где лежит ключ и куда уходит код ----
	form.add_child(HSeparator.new())
	_api_cfg_path = _api_hint(form, "")
	_api_cfg_path.tooltip_text = _t("api_cfg_path_tip")
	var privacy := _api_hint(form, _t("api_privacy"))
	privacy.add_theme_color_override("font_color", _color("warning"))

	# ---- Начать чат ----
	_api_start_btn = Button.new()
	_api_start_btn.text = _t("api_start_chat")
	_api_start_btn.custom_minimum_size = Vector2(0, MAIN_BUTTON_HEIGHT)
	_api_start_btn.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_start_btn.pressed.connect(_on_api_start_chat)
	if T:
		T.style_button(_api_start_btn, "accent", false)
		_api_start_btn.icon = T.first_icon(["Add", "Script"])
	_api_view.add_child(_api_start_btn)


func _make_header(text: String) -> HBoxContainer:
	var T = _T()
	var head := HBoxContainer.new()
	var back := Button.new()
	back.text = _t("back")
	back.pressed.connect(show_home)
	if T:
		T.style_button(back, "neutral")
		back.icon = T.first_icon(["Back", "ArrowLeft"])
	head.add_child(back)
	var lbl := Label.new()
	lbl.text = text
	lbl.size_flags_horizontal = SIZE_EXPAND_FILL
	lbl.add_theme_color_override("font_color", _color("accent"))
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
	var T = _T()
	_clear_container(_chats_list)
	if _chats_data.is_empty():
		var empty := Label.new()
		empty.text = _t("no_chats")
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		empty.add_theme_color_override("font_color", _color("dim"))
		_chats_list.add_child(empty)
		return
	for c in _chats_data:
		if typeof(c) != TYPE_DICTIONARY:
			continue
		var btn := Button.new()
		var t := str(c.get("title", _t("untitled")))
		var sname := str(c.get("site_name", ""))
		# v48: сайт нейросети, время последнего использования и признак «промпт устарел».
		var info := PackedStringArray()
		if sname != "":
			info.append(sname)
		var used_ts := int(c.get("last_used", 0))
		if used_ts > 0:
			info.append(_fmt_ts(used_ts))
		var stale := bool(c.get("prompt_stale", false))
		if stale:
			info.append(_t("prompt_stale_short"))
		btn.text = t if info.is_empty() else (t + "   — " + " · ".join(info))
		btn.tooltip_text = _t("tip_chat_times") % [_fmt_ts(int(c.get("created", 0))), _fmt_ts(used_ts)]
		if T:
			# «Промпт устарел» — предупреждающим цветом темы вместо хардкода.
			T.style_button(btn, "warning" if stale else "neutral")
			btn.icon = T.first_icon(["Script", "File"])
		if stale:
			btn.tooltip_text += "\n" + _t("prompt_stale_tip")
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		btn.clip_text = true
		btn.size_flags_horizontal = SIZE_EXPAND_FILL
		btn.pressed.connect(_pick_chat.bind(str(c.get("id", ""))))
		_chats_list.add_child(btn)


func _fmt_ts(ts: int) -> String:
	# Локальное время «ДД.ММ ЧЧ:ММ» из unix-времени (сервер пишет time.time()).
	if ts <= 0:
		return "—"
	var bias := 0
	var tz: Dictionary = Time.get_time_zone_from_system()
	if tz.has("bias"):
		bias = int(tz["bias"])  # смещение локальной зоны в минутах
	var d := Time.get_datetime_dict_from_unix_time(ts + bias * 60)
	return "%02d.%02d %02d:%02d" % [int(d.get("day", 0)), int(d.get("month", 0)), int(d.get("hour", 0)), int(d.get("minute", 0))]


func _rebuild_sites() -> void:
	if _sites_list == null:
		return
	var T = _T()
	_clear_container(_sites_list)
	if _sites_data.is_empty():
		var empty := Label.new()
		empty.text = _t("sites_empty")
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		empty.add_theme_color_override("font_color", _color("dim"))
		_sites_list.add_child(empty)
		return
	for s in _sites_data:
		if typeof(s) != TYPE_DICTIONARY:
			continue
		var btn := Button.new()
		btn.text = str(s.get("name", _t("site_fallback")))
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		btn.clip_text = true
		btn.size_flags_horizontal = SIZE_EXPAND_FILL
		btn.pressed.connect(_pick_site.bind(str(s.get("id", ""))))
		if T:
			T.style_button(btn, "neutral")
			btn.icon = T.first_icon(["Environment", "Node"])
		_sites_list.add_child(btn)
	# ЗАГОТОВКА: кнопка «добавить свою страницу» (универсальный парсер) — позже.
	var add_own := Button.new()
	add_own.text = _t("add_own")
	add_own.disabled = true
	add_own.tooltip_text = _t("add_own_tip")
	add_own.size_flags_horizontal = SIZE_EXPAND_FILL
	if T:
		T.style_button(add_own, "dim")
		add_own.icon = T.first_icon(["Add"])
	_sites_list.add_child(add_own)


func _pick_chat(chat_id: String) -> void:
	if chat_id != "":
		load_chat_requested.emit(chat_id)


func _pick_site(site_id: String) -> void:
	if site_id != "":
		new_chat_requested.emit(site_id)


# ---------------------------------------------------------------------------
# Работа по ключу API: заполнение формы и обработчики.
# ---------------------------------------------------------------------------

func _api_current_provider() -> String:
	if _api_provider_opt == null:
		return ""
	var idx := _api_provider_opt.selected
	if idx < 0 or idx >= _api_provider_ids.size():
		return ""
	return str(_api_provider_ids[idx])


func _api_provider_rec(pid: String) -> Dictionary:
	for p in _api_data.get("providers", []):
		if typeof(p) == TYPE_DICTIONARY and str(p.get("id", "")) == pid:
			return p
	return {}


func set_api_settings(json: Dictionary) -> void:
	# Единственный источник состояния формы — ответ сервера. Панель ничего не
	# домысливает сама, поэтому после любого сохранения форма перерисовывается
	# целиком и не может разойтись с тем, что реально записано на диске.
	if typeof(json) != TYPE_DICTIONARY or _api_provider_opt == null:
		return
	if json.has("providers"):
		_api_data = json
	_api_filling = true
	var want := _api_current_provider()
	if want == "":
		want = str(_api_data.get("defaults", {}).get("provider", ""))
	_api_provider_opt.clear()
	_api_provider_ids.clear()
	var sel := 0
	for p in _api_data.get("providers", []):
		if typeof(p) != TYPE_DICTIONARY:
			continue
		var pid := str(p.get("id", ""))
		var mark := "" if bool(p.get("ready", false)) else ("  — " + _t("api_not_ready"))
		_api_provider_opt.add_item(str(p.get("name", pid)) + mark)
		_api_provider_ids.append(pid)
		if pid == want:
			sel = _api_provider_ids.size() - 1
	if _api_provider_ids.size() > 0:
		_api_provider_opt.selected = sel
	_api_fill_provider_fields()
	var proxy: Dictionary = _api_data.get("proxy", {})
	if _api_proxy_on:
		_api_proxy_on.button_pressed = bool(proxy.get("enabled", false))
	if _api_proxy_host:
		_api_proxy_host.text = str(proxy.get("host", ""))
	if _api_proxy_port:
		_api_proxy_port.value = int(proxy.get("port", 0))
	if _api_proxy_user:
		_api_proxy_user.text = str(proxy.get("user", ""))
	if _api_proxy_pass:
		# Сам пароль сервер не отдаёт — показываем только факт его наличия.
		_api_proxy_pass.text = ""
		_api_proxy_pass.placeholder_text = _t("api_proxy_pass_set") \
			if bool(proxy.get("has_password", false)) else _t("api_proxy_pass")
	if _api_cfg_path:
		_api_cfg_path.text = _t("api_cfg_path") % str(_api_data.get("config_path", "?"))
	_api_filling = false


func _api_fill_provider_fields() -> void:
	var pid := _api_current_provider()
	var rec := _api_provider_rec(pid)
	var lang_note := "note_ru" if _lang() != "en" else "note_en"
	if _api_note:
		_api_note.text = str(rec.get(lang_note, ""))
	if _api_model_edit:
		_api_model_edit.text = str(rec.get("model", ""))
	if _api_base_edit:
		_api_base_edit.text = str(rec.get("base_url", ""))
	if _api_base_row:
		# Поле адреса имеет смысл только там, где адрес задаёт пользователь
		# (провайдер «свой адрес», в будущем — локальный llama-server).
		_api_base_row.visible = bool(rec.get("base_url_editable", false))
	if _api_key_edit:
		# Введённый ключ в поле не остаётся: показывать его повторно незачем,
		# а хранить в памяти узла — лишний риск.
		_api_key_edit.text = ""
		_api_key_edit.editable = str(rec.get("key_source", "")) != "env"
	if _api_key_state:
		var src := str(rec.get("key_source", ""))
		if src == "env":
			_api_key_state.text = _t("api_key_from_env") % str(rec.get("masked", ""))
		elif bool(rec.get("configured", false)):
			_api_key_state.text = _t("api_key_set") % str(rec.get("masked", ""))
		elif bool(rec.get("needs_key", true)):
			_api_key_state.text = _t("api_key_missing")
		else:
			_api_key_state.text = _t("api_key_optional")
	if _api_start_btn:
		_api_start_btn.disabled = not bool(rec.get("ready", false))
		_api_start_btn.tooltip_text = "" if bool(rec.get("ready", false)) \
			else str(rec.get("not_ready_reason", ""))
	if _api_test_state:
		_api_test_state.text = ""


func _on_api_provider_selected(_idx: int) -> void:
	if _api_filling:
		return
	_api_fill_provider_fields()
	if _api_model_opt:
		_api_model_opt.clear()


func _api_proxy_payload(include_password: bool) -> Dictionary:
	var pr := {
		"enabled": _api_proxy_on.button_pressed if _api_proxy_on else false,
		"host": _api_proxy_host.text.strip_edges() if _api_proxy_host else "",
		"port": int(_api_proxy_port.value) if _api_proxy_port else 0,
		"user": _api_proxy_user.text.strip_edges() if _api_proxy_user else "",
	}
	# Пароль отправляем ТОЛЬКО когда пользователь его действительно ввёл:
	# пустое поле означает «не менять», иначе правка хоста стирала бы пароль.
	if include_password and _api_proxy_pass and _api_proxy_pass.text != "":
		pr["password"] = _api_proxy_pass.text
	return pr


func _on_api_save_fields() -> void:
	if _api_filling:
		return
	var pid := _api_current_provider()
	if pid == "":
		return
	var data := {
		"provider": pid,
		"model": _api_model_edit.text.strip_edges() if _api_model_edit else "",
		"proxy": _api_proxy_payload(true),
	}
	# base_url отправляем ТОЛЬКО там, где адрес задаёт пользователь. Иначе мы
	# записали бы текущий адрес провайдера как «переопределение», и обновление
	# реестра в новой версии плагина перестало бы действовать — пользователь
	# навсегда остался бы на старом адресе, не понимая почему.
	if _api_base_row and _api_base_row.visible and _api_base_edit:
		data["base_url"] = _api_base_edit.text.strip_edges()
	api_settings_save_requested.emit(data)


func _on_api_key_save() -> void:
	var pid := _api_current_provider()
	if pid == "" or _api_key_edit == null:
		return
	var key := _api_key_edit.text.strip_edges()
	if key == "":
		set_status(_t("api_key_empty"), "error")
		return
	api_settings_save_requested.emit({
		"provider": pid, "key": key, "make_default": true,
		"model": _api_model_edit.text.strip_edges() if _api_model_edit else "",
	})


func _on_api_key_delete() -> void:
	var pid := _api_current_provider()
	if pid == "":
		return
	api_settings_save_requested.emit({"provider": pid, "key": ""})


func _on_api_models_refresh() -> void:
	var pid := _api_current_provider()
	if pid == "":
		return
	set_status(_t("api_models_loading"), "status")
	api_models_refresh_requested.emit(
		pid, _api_free_only.button_pressed if _api_free_only else false)


func set_api_models(provider: String, models: Array) -> void:
	if _api_model_opt == null:
		return
	if provider != "" and provider != _api_current_provider():
		return  # ответ про другого провайдера — пользователь уже переключился
	_api_model_opt.clear()
	if models.is_empty():
		_api_model_opt.add_item(_t("api_models_none"))
		_api_model_opt.disabled = true
		return
	_api_model_opt.disabled = false
	for m in models:
		_api_model_opt.add_item(str(m))
	set_status(_t("api_models_loaded") % models.size(), "success")


func _on_api_model_picked(idx: int) -> void:
	if _api_model_opt == null or _api_model_opt.disabled:
		return
	if idx < 0 or idx >= _api_model_opt.item_count:
		return
	if _api_model_edit:
		_api_model_edit.text = _api_model_opt.get_item_text(idx)
	_on_api_save_fields()


func _on_api_test() -> void:
	var pid := _api_current_provider()
	if pid == "":
		return
	if _api_test_state:
		_api_test_state.text = _t("api_test_running")
		_api_test_state.add_theme_color_override("font_color", _color("dim"))
	api_test_requested.emit(
		pid, _api_model_edit.text.strip_edges() if _api_model_edit else "")


func set_api_test_result(json: Dictionary) -> void:
	if _api_test_state == null:
		return
	var ok := bool(json.get("ok", false))
	var text := str(json.get("message", "")) if ok else str(json.get("error", ""))
	if text == "":
		text = _t("api_test_ok") if ok else _t("api_test_fail")
	_api_test_state.text = text
	_api_test_state.add_theme_color_override(
		"font_color", _color("success") if ok else _color("error"))


func _on_api_start_chat() -> void:
	var pid := _api_current_provider()
	if pid == "":
		return
	new_api_chat_requested.emit(
		pid, _api_model_edit.text.strip_edges() if _api_model_edit else "")


func show_home() -> void:
	_stop_loading_visual()
	if _home: _home.visible = true
	if _chats_view: _chats_view.visible = false
	if _sites_view: _sites_view.visible = false
	if _api_view: _api_view.visible = false


func show_chats() -> void:
	_stop_loading_visual()
	_rebuild_chats()
	if _home: _home.visible = false
	if _chats_view: _chats_view.visible = true
	if _sites_view: _sites_view.visible = false
	if _api_view: _api_view.visible = false


func show_sites() -> void:
	_stop_loading_visual()
	_rebuild_sites()
	if _home: _home.visible = false
	if _sites_view: _sites_view.visible = true
	if _chats_view: _chats_view.visible = false
	if _api_view: _api_view.visible = false


func show_api() -> void:
	_stop_loading_visual()
	if _home: _home.visible = false
	if _sites_view: _sites_view.visible = false
	if _chats_view: _chats_view.visible = false
	if _api_view: _api_view.visible = true


func set_status(text: String, kind: String = "info") -> void:
	# Статус внизу экрана: виден из любого подраздела стартового экрана.
	if _status == null:
		return
	_status.text = text
	# Панель прячется вместе с текстом, иначе оставалась бы пустая рамка.
	if _status_panel:
		_status_panel.visible = text != ""
	_status.visible = text != ""
	# Цвета из темы редактора вместо захардкоженных.
	var key := "text"
	if kind == "success":
		key = "success"
	elif kind == "error":
		key = "error"
	elif kind == "status":
		key = "warning"
	_status.add_theme_color_override("font_color", _color(key))


func show_loading(text: String) -> void:
	if not is_loading():
		if _sites_view and _sites_view.visible:
			_return_view = "sites"
		elif _chats_view and _chats_view.visible:
			_return_view = "chats"
		elif _api_view and _api_view.visible:
			_return_view = "api"
		else:
			_return_view = "home"
	if _home: _home.visible = false
	if _chats_view: _chats_view.visible = false
	if _sites_view: _sites_view.visible = false
	if _api_view: _api_view.visible = false
	if _loading_view: _loading_view.visible = true
	if _loading_label: _loading_label.text = text
	if _spin_timer: _spin_timer.start()
	_apply_server_visibility()


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
		"api":
			show_api()
		_:
			show_home()


func _stop_loading_visual() -> void:
	if _spin_timer: _spin_timer.stop()
	if _loading_view: _loading_view.visible = false


func _on_spin_tick() -> void:
	_spin_idx = (_spin_idx + 1) % SPIN_FRAMES.size()
	if _loading_spinner and _loading_spinner.visible:
		_loading_spinner.text = SPIN_FRAMES[_spin_idx]
	# Иконка крутится с тем же шагом: 12 кадров на оборот (0.12с × 12 ≈ 1.4с).
	if _loading_icon and _loading_icon.visible:
		_loading_icon.rotation = TAU * (float(_spin_idx % 12) / 12.0)
