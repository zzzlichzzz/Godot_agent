@tool
extends Control

# ---------------------------------------------------------------------------
# Стартовый экран агента.
# Главная: три равноправных входа — новый чат, сохранённый чат и работа
# напрямую через API-ключ.
# Наружу отдаёт сигналы, а данные получает через set_chats()/set_sites().
# Локализация RU/EN — agent_locale.gd; переключатель языка — справа сверху.
# Блок «Поддержать автора»: для русского языка — CloudTips + Boosty,
# для английского — только Boosty (CloudTips не принимает зарубежные карты).
# ---------------------------------------------------------------------------

signal new_chat_requested(site_id)
signal load_chat_requested(chat_id)
signal delete_chat_requested(chat_id)
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
# Выбранный провайдер держим строкой, а не индексом выпадающего списка: список
# провайдеров теперь живёт в отдельном диалоге и перестраивается при каждом
# поиске и фильтре, а идентификатор выбранного от этого зависеть не должен.
var _api_selected_provider: String = ""
var _api_provider_btn: Button = null
var _api_provider_ids: Array = []
var _api_note: Label = null
var _api_key_edit: LineEdit = null
var _api_key_state: Label = null
var _api_base_row: HBoxContainer = null
var _api_base_edit: LineEdit = null
var _api_base_custom: Label = null
var _api_base_error: Label = null
var _api_model_edit: LineEdit = null
var _api_model_opt: OptionButton = null
var _api_free_only: CheckBox = null
var _api_proxy_on: CheckBox = null
var _api_proxy_host: LineEdit = null
var _api_proxy_port: SpinBox = null
var _api_proxy_user: LineEdit = null
var _api_proxy_pass: LineEdit = null
var _api_proxy_error: Label = null
var _api_dns_on: CheckBox = null
var _api_dns_url: LineEdit = null
var _api_dns_error: Label = null
var _api_ready_note: Label = null
var _api_test_state: Label = null
var _api_cfg_path: Label = null
var _api_start_btn: Button = null
var _api_data: Dictionary = {}
# ---- Диалог выбора провайдера ----
# Отдельным окном по центру редактора, а не списком внутри дока: док шириной
# 250–400 px не вмещает карточку с названием, пометками и описанием сразу.
var _api_pick_dialog: AcceptDialog = null
var _api_pick_list: VBoxContainer = null
var _api_pick_search: LineEdit = null
var _api_pick_empty: Label = null
# Фильтр: "all" | "free" | "ready". Не сортировка — на десятке провайдеров
# сортировать нечего, а вот отсеивать платных и ненастроенных полезно.
var _api_pick_filter: String = "all"
# Свёрнутые группы запоминаются между открытиями диалога: иначе «Пока
# недоступны» разворачивалась бы заново при каждом поиске.
var _api_pick_collapsed: Dictionary = {}
# Список моделей, полученный кнопкой «Обновить список», в разрезе провайдера:
# provider_id -> [идентификаторы]. Держим его отдельно от _api_data, потому что
# ответ сервера с настройками содержит ТОЛЬКО зашитый в реестр список (у
# большинства провайдеров он пуст намеренно — идентификаторы моделей меняются
# слишком часто). Без этого кэша выбор модели затирал бы сам себя: сохранение
# возвращает настройки, форма перерисовывается из реестра, и 62 только что
# загруженные модели исчезали из выпадающего списка.
var _api_fetched_models: Dictionary = {}
# Пока форма заполняется ответом сервера, обработчики изменения полей молчат:
# иначе программная установка значений выглядела бы как правка пользователем и
# уходила бы обратно на сервер.
var _api_filling: bool = false
var _delete_dialog: ConfirmationDialog = null
var _delete_chat_id: String = ""


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
	# Диалог выбора провайдера разбираем ДО общего цикла и вручную. Он модальный
	# (exclusive), а модальное окно остаётся «исключительным ребёнком»
	# родительского окна до фактического освобождения — queue_free() же отложен
	# до конца кадра. Диалог, созданный сразу после пересборки, не смог бы стать
	# модальным: Godot отвечает «parent window already has another exclusive
	# child» и окно ведёт себя как обычное. Снимаем модальность и изымаем узел
	# из дерева немедленно.
	if _api_pick_dialog and is_instance_valid(_api_pick_dialog):
		_api_pick_dialog.hide()
		_api_pick_dialog.exclusive = false
		remove_child(_api_pick_dialog)
		_api_pick_dialog.queue_free()
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
	_delete_dialog = null
	_delete_chat_id = ""
	_api_key_btn = null
	_loading_view = null
	_loading_spinner = null
	_loading_icon = null
	_loading_label = null
	_spin_timer = null
	_loading_server_btn = null
	_loading_server_hint = null
	# Диалог выбора провайдера создаётся по требованию, а не в _build(), поэтому
	# его надо обнулить здесь ЯВНО: queue_free() выше уже убил сам узел, а
	# переменная продолжала бы указывать на освобождённый объект — следующий
	# показ диалога упал бы, как когда-то падал статус-бар, получавший имя
	# AgentStatusBar2 вместо прежнего.
	_api_pick_dialog = null
	_api_pick_list = null
	_api_pick_search = null
	_api_pick_empty = null
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

	# Работа напрямую через API нейросети — такое же основное действие, как
	# новый или сохранённый браузерный чат.
	_api_key_btn = Button.new()
	_api_key_btn.name = "ApiKeyBtn"
	_api_key_btn.text = _t("btn_api_key")
	_api_key_btn.tooltip_text = _t("btn_api_key_tip")
	_api_key_btn.custom_minimum_size = Vector2(0, MAIN_BUTTON_HEIGHT)
	_api_key_btn.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_key_btn.pressed.connect(func(): api_tab_requested.emit())
	if T:
		T.style_button(_api_key_btn, "neutral", false)
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
	# Кнопка, а не выпадающий список: у провайдера кроме названия есть состояние
	# ключа, число бесплатных моделей и описание, а в строку OptionButton это не
	# помещается — там был виден только «Groq — не настроен». Полный список с
	# поиском и фильтрами открывается отдельным окном.
	var prov_box := _api_section(form, "api_provider")
	_api_provider_btn = Button.new()
	_api_provider_btn.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_provider_btn.custom_minimum_size = Vector2(0, 32)
	_api_provider_btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	_api_provider_btn.clip_text = true
	_api_provider_btn.tooltip_text = _t("api_provider_change_tip")
	_api_provider_btn.pressed.connect(_on_api_pick_open)
	if T:
		T.style_button(_api_provider_btn, "accent", false)
		_api_provider_btn.icon = T.first_icon(["GuiDropdown", "GuiOptionArrow", "Tools"])
	prov_box.add_child(_api_provider_btn)
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

	# ---- Адрес endpoint'а ----
	# Поле открыто у ВСЕХ провайдеров, а не только у «своего адреса»: сервис
	# может переехать, и тогда адрес исправляется здесь, без новой версии
	# плагина. Пустое поле означает «взять адрес из реестра», поэтому отдельной
	# кнопки сброса не нужно — достаточно очистить.
	var base_box := _api_section(form, "api_base_url")
	_api_base_row = HBoxContainer.new()
	_api_base_row.size_flags_horizontal = SIZE_EXPAND_FILL
	base_box.add_child(_api_base_row)
	_api_base_edit = LineEdit.new()
	_api_base_edit.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_base_edit.text_submitted.connect(func(_s): _on_api_save_fields())
	_api_base_edit.focus_exited.connect(_on_api_save_fields)
	_api_base_row.add_child(_api_base_edit)
	_api_hint(base_box, _t("api_base_url_hint"))
	# Подмена адреса — отдельной строкой: провайдер с чужим адресом ведёт себя
	# не так, как написано в его описании, и об этом надо сказать раньше, чем
	# человек пойдёт искать причину отказов в ключе.
	_api_base_custom = _api_hint(base_box, "")
	_api_base_custom.add_theme_color_override("font_color", _color("warning"))
	_api_base_error = _api_hint(base_box, "")
	_api_base_error.add_theme_color_override("font_color", _color("error"))

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

	# ---- DNS over HTTPS ----
	var dns_box := _api_section(form, "api_dns")
	_api_dns_on = CheckBox.new()
	_api_dns_on.text = _t("api_dns_enable")
	_api_dns_on.toggled.connect(func(_v): _on_api_save_dns())
	dns_box.add_child(_api_dns_on)
	_api_dns_url = LineEdit.new()
	_api_dns_url.placeholder_text = _t("api_dns_placeholder")
	_api_dns_url.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_dns_url.text_submitted.connect(func(_s): _on_api_save_dns())
	_api_dns_url.focus_exited.connect(_on_api_save_dns)
	dns_box.add_child(_api_dns_url)
	_api_hint(dns_box, _t("api_dns_hint"))
	_api_dns_error = _api_hint(dns_box, "")
	_api_dns_error.add_theme_color_override("font_color", _color("error"))

	# ---- Дополнительно: прокси ----
	var advanced_btn := Button.new()
	advanced_btn.text = _t("api_advanced")
	advanced_btn.toggle_mode = true
	advanced_btn.size_flags_horizontal = SIZE_EXPAND_FILL
	if T:
		T.style_button(advanced_btn, "neutral")
		advanced_btn.icon = T.first_icon(["Tools", "GuiTreeArrowDown", "Settings"])
	form.add_child(advanced_btn)
	var proxy_wrap := VBoxContainer.new()
	proxy_wrap.size_flags_horizontal = SIZE_EXPAND_FILL
	proxy_wrap.visible = false
	form.add_child(proxy_wrap)
	advanced_btn.toggled.connect(func(on): proxy_wrap.visible = on)
	var proxy_box := _api_section(proxy_wrap, "api_proxy")
	_api_proxy_on = CheckBox.new()
	_api_proxy_on.text = _t("api_proxy_enable")
	_api_proxy_on.toggled.connect(func(_v): _on_api_save_proxy())
	proxy_box.add_child(_api_proxy_on)
	var pr_row := HBoxContainer.new()
	pr_row.size_flags_horizontal = SIZE_EXPAND_FILL
	proxy_box.add_child(pr_row)
	var host_lbl := Label.new()
	host_lbl.text = _t("api_proxy_host")
	pr_row.add_child(host_lbl)
	_api_proxy_host = LineEdit.new()
	_api_proxy_host.placeholder_text = _t("api_proxy_host_placeholder")
	_api_proxy_host.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_proxy_host.text_submitted.connect(func(_s): _on_api_save_proxy())
	_api_proxy_host.focus_exited.connect(_on_api_save_proxy)
	pr_row.add_child(_api_proxy_host)
	_api_proxy_port = SpinBox.new()
	_api_proxy_port.min_value = 0
	_api_proxy_port.max_value = 65535
	_api_proxy_port.step = 1
	_api_proxy_port.value = 0
	_api_proxy_port.value_changed.connect(func(_v): _on_api_save_proxy())
	pr_row.add_child(_api_proxy_port)
	var auth_row := HBoxContainer.new()
	auth_row.size_flags_horizontal = SIZE_EXPAND_FILL
	proxy_box.add_child(auth_row)
	_api_proxy_user = LineEdit.new()
	_api_proxy_user.placeholder_text = _t("api_proxy_user")
	_api_proxy_user.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_proxy_user.focus_exited.connect(_on_api_save_proxy)
	auth_row.add_child(_api_proxy_user)
	_api_proxy_pass = LineEdit.new()
	_api_proxy_pass.secret = true
	_api_proxy_pass.placeholder_text = _t("api_proxy_pass")
	_api_proxy_pass.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_proxy_pass.focus_exited.connect(_on_api_save_proxy)
	auth_row.add_child(_api_proxy_pass)
	_api_hint(proxy_box, _t("api_proxy_hint"))
	# Ошибка разбора адреса прокси — видимой строкой прямо под полями, а не
	# только в статусе внизу: именно здесь пользователь ошибается, вставляя
	# адрес сервиса вместо прокси.
	_api_proxy_error = _api_hint(proxy_box, "")
	_api_proxy_error.add_theme_color_override("font_color", _color("error"))

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
	# Причина, по которой чат ещё нельзя начать, показывается СТРОКОЙ, а не
	# подсказкой на выключенной кнопке: подсказку не видно, и «ключ сохранён,
	# а начать нельзя» выглядит как поломка.
	_api_ready_note = _api_hint(_api_view, "")
	_api_ready_note.add_theme_color_override("font_color", _color("warning"))
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
		# remove_child ДО queue_free: освобождение отложено до конца кадра, и без
		# немедленного изъятия из дерева контейнер весь кадр держал бы и старых
		# детей, и только что добавленных новых — список рисовался бы дважды. На
		# перерисовке раз в переход это незаметно, но список провайдеров
		# перестраивается на каждую букву в поиске, и там это уже видно.
		c.remove_child(ch)
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
		var row := HBoxContainer.new()
		row.size_flags_horizontal = SIZE_EXPAND_FILL
		row.add_theme_constant_override("separation", 4)
		var btn := Button.new()
		var t := str(c.get("title", _t("untitled")))
		var chat_id := str(c.get("id", ""))
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
		btn.pressed.connect(_pick_chat.bind(chat_id))
		row.add_child(btn)
		var del_btn := Button.new()
		del_btn.tooltip_text = _t("del_text") % t
		del_btn.custom_minimum_size = Vector2(36, 36)
		del_btn.pressed.connect(_request_chat_delete.bind(chat_id, t))
		if T:
			T.style_icon_button(del_btn, ["Remove", "Close"], "X", "error")
		else:
			del_btn.text = "X"
		row.add_child(del_btn)
		_chats_list.add_child(row)


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


func _request_chat_delete(chat_id: String, chat_title: String) -> void:
	if chat_id == "":
		return
	_delete_chat_id = chat_id
	if _delete_dialog == null or not is_instance_valid(_delete_dialog):
		_delete_dialog = ConfirmationDialog.new()
		_delete_dialog.confirmed.connect(_confirm_chat_delete)
		add_child(_delete_dialog)
	_delete_dialog.title = _t("del_title")
	_delete_dialog.dialog_text = _t("del_text") % chat_title
	_delete_dialog.get_ok_button().text = _t("del_yes")
	_delete_dialog.get_cancel_button().text = _t("del_no")
	_delete_dialog.popup_centered(Vector2i(420, 150))


func _confirm_chat_delete() -> void:
	var chat_id := _delete_chat_id
	_delete_chat_id = ""
	if chat_id != "":
		delete_chat_requested.emit(chat_id)


func _pick_site(site_id: String) -> void:
	if site_id != "":
		new_chat_requested.emit(site_id)


# ---------------------------------------------------------------------------
# Работа по ключу API: заполнение формы и обработчики.
# ---------------------------------------------------------------------------

func _api_current_provider() -> String:
	return _api_selected_provider


func _api_provider_rec(pid: String) -> Dictionary:
	for p in _api_data.get("providers", []):
		if typeof(p) == TYPE_DICTIONARY and str(p.get("id", "")) == pid:
			return p
	return {}


func _api_why(rec: Dictionary) -> String:
	# Причина неготовности словами НА ЯЗЫКЕ ПАНЕЛИ. Сервер присылает и код
	# (not_ready_code), и готовую фразу (not_ready_reason), но фраза у него
	# только по-русски: она писалась под строку в настройках. Поэтому переводим
	# по коду, а текст сервера оставляем запасным вариантом — на случай кода,
	# которого эта версия панели ещё не знает (например, новый провайдер с
	# новой причиной после обновления сервера).
	var code := str(rec.get("not_ready_code", ""))
	match code:
		"":
			return ""
		"no_key":
			return _t("api_why_no_key")
		"no_model":
			return _t("api_why_no_model")
		"no_base_url":
			return _t("api_why_no_base_url")
		"unavailable":
			return _t("api_why_unavailable")
		"unknown_provider":
			return _t("api_why_unknown")
	return str(rec.get("not_ready_reason", ""))


func _api_ago(stamp: float) -> String:
	# «Когда проверяли» словами. Точная дата тут не нужна и мешает: важно
	# только, свежее это знание или ему неделя.
	if stamp <= 0.0:
		return ""
	var secs := int(Time.get_unix_time_from_system() - stamp)
	if secs < 90:
		return _t("api_ago_now")
	if secs < 3600:
		return _t("api_ago_minutes") % int(secs / 60.0)
	if secs < 86400:
		return _t("api_ago_hours") % int(secs / 3600.0)
	return _t("api_ago_days") % int(secs / 86400.0)


func set_api_settings(json: Dictionary) -> void:
	# Единственный источник состояния формы — ответ сервера. Панель ничего не
	# домысливает сама, поэтому после любого сохранения форма перерисовывается
	# целиком и не может разойтись с тем, что реально записано на диске.
	if typeof(json) != TYPE_DICTIONARY or _api_provider_btn == null:
		return
	if json.has("providers"):
		_api_data = json
	_api_filling = true
	_api_provider_ids.clear()
	for p in _api_data.get("providers", []):
		if typeof(p) == TYPE_DICTIONARY:
			_api_provider_ids.append(str(p.get("id", "")))
	# Выбор пользователя важнее предложения сервера: перерисовка формы после
	# сохранения не должна перебрасывать его на другого провайдера.
	if _api_selected_provider == "" or not _api_provider_ids.has(_api_selected_provider):
		var want := str(_api_data.get("defaults", {}).get("provider", ""))
		if _api_provider_ids.has(want):
			_api_selected_provider = want
		elif not _api_provider_ids.is_empty():
			_api_selected_provider = str(_api_provider_ids[0])
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
	var dns: Dictionary = _api_data.get("dns", {})
	if _api_dns_on:
		_api_dns_on.button_pressed = bool(dns.get("enabled", false))
	if _api_dns_url:
		_api_dns_url.text = str(dns.get("url", ""))
	if _api_proxy_error:
		# Сервер отклонил адрес прокси — показываем ЕГО объяснение, а не общий текст.
		_api_proxy_error.text = str(json.get("proxy_error", ""))
	if _api_dns_error:
		_api_dns_error.text = str(json.get("dns_error", ""))
	if _api_base_error:
		_api_base_error.text = str(json.get("base_url_error", ""))
	_api_filling = false
	# Диалог мог остаться открытым (сохранение ключа прямо из карточки) —
	# перерисовываем его тем же ответом, чтобы пометки не устарели.
	if _api_pick_dialog and is_instance_valid(_api_pick_dialog) and _api_pick_dialog.visible:
		_api_rebuild_pick_list()


func _api_fill_provider_fields() -> void:
	var pid := _api_current_provider()
	var rec := _api_provider_rec(pid)
	var lang_note := "note_ru" if _lang() != "en" else "note_en"
	if _api_provider_btn:
		var title := str(rec.get("name", pid))
		if title == "":
			title = _t("api_provider_change")
		elif not bool(rec.get("ready", false)):
			title += "  —  " + _t("api_not_ready")
		_api_provider_btn.text = title
	if _api_note:
		_api_note.text = str(rec.get(lang_note, ""))
	if _api_model_edit:
		_api_model_edit.text = str(rec.get("model", ""))
	if _api_model_opt:
		_api_model_opt.clear()
		# Загруженный с сервиса список важнее зашитого в реестр: он свежий и
		# полный. Реестр — запасной вариант для провайдеров с коротким
		# фиксированным перечнем моделей.
		var known_models = _api_fetched_models.get(pid, [])
		if typeof(known_models) != TYPE_ARRAY or (known_models as Array).is_empty():
			known_models = rec.get("models", [])
		if typeof(known_models) == TYPE_ARRAY:
			for model in known_models:
				_api_add_model_item(model)
		_api_model_opt.disabled = _api_model_opt.item_count == 0
		# Тот же сброс выбора, что и в set_api_models: без него клик по первой
		# модели списка не давал item_selected (add_item уже выбрал её сам),
		# и выбрать её было нельзя.
		if _api_model_opt.item_count > 0:
			_api_model_opt.selected = -1
			_api_model_opt.text = _t("api_models_pick") % _api_model_opt.item_count
	if _api_base_edit:
		# В поле — ТОЛЬКО заданный вручную адрес, а не действующий. Если
		# подставить сюда адрес из реестра, ближайшее сохранение формы запишет
		# его как переопределение, и обновление реестра в новой версии плагина
		# перестанет действовать: человек навсегда останется на старом адресе,
		# не понимая почему. Стандартный адрес показываем подсказкой в пустом поле.
		var default_url := str(rec.get("base_url_default", ""))
		var is_custom := bool(rec.get("base_url_custom", false))
		_api_base_edit.text = str(rec.get("base_url", "")) if is_custom else ""
		_api_base_edit.placeholder_text = (_t("api_base_url_default") % default_url) \
			if default_url != "" else "http://127.0.0.1:8080/v1"
		if _api_base_custom:
			_api_base_custom.text = _t("api_base_url_custom") if is_custom else ""
	if _api_base_row:
		_api_base_row.visible = bool(rec.get("base_url_editable", true))
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
		var ready := bool(rec.get("ready", false))
		var why := _api_why(rec)
		_api_start_btn.disabled = not ready
		_api_start_btn.tooltip_text = "" if ready else why
		if _api_ready_note:
			_api_ready_note.text = "" if ready else (_t("api_not_ready_note") % why)
	if _api_test_state:
		_api_test_state.text = ""


func _api_add_model_item(model) -> void:
	# Одна строка списка моделей. Подпись и идентификатор РАЗДЕЛЕНЫ: подпись
	# может содержать пометку «бесплатная», а в запрос уходит только сам
	# идентификатор. Если бы обработчик читал подпись кнопки, к имени модели
	# приклеилась бы пометка и провайдер ответил бы «модель не найдена».
	if _api_model_opt == null:
		return
	var mid := ""
	var free := false
	if typeof(model) == TYPE_DICTIONARY:
		mid = str((model as Dictionary).get("id", ""))
		free = bool((model as Dictionary).get("free", false))
	else:
		mid = str(model)
	if mid == "":
		return
	_api_model_opt.add_item((_t("api_model_free") % mid) if free else mid)
	_api_model_opt.set_item_metadata(_api_model_opt.item_count - 1, mid)


func _api_model_id_at(idx: int) -> String:
	# Идентификатор модели по номеру строки. Метаданные — основной путь, текст
	# кнопки — запасной: у элементов, добавленных старым кодом, метаданных нет.
	if _api_model_opt == null or idx < 0 or idx >= _api_model_opt.item_count:
		return ""
	var meta = _api_model_opt.get_item_metadata(idx)
	if typeof(meta) == TYPE_STRING and str(meta) != "":
		return str(meta)
	return _api_model_opt.get_item_text(idx)


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
	}
	# base_url отправляем как есть, включая ПУСТУЮ строку: пусто означает
	# «вернуться к адресу из реестра», и это единственный способ сбросить
	# ошибочно введённый адрес. Подставлять сюда действующий адрес нельзя —
	# тогда он записался бы переопределением, и обновление реестра в новой
	# версии плагина перестало бы действовать (см. _api_fill_provider_fields).
	if _api_base_row and _api_base_row.visible and _api_base_edit:
		data["base_url"] = _api_base_edit.text.strip_edges()
	api_settings_save_requested.emit(data)


func _on_api_save_proxy() -> void:
	if _api_filling:
		return
	var proxy := _api_proxy_payload(true)
	if bool(proxy.get("enabled", false)) and str(proxy.get("host", "")) == "":
		if _api_proxy_error:
			_api_proxy_error.text = _t("api_proxy_address_required")
		return
	if _api_proxy_error:
		_api_proxy_error.text = ""
	api_settings_save_requested.emit({"proxy": proxy})


func _on_api_save_dns() -> void:
	if _api_filling:
		return
	var enabled := _api_dns_on.button_pressed if _api_dns_on else false
	var url := _api_dns_url.text.strip_edges() if _api_dns_url else ""
	if enabled and url == "":
		if _api_dns_error:
			_api_dns_error.text = _t("api_dns_address_required")
		return
	if _api_dns_error:
		_api_dns_error.text = ""
	api_settings_save_requested.emit({
		"dns": {"enabled": enabled, "url": url},
	})


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


func set_api_models(provider: String, models: Array, models_info: Array = []) -> void:
	if _api_model_opt == null:
		return
	if provider != "" and provider != _api_current_provider():
		return  # ответ про другого провайдера — пользователь уже переключился
	# Записи с признаком бесплатности важнее простого списка строк: по ним видна
	# пометка «бесплатная» даже у модели, в имени которой нет ":free" (сервис
	# может отдавать нулевую цену без всякого суффикса). Список строк остаётся
	# запасным вариантом — на случай сервера старой версии.
	var source: Array = models_info if not models_info.is_empty() else models
	var pid := provider if provider != "" else _api_current_provider()
	# Запоминаем список за провайдером: сохранение настроек перерисовывает форму
	# из ответа сервера, где загруженных моделей нет, и без кэша список пропадал
	# сразу после выбора модели.
	if pid != "":
		_api_fetched_models[pid] = source.duplicate()
	_api_model_opt.clear()
	if source.is_empty():
		_api_model_opt.add_item(_t("api_models_none"))
		_api_model_opt.disabled = true
		return
	_api_model_opt.disabled = false
	for m in source:
		_api_add_model_item(m)
	# ПОЧЕМУ ЗДЕСЬ СБРОС ВЫБОРА. add_item автоматически выбирает ПЕРВЫЙ
	# добавленный элемент (selected становится 0), а item_selected приходит
	# только при СМЕНЕ выбора. Значит клик по первой модели списка не менял
	# ничего и сигнал не приходил вовсе: пользователь выбирал верхнюю модель
	# (у Opencode Zen это deepseek-v4-flash-free), а в поле оставалась прежняя —
	# работали все модели, кроме первой. Снимаем выбор, чтобы ЛЮБОЙ пункт,
	# включая первый, был именно сменой выбора и доходил до _on_api_model_picked.
	_api_model_opt.selected = -1
	# При selected = -1 кнопка показывает пустую строку — подсказываем, что
	# список получен и из него нужно выбрать.
	_api_model_opt.text = _t("api_models_pick") % _api_model_opt.item_count
	set_status(_t("api_models_loaded") % _api_model_opt.item_count, "success")


func _on_api_model_picked(idx: int) -> void:
	if _api_model_opt == null or _api_model_opt.disabled:
		return
	if idx < 0 or idx >= _api_model_opt.item_count:
		return
	if _api_model_edit:
		# Именно идентификатор из метаданных, а не подпись: в подписи может
		# стоять пометка «бесплатная», и она уехала бы в запрос вместе с именем.
		_api_model_edit.text = _api_model_id_at(idx)
	# Выпадающий список — это КНОПКА ВЫБОРА, а не показ текущего состояния
	# (выбранная модель видна в поле выше). Поэтому сразу возвращаем «нет
	# выбора»: иначе повторный клик по той же модели не менял бы selected и не
	# доходил бы до этого обработчика — ровно та же ловушка, что и с первым
	# пунктом списка.
	var count := _api_model_opt.item_count
	_api_model_opt.selected = -1
	_api_model_opt.text = _t("api_models_pick") % count
	_on_api_save_fields()


# ---------------------------------------------------------------------------
# Выбор провайдера отдельным окном.
#
# ПОЧЕМУ ОКНО, А НЕ СПИСОК В ДОКЕ. Панель живёт в правом доке шириной 250–400
# px. Карточка провайдера — это название, пометки о ключе, число бесплатных
# моделей и описание в две строки; в доке это либо не влезает, либо вытесняет
# саму форму настроек. Окно по центру редактора не ограничено шириной дока.
#
# ПОЧЕМУ ГРУППЫ, А НЕ СОРТИРОВКА ПО КОЛОНКАМ. Сравнивать значения в колонках
# можно, когда колонки видны рядом; в вертикальном списке одновременно видно
# 5–6 карточек, и сортировка ничего не даёт. Группы «готов / можно настроить /
# недоступен» отвечают на единственный вопрос, который тут есть: с чего можно
# начать прямо сейчас. Они же не пустуют — в отличие от группы «проверенные»,
# которая была бы пуста, потому что живьём не проверялся ни один провайдер.
# ---------------------------------------------------------------------------

func _on_api_pick_open() -> void:
	if _api_pick_dialog == null or not is_instance_valid(_api_pick_dialog):
		_api_build_pick_dialog()
	_api_pick_dialog.title = _t("api_pick_title")
	_api_pick_dialog.get_ok_button().text = _t("api_pick_close")
	_api_rebuild_pick_list()
	# Модальное окно: пока выбирают провайдера, трогать форму под ним нечего, а
	# два источника состояния разом (карточка и форма) разошлись бы.
	#
	# ИМЕННО clamped, а не popup_centered с фиксированным размером: 720x560 не
	# влезет в окно редактора на маленьком экране, и окно уедет за его границы
	# (Godot ругается «Window spawned at invalid position» и показывает диалог
	# частично). clamped берёт желаемый размер, но не больше доли родительского
	# окна, поэтому диалог остаётся целиком видимым при любом размере редактора.
	_api_pick_dialog.popup_centered_clamped(Vector2i(720, 560), 0.9)
	if _api_pick_search:
		_api_pick_search.grab_focus()


func _api_build_pick_dialog() -> void:
	var T = _T()
	_api_pick_dialog = AcceptDialog.new()
	_api_pick_dialog.exclusive = true
	# Единственную кнопку диалога НЕ скрываем, а переименовываем в «Закрыть».
	# Выбор делается кликом по карточке, но окно модальное: остаться в нём без
	# видимого выхода нельзя, а надеяться на Esc в модальном окне — значит
	# надеяться, что фокус в нужном месте (в поле поиска он не там).
	add_child(_api_pick_dialog)

	var root := VBoxContainer.new()
	root.size_flags_horizontal = SIZE_EXPAND_FILL
	root.size_flags_vertical = SIZE_EXPAND_FILL
	root.add_theme_constant_override("separation", 8)
	_api_pick_dialog.add_child(root)

	_api_pick_search = LineEdit.new()
	_api_pick_search.placeholder_text = _t("api_pick_search")
	_api_pick_search.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_pick_search.clear_button_enabled = true
	_api_pick_search.text_changed.connect(_on_api_pick_search)
	if T:
		T.style_input(_api_pick_search)
		_api_pick_search.right_icon = T.first_icon(["Search", "Zoom"])
	root.add_child(_api_pick_search)

	# Фильтры чипами, а не выпадающим списком: их три, они всегда видны, и
	# видно, какой включён.
	var chips := HBoxContainer.new()
	chips.size_flags_horizontal = SIZE_EXPAND_FILL
	root.add_child(chips)
	var group := ButtonGroup.new()
	_api_add_chip(chips, group, "all", "api_pick_filter_all")
	_api_add_chip(chips, group, "free", "api_pick_filter_free")
	_api_add_chip(chips, group, "ready", "api_pick_filter_ready")

	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = SIZE_EXPAND_FILL
	scroll.size_flags_vertical = SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	root.add_child(scroll)
	_api_pick_list = VBoxContainer.new()
	_api_pick_list.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_pick_list.add_theme_constant_override("separation", 10)
	scroll.add_child(_api_pick_list)

	# Пустой результат объясняется словами, а не пустым экраном: у фильтра
	# «с бесплатными» пусто — это нормальное состояние до первого обновления
	# списков моделей, и человек должен узнать, что нажать.
	_api_pick_empty = Label.new()
	_api_pick_empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_api_pick_empty.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_pick_empty.add_theme_color_override("font_color", _color("dim"))
	_api_pick_empty.visible = false
	root.add_child(_api_pick_empty)


func _api_add_chip(parent: Node, group: ButtonGroup, mode: String, key: String) -> void:
	var T = _T()
	var chip := Button.new()
	chip.text = _t(key)
	chip.toggle_mode = true
	chip.button_group = group
	chip.button_pressed = _api_pick_filter == mode
	chip.pressed.connect(_on_api_pick_filter.bind(mode))
	if T:
		T.style_button(chip, "neutral", false)
	parent.add_child(chip)


func _on_api_pick_search(_text: String) -> void:
	_api_rebuild_pick_list()


func _on_api_pick_filter(mode: String) -> void:
	_api_pick_filter = mode
	_api_rebuild_pick_list()


func _api_pick_matches(rec: Dictionary, query: String) -> bool:
	if query != "" and not str(rec.get("name", "")).to_lower().contains(query) \
			and not str(rec.get("id", "")).to_lower().contains(query):
		return false
	match _api_pick_filter:
		"ready":
			return bool(rec.get("configured", false)) or not bool(rec.get("needs_key", true))
		"free":
			# Только по ИЗМЕРЕННОМУ числу бесплатных моделей. Догадываться по
			# описанию провайдера нельзя: «бесплатный тариф» в тексте реестра —
			# это наше утверждение, которое устареет молча, а число пришло из
			# ответа самого сервиса.
			var stats: Dictionary = rec.get("stats", {})
			return int(stats.get("models_free", -1)) > 0
	return true


func _api_rebuild_pick_list() -> void:
	if _api_pick_list == null or not is_instance_valid(_api_pick_list):
		return
	_clear_container(_api_pick_list)
	var query := ""
	if _api_pick_search:
		query = _api_pick_search.text.strip_edges().to_lower()
	var ready_recs: Array = []
	var setup_recs: Array = []
	var blocked_recs: Array = []
	for p in _api_data.get("providers", []):
		if typeof(p) != TYPE_DICTIONARY:
			continue
		var rec: Dictionary = p
		if not _api_pick_matches(rec, query):
			continue
		if str(rec.get("unavailable", "")) != "":
			blocked_recs.append(rec)
		elif bool(rec.get("ready", false)):
			ready_recs.append(rec)
		else:
			setup_recs.append(rec)
	var shown := ready_recs.size() + setup_recs.size() + blocked_recs.size()
	_api_add_pick_group("ready", "api_pick_group_ready", ready_recs, false)
	_api_add_pick_group("setup", "api_pick_group_setup", setup_recs, false)
	# Недоступные свёрнуты по умолчанию: их нельзя выбрать, и держать их
	# раскрытыми значит каждый раз прокручивать список мимо них.
	_api_add_pick_group("blocked", "api_pick_group_blocked", blocked_recs, true)
	if _api_pick_empty:
		_api_pick_empty.visible = shown == 0
		if shown == 0:
			_api_pick_empty.text = _t("api_pick_no_free_data") \
				if _api_pick_filter == "free" and query == "" else _t("api_pick_nothing")


func _api_add_pick_group(key: String, title_key: String, recs: Array,
		collapsed_by_default: bool) -> void:
	if recs.is_empty():
		return
	var T = _T()
	var head := Button.new()
	head.text = _t(title_key) % recs.size()
	head.toggle_mode = true
	head.alignment = HORIZONTAL_ALIGNMENT_LEFT
	head.size_flags_horizontal = SIZE_EXPAND_FILL
	if not _api_pick_collapsed.has(key):
		_api_pick_collapsed[key] = collapsed_by_default
	var open := not bool(_api_pick_collapsed[key])
	head.button_pressed = open
	if T:
		T.style_button(head, "accent", false)
		# У Button нет icon_rotation, поэтому стрелка — это две разные иконки
		# темы (тот же приём, что в ToolCallCard).
		head.icon = T.first_icon(["GuiTreeArrowDown"] if open else ["GuiTreeArrowRight"])
	_api_pick_list.add_child(head)

	var box := VBoxContainer.new()
	box.size_flags_horizontal = SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 6)
	box.visible = open
	_api_pick_list.add_child(box)
	# Подключаем ПОСЛЕ установки button_pressed: иначе начальное значение само
	# выглядело бы как нажатие пользователя. И переключаем видимость, а не
	# перестраиваем список целиком — перестройка освободила бы кнопку, чей
	# сигнал прямо сейчас обрабатывается.
	head.toggled.connect(_on_api_pick_group_toggled.bind(key, head, box))
	for rec in recs:
		_api_add_pick_card(box, rec)


func _on_api_pick_group_toggled(pressed: bool, key: String, head: Button,
		box: VBoxContainer) -> void:
	_api_pick_collapsed[key] = not pressed
	if is_instance_valid(box):
		box.visible = pressed
	# У Button нет icon_rotation, поэтому стрелка — две разные иконки темы.
	var T = _T()
	if T and is_instance_valid(head):
		head.icon = T.first_icon(["GuiTreeArrowDown"] if pressed else ["GuiTreeArrowRight"])


func _api_add_pick_card(parent: Node, rec: Dictionary) -> void:
	var T = _T()
	var pid := str(rec.get("id", ""))
	var blocked := str(rec.get("unavailable", "")) != ""
	var card := PanelContainer.new()
	card.size_flags_horizontal = SIZE_EXPAND_FILL
	if T:
		card.add_theme_stylebox_override(
			"panel", T.panel_style("error" if blocked else "tool"))
	parent.add_child(card)
	var body := VBoxContainer.new()
	body.size_flags_horizontal = SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 4)
	card.add_child(body)

	# Верхняя строка: название кнопкой (это и есть выбор) + пометки справа.
	var head := HBoxContainer.new()
	head.size_flags_horizontal = SIZE_EXPAND_FILL
	body.add_child(head)
	var pick := Button.new()
	pick.text = str(rec.get("name", pid))
	pick.alignment = HORIZONTAL_ALIGNMENT_LEFT
	pick.clip_text = true
	pick.size_flags_horizontal = SIZE_EXPAND_FILL
	# Недоступного провайдера нельзя выбрать: он всё равно отклонит запрос, а
	# «выбрал и не работает» выглядит поломкой плагина, а не ограничением сервиса.
	pick.disabled = blocked
	if pid == _api_current_provider():
		pick.text += "  ·  " + _t("api_pick_current")
	if not blocked:
		pick.pressed.connect(_on_api_pick_choose.bind(pid))
	if T:
		var tone := "dim" if blocked else ("success" if bool(rec.get("ready", false)) else "neutral")
		T.style_button(pick, tone, false)
		pick.icon = T.first_icon(["StatusSuccess"] if bool(rec.get("ready", false)) else ["Script"])
	head.add_child(pick)
	for badge in _api_pick_badges(rec):
		var lbl := Label.new()
		lbl.text = str(badge.get("text", ""))
		lbl.add_theme_color_override("font_color", _color(str(badge.get("tone", "dim"))))
		head.add_child(lbl)

	var lang_note := "note_ru" if _lang() != "en" else "note_en"
	var note := str(rec.get(lang_note, ""))
	if blocked:
		# У недоступного провайдера важнее причина, чем описание возможностей:
		# описание обещало бы то, чем нельзя воспользоваться.
		note = str(rec.get("unavailable", ""))
	if note != "":
		var note_lbl := _api_hint(body, note)
		if blocked:
			note_lbl.add_theme_color_override("font_color", _color("warning"))
	var stats_line := _api_pick_stats_line(rec)
	if stats_line != "":
		_api_hint(body, stats_line)


func _api_pick_badges(rec: Dictionary) -> Array:
	# Пометки — только то, что ИЗВЕСТНО, а не то, что обещает описание. Слова
	# «бесплатный» среди них нет намеренно: бесплатность бывает у модели, а не
	# у провайдера, и она видна числом в строке статистики.
	var out: Array = []
	var src := str(rec.get("key_source", ""))
	if src == "env":
		out.append({"text": _t("api_badge_key_env"), "tone": "success"})
	elif bool(rec.get("configured", false)):
		out.append({"text": _t("api_badge_key"), "tone": "success"})
	elif not bool(rec.get("needs_key", true)):
		out.append({"text": _t("api_badge_no_key_needed"), "tone": "dim"})
	else:
		out.append({"text": _t("api_badge_no_key"), "tone": "warning"})
	if bool(rec.get("models_public", false)):
		out.append({"text": _t("api_badge_models_public"), "tone": "accent"})
	if bool(rec.get("base_url_custom", false)):
		out.append({"text": _t("api_badge_custom_url"), "tone": "warning"})
	# «Живьём не проверялся» показываем ЧЕСТНО у всех, у кого этого не было.
	# Обратной пометки «проверен» нет: её нельзя поставить по предположению,
	# а живого обмена настоящим ключом пока не было ни с одним провайдером.
	if not bool(rec.get("verified", false)):
		out.append({"text": _t("api_badge_unverified"), "tone": "dim"})
	return out


func _api_pick_stats_line(rec: Dictionary) -> String:
	# Числа сопровождаются возрастом измерения. «57 бесплатных» без даты — это
	# обещание за сервис, который мог поменять тарифы неделю назад; «57
	# бесплатных, проверено 3 дня назад» — уже наблюдение.
	var stats: Dictionary = rec.get("stats", {})
	var parts: Array = []
	var total := int(stats.get("models_total", -1))
	var free := int(stats.get("models_free", -1))
	if total >= 0:
		parts.append(_t("api_stats_models") % [total, free if free >= 0 else 0])
		var when := _api_ago(float(stats.get("models_at", 0.0)))
		if when != "":
			parts.append(_t("api_stats_checked") % when)
	else:
		parts.append(_t("api_stats_models_none"))
	if stats.has("test_ok"):
		var t_when := _api_ago(float(stats.get("test_at", 0.0)))
		if t_when == "":
			t_when = _t("api_ago_now")
		# Подстановка на той же строке, что и ключ: иначе строку с %s легко
		# однажды вывести как есть, и пользователь увидит «(%s)» вместо даты.
		if bool(stats["test_ok"]):
			parts.append(_t("api_stats_test_ok") % t_when)
		else:
			parts.append(_t("api_stats_test_fail") % t_when)
	return " ".join(parts)


func _on_api_pick_choose(pid: String) -> void:
	if pid == "":
		return
	_api_selected_provider = pid
	_api_filling = true
	_api_fill_provider_fields()
	_api_filling = false
	if _api_pick_dialog and is_instance_valid(_api_pick_dialog):
		_api_pick_dialog.hide()


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
