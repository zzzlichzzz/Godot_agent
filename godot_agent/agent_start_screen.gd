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
# Обход провайдеров за списками моделей. Отдельно от api_models_refresh_requested:
# там пользователь просит список У ОДНОГО провайдера и ждёт его в выпадающем
# списке, а здесь обновляются ЧИСЛА моделей у всех, кого можно спросить молча,
# и ни один список на экран не попадает. Без этого числа были только у
# провайдеров, которых пользователь открывал руками, а фильтр «с бесплатными»
# отбирал ровно их — то есть выглядел как утверждение, что у остальных
# бесплатных моделей нет.
signal api_models_scan_requested(force: bool)
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
# Коды языков в том порядке, в каком они стоят в переключателе. Держим отдельно
# от подписей: подпись показывается человеку, а на сервер и в файл уходит код.
var _lang_codes: Array = []
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
# Выбранная модель. ОБЫЧНАЯ СТРОКА, а не поле ввода: выбирают её в окне
# провайдера, из списка, пришедшего от самого провайдера. Поле ввода здесь было
# соблазном набрать имя руками — и провайдер отвергал такую модель уже в чате,
# то есть после того, как человек решил, что всё настроено.
var _api_model: String = ""
var _api_model_state: Label = null
var _api_base_row: HBoxContainer = null
var _api_base_edit: LineEdit = null
var _api_base_custom: Label = null
var _api_base_error: Label = null
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
#
# ОКНО РАЗДЕЛЕНО НАДВОЕ. Слева — только имена, одна строка на провайдера;
# справа — всё про одного выбранного. Раньше каждая запись была карточкой из
# пяти блоков (кнопка-имя, ряд пометок, описание с переносом, строка
# статистики, чипы моделей) — замерено около 160 px на провайдера, то есть в
# окне 720x560 одновременно видно два с половиной. На ста шестидесяти пяти
# записях каталога это шестьдесят экранов прокрутки. Строка в одну высоту
# кнопки даёт четырнадцать провайдеров на экран, а высота списка перестаёт
# зависеть от того, сколько про провайдера известно.
var _api_pick_dialog: AcceptDialog = null
var _api_pick_list: VBoxContainer = null
var _api_pick_search: LineEdit = null
var _api_pick_empty: Label = null
# Правая половина окна и её части. Собирается заново при смене выбранной
# строки, а не прячется-показывается: полей у провайдера разное число (у
# недоступного нет моделей, у каталожного нет статистики), и держать все
# варианты собранными значит держать половину окна из скрытых узлов.
var _api_detail: VBoxContainer = null
var _api_detail_models: VBoxContainer = null
var _api_detail_cap: Label = null
var _api_detail_filter: LineEdit = null
var _api_detail_free: Button = null
var _api_detail_key: LineEdit = null
# Чей провайдер показан СПРАВА. Это НЕ выбранный провайдер: строку можно
# листать, читая описания, и ничего при этом не менять. Выбор происходит только
# кнопкой «Выбрать этого провайдера» или нажатием на модель.
var _api_pick_shown: String = ""
# Для какого провайдера правая половина уже собрана. Список перестраивается на
# каждую букву в поиске, а собирать при этом заново шестьдесят строк моделей
# незачем — они не изменились.
var _api_detail_built_for: String = ""
# Строки списка: provider_id -> кнопка. Нужны, чтобы после перестройки списка
# подсветить ту же строку, что была выбрана до неё.
var _api_pick_rows: Dictionary = {}
# Общая группа переключателей строк: она и обеспечивает «выбрана ровно одна».
# Пересоздаётся вместе со списком — прежние кнопки уже освобождены.
var _api_row_group: ButtonGroup = null
# Запрос, по которому список собран в последний раз. По его смене поиск
# переносится в фильтр моделей справа: человек искал «kimi», нашёл провайдера, и
# заставлять его набирать «kimi» второй раз в правой половине незачем.
var _api_pick_query: String = ""
# Строка состояния списка: «обновляю списки моделей» и «скрыто провайдеров без
# данных». Отдельно от _api_pick_empty: та объясняет ПУСТОЙ список, а эта нужна
# как раз когда список НЕ пуст — иначе короткий список после фильтра читается
# как полный ответ, и пользователь делает вывод о провайдерах, которых в нём
# нет вовсе.
var _api_pick_note: Label = null
# Просили ли сервер включить полный список провайдеров из каталога. Полный
# список включён всегда (см. _api_ensure_catalog_on), а флаг нужен ровно для
# того, чтобы просьба ушла один раз: ответ придёт тем же набором настроек и
# снова попадёт в ту же функцию.
var _api_catalog_asked: bool = false
# Идёт ли обход провайдеров за списками моделей. Панель обхода не ведёт: она
# только просит сервер, а он сам решает, кого и когда спрашивать.
var _api_scan_running: bool = false
# Когда обход просили в последний раз. Нужно, чтобы возвращение на экран после
# каждой долгой операции не превращалось в поток запросов к серверу.
var _api_scan_asked_at: float = 0.0
# Чем кончился последний обход, если он не удался целиком. Держим отдельно от
# статусной строки экрана: обход автоматический, и об его неудаче рассказывает
# строка под списком провайдеров, а не красное сообщение на весь экран.
var _api_scan_error: String = ""
# Сколько провайдеров скрыл фильтр «с бесплатными» из-за отсутствия данных.
var _api_pick_hidden_unknown: int = 0
# Фильтр: "all" | "free" | "ready". Не сортировка — на десятке провайдеров
# сортировать нечего, а вот отсеивать платных и ненастроенных полезно.
var _api_pick_filter: String = "all"
# Свёрнутые группы запоминаются между открытиями диалога: иначе «Пока
# недоступны» разворачивалась бы заново при каждом поиске.
var _api_pick_collapsed: Dictionary = {}
# Записи свёрнутых групп, ещё не превращённые в карточки: {ключ: {recs, query,
# box}}. Свёрнутая группа не собирается вовсе — на ста шестидесяти трёх записях
# каталога это 320 мс на каждую букву в поиске (замерено 1.9 мс на карточку).
var _api_pick_pending: Dictionary = {}
# Список моделей, полученный кнопкой «Обновить список», в разрезе провайдера:
# provider_id -> [идентификаторы]. Держим его отдельно от _api_data, потому что
# ответ сервера с настройками содержит ТОЛЬКО зашитый в реестр список (у
# большинства провайдеров он пуст намеренно — идентификаторы моделей меняются
# слишком часто). Без этого кэша выбор модели затирал бы сам себя: сохранение
# возвращает настройки, форма перерисовывается из реестра, и 62 только что
# загруженные модели исчезали из выпадающего списка.
var _api_fetched_models: Dictionary = {}
# Списки моделей ВСЕХ провайдеров, какие известны серверу: provider_id -> [{id,
# free}]. Нужно ровно для одного: искать модель по названию, не зная заранее, у
# кого она есть. Человек помнит «мне нужен kimi» или «deepseek», а не кто из
# провайдеров его отдаёт, — и до этого списка узнать это можно было только
# открыв каждого провайдера по очереди и нажав «Обновить список».
#
# Индекс приходит С СЕРВЕРА (поле models_index), а не собирается здесь из
# ответов на «Обновить»: тот ответ бывает отфильтрован флажком «только
# бесплатные», и поиск по нему был бы слеп к платным моделям.
var _api_model_index: Dictionary = {}
# Состояние каталога models.dev (поле catalog в ответе сервера): {url, at,
# error, try_at, providers, models}. Каталог — ВТОРИЧНЫЙ источник: он даёт цены,
# окно контекста и признак поддержки инструментов там, где живой /models их не
# присылает (у Opencode Zen там вообще только id). Здесь он нужен ровно для
# того, чтобы КАЖДОЕ его число на экране было подписано «по каталогу» и рядом
# стоял возраст этого знания: замерено, что каталог знает у Opencode Zen 91
# модель, а живой список отдаёт 62 — оба числа верные, но про разное.
var _api_catalog: Dictionary = {}
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
	if l and idx >= 0 and idx < _lang_codes.size():
		l.set_lang(str(_lang_codes[idx]))
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
	_api_pick_note = null
	_api_detail = null
	_api_detail_models = null
	_api_detail_cap = null
	_api_detail_filter = null
	_api_detail_free = null
	_api_detail_key = null
	_api_detail_built_for = ""
	# Сами строки списка освобождены вместе с диалогом, но словарь продолжал бы
	# держать ссылки на освобождённые кнопки, и подсветка выбранной строки после
	# смены языка обращалась бы к мёртвым объектам.
	_api_pick_rows.clear()
	_api_row_group = null
	_api_pick_query = ""
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
	# ПОЧЕМУ FLOW И ПЕРЕНОС ТЕКСТА. Эта строка видна поверх ВСЕХ разделов, поэтому
	# её наименьшая ширина становится наименьшей шириной всей панели. Кнопка с
	# подписью «Открыть папку с exe сервера» требовала 243 px, и в доке уже 220 px
	# за его край уезжало всё содержимое любого раздела, а не эта кнопка (измерено
	# обходом дерева при разных ширинах). С переносом подписи и EXPAND_FILL кнопка
	# занимает то место, которое есть, а подсказка уходит на свою строку.
	var server_row := HFlowContainer.new()
	server_row.alignment = FlowContainer.ALIGNMENT_CENTER
	root.add_child(server_row)
	_server_btn = Button.new()
	_server_btn.text = _t("srv_open_folder_btn")
	_server_btn.tooltip_text = _t("srv_open_folder_tip") + " " + _t("srv_manual_hint")
	# Перенос подписи безопасен только вместе с EXPAND_FILL: без него кнопка
	# получила бы наименьшую ширину (28 px) и превратилась бы в столбик из букв.
	_server_btn.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_server_btn.size_flags_horizontal = SIZE_EXPAND_FILL
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
	# Языки берутся ИЗ СЛОВАРЕЙ локализации, а не перечисляются здесь: добавленный
	# в agent_locale.gd язык должен появиться в переключателе сам, иначе он бы
	# работал (редактор на нём подхватил бы его) и при этом не выбирался руками.
	_lang_codes.clear()
	var L = _locale()
	if L:
		_lang_codes = L.languages()
	if _lang_codes.is_empty():
		_lang_codes = ["ru", "en"]
	for i in _lang_codes.size():
		var code := str(_lang_codes[i])
		lang_btn.add_item(L.lang_name(code) if L else code, i)
	lang_btn.select(maxi(0, _lang_codes.find(_lang())))
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

	# ПОРЯДОК КНОПОК: сохранённый чат — первым. Возвращаются к работе чаще, чем
	# начинают с нуля, а действие, которое делают чаще, не должно стоять вторым.
	var b_load := Button.new()
	b_load.text = _t("btn_load")
	b_load.custom_minimum_size = Vector2(0, MAIN_BUTTON_HEIGHT)
	b_load.size_flags_horizontal = SIZE_EXPAND_FILL
	b_load.pressed.connect(func(): chats_tab_requested.emit())
	if T:
		T.style_button(b_load, "neutral", false)
		b_load.icon = T.first_icon(["Load", "Folder"])
	actions.add_child(b_load)

	var b_new := Button.new()
	b_new.text = _t("btn_new")
	b_new.tooltip_text = _t("btn_new_tip")
	b_new.custom_minimum_size = Vector2(0, MAIN_BUTTON_HEIGHT)
	b_new.size_flags_horizontal = SIZE_EXPAND_FILL
	b_new.pressed.connect(func(): sites_tab_requested.emit())
	# Главное действие — акцентная и не плоская.
	if T:
		T.style_button(b_new, "accent", false)
		# Иконка «наружу», а не «плюс»: кнопка больше не про создание чата, а про
		# работу в чужом окне браузера. Список запасных именно такой длины
		# потому, что имена иконок редактора между версиями Godot меняются, и
		# first_icon молча берёт первое существующее.
		b_new.icon = T.first_icon(["ExternalLink", "InstanceOptions", "Add", "Script"])
	actions.add_child(b_new)

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
	# CloudTips — ТОЛЬКО русскому языку: сервис не принимает зарубежные карты, и
	# кнопка на него в любом другом интерфейсе ведёт в тупик. Условие именно
	# «язык русский», а не «язык не английский»: языков в плагине может стать
	# больше двух, и немецкому эта кнопка так же бесполезна, как английскому.
	if _lang() == "ru":
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
	# Flow и перенос подписи — по той же причине, что у копии наверху: пока экран
	# ожидания виден, наименьшая ширина этой кнопки становится наименьшей шириной
	# всей панели, и в узком доке за его край уезжало бы всё содержимое.
	var loading_srv_row := HFlowContainer.new()
	loading_srv_row.alignment = FlowContainer.ALIGNMENT_CENTER
	_loading_view.add_child(loading_srv_row)
	_loading_server_btn = Button.new()
	_loading_server_btn.text = _t("srv_open_folder_btn")
	_loading_server_btn.tooltip_text = _t("srv_open_folder_tip") + " " + _t("srv_manual_hint")
	_loading_server_btn.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_loading_server_btn.size_flags_horizontal = SIZE_EXPAND_FILL
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
	# ПЕРЕНОС ОБЯЗАТЕЛЕН. Без него наименьшая ширина подписи равна её полной
	# длине, а наименьшая ширина формы — наибольшей из них: «DNS over HTTPS
	# (если адрес провайдера не разрешается)» требовала 463 px и растягивала
	# форму целиком, из-за чего в доке 250 px за его край уезжало ВСЁ содержимое,
	# а не одна эта строка (измерено). С переносом та же подпись требует 9 px.
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
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

	# ---- Провайдер и модель ----
	# Кнопка, а не выпадающий список: у провайдера кроме названия есть состояние
	# ключа, число бесплатных моделей и описание, а в строку OptionButton это не
	# помещается — там был виден только «Groq — не настроен». Полный список с
	# поиском и фильтрами открывается отдельным окном.
	#
	# КЛЮЧ И МОДЕЛЬ ЖИВУТ В ТОМ ЖЕ ОКНЕ, а не здесь. Раньше форма спрашивала три
	# вещи по очереди: провайдера — в окне, ключ — полем ниже, модель — полем и
	# выпадающим списком под ним. Порядок при этом был обязателен и ниоткуда не
	# следовал: список моделей у большинства провайдеров пуст, пока не сохранён
	# ключ, поэтому «выбрать модель» до «сохранить ключ» не работало, а понять
	# это можно было только по пустому списку. Теперь всё три шага стоят рядом с
	# провайдером, которого они касаются, и видно, чего не хватает.
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
	# Выбранная модель — ПОДПИСЬЮ, а не полем ввода. Менять её здесь больше
	# нельзя, и это правильно: имя, набранное руками с опечаткой, провайдер
	# отвергает уже в чате, а список в окне выбора приходит от него самого.
	_api_model_state = _api_hint(prov_box, "")
	_api_note = _api_hint(prov_box, "")

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

	# ---- DNS over HTTPS ----
	var dns_box := _api_section(form, "api_dns")
	_api_dns_on = CheckBox.new()
	_api_dns_on.text = _t("api_dns_enable")
	# Флажок с длинной подписью тоже держал форму широкой: у CheckBox наименьшая
	# ширина равна ширине текста (378 px), а перенос сводит её к 28. Включать
	# перенос можно ТОЛЬКО у флажков, которые получают всю ширину от родителя
	# (здесь родитель — вертикальный контейнер). У флажка внутри строки с
	# кнопками перенос дал бы обратное: он сжался бы до наименьшей ширины и
	# превратился в нечитаемый столбик из букв.
	_api_dns_on.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
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
	# Тот же перенос, что у флажка DoH: родитель вертикальный, ширину даёт он.
	_api_proxy_on.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_api_proxy_on.toggled.connect(func(_v): _on_api_save_proxy())
	proxy_box.add_child(_api_proxy_on)
	# Подпись «Хост», поле и порт: в узком доке порт уезжал за границу.
	var pr_row := HFlowContainer.new()
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
	# Логин и пароль прокси. Наименьшая ширина у полей маленькая, поэтому в доке
	# 250 px они ещё стоят рядом; перенос сработает, только если места правда не
	# останется. Flow здесь ради этого запаса, а не ради переноса всегда.
	var auth_row := HFlowContainer.new()
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


func _make_header(text: String) -> HFlowContainer:
	var T = _T()
	# Flow вместо HBox: «Назад» плюс заголовок раздела («Работа по ключу API»,
	# в английской локали ещё длиннее) в узком доке не влезают в одну строку, и
	# заголовок обрезался краем дока. Теперь он переходит на вторую строку.
	var head := HFlowContainer.new()
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
	# Заголовок переносится по словам: иначе он остаётся одной длинной строкой и
	# обрезается, даже переехав на свою строку.
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
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
	# Индекс моделей приходит вместе с обходом провайдеров и с обновлением
	# списка у одного из них. Обновляем ТОЛЬКО когда он есть: обычный ответ с
	# настройками его не несёт, и пустой словарь оттуда стёр бы поиск по моделям.
	if typeof(json.get("models_index")) == TYPE_DICTIONARY:
		_api_model_index = json["models_index"]
	# Состояние каталога models.dev приходит в КАЖДОМ ответе с настройками — он
	# один на всех провайдеров, и держать его в записи каждого было бы
	# дублированием. Проверка типа обязательна: со старым сервером поля нет
	# вовсе, и панель должна просто не показывать строку о каталоге, а не падать.
	if typeof(json.get("catalog")) == TYPE_DICTIONARY:
		_api_catalog = json["catalog"]
	_api_ensure_catalog_on()
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
	# Диалог мог остаться открытым (сохранение ключа прямо из формы) —
	# перерисовываем его тем же ответом, чтобы пометки не устарели. Правую
	# половину заставляем собраться заново: провайдер справа тот же, и без
	# сброса она осталась бы с прежними пометками и прежней статистикой, то есть
	# показывала бы состояние до сохранения.
	if _api_pick_dialog and is_instance_valid(_api_pick_dialog) and _api_pick_dialog.visible:
		_api_detail_built_for = ""
		_api_rebuild_pick_list()


func _api_fill_provider_fields() -> void:
	var pid := _api_current_provider()
	var rec := _api_provider_rec(pid)
	# Описание провайдера сервер присылает на двух языках, поэтому «русский или
	# английский», а не «не английский»: языков в плагине может быть больше, и
	# немецкому интерфейсу русское описание не поможет.
	var lang_note := "note_ru" if _lang() == "ru" else "note_en"
	if _api_provider_btn:
		var title := str(rec.get("name", pid))
		if title == "":
			title = _t("api_provider_change")
		elif not bool(rec.get("ready", false)):
			title += "  —  " + _t("api_not_ready")
		_api_provider_btn.text = title
	if _api_note:
		_api_note.text = str(rec.get(lang_note, ""))
	_api_model = str(rec.get("model", ""))
	if _api_model_state:
		# «Модель не выбрана» — не пустая строка, а объяснение с указанием, где
		# её выбрать: пустое место под кнопкой провайдера читается как «всё
		# готово», а чат при этом не запустится.
		_api_model_state.text = (_t("api_model_current") % _api_model) \
			if _api_model != "" else _t("api_model_unset")
		_api_model_state.add_theme_color_override("font_color",
			_color("dim") if _api_model != "" else _color("warning"))
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
	if _api_base_error:
		# Ошибка адреса относится к ТОМУ провайдеру, при сохранении которого она
		# пришла. При переключении на другого её надо снять: красная строка про
		# отклонённый адрес под полем с исправным адресом заставляет искать
		# несуществующую поломку. Свежую ошибку поставит set_api_settings из
		# ответа сервера.
		_api_base_error.text = ""
	if _api_base_row:
		_api_base_row.visible = bool(rec.get("base_url_editable", true))
	if _api_start_btn:
		var ready := bool(rec.get("ready", false))
		var why := _api_why(rec)
		_api_start_btn.disabled = not ready
		_api_start_btn.tooltip_text = "" if ready else why
		if _api_ready_note:
			_api_ready_note.text = "" if ready else (_t("api_not_ready_note") % why)
	if _api_test_state:
		_api_test_state.text = ""


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
		"model": _api_model,
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


func _on_api_detail_key_save() -> void:
	# Ключ сохраняется ДЛЯ ПОКАЗАННОГО провайдера, а не для текущего: поле стоит
	# в его карточке, и сохранять чужой ключ по кнопке под чужим названием было бы
	# прямым обманом.
	#
	# make_default НЕ ставим. Сохранённый ключ — это «у меня есть доступ», а не
	# «работаем через него»: человек может завести ключи трём сервисам и выбрать
	# один. Переключение — отдельная кнопка «Выбрать этого провайдера» в той же
	# карточке, то есть в одном движении глаз отсюда.
	var pid := _api_detail_built_for
	if pid == "" or _api_detail_key == null or not is_instance_valid(_api_detail_key):
		return
	var key := _api_detail_key.text.strip_edges()
	if key == "":
		set_status(_t("api_key_empty"), "error")
		return
	api_settings_save_requested.emit({"provider": pid, "key": key})


func _on_api_detail_key_delete() -> void:
	var pid := _api_detail_built_for
	if pid == "":
		return
	api_settings_save_requested.emit({"provider": pid, "key": ""})


func _on_api_detail_models_refresh() -> void:
	# Спросить список моделей у ОДНОГО провайдера прямо сейчас. Нужно ровно после
	# сохранения ключа: обход по возрасту данных случится когда-нибудь потом, а
	# список хочется увидеть сразу — иначе кажется, что ключ не подошёл.
	#
	# free_only = false ВСЕГДА. Ответ кладётся в кэш и становится источником для
	# списка справа; отфильтрованный ответ означал бы, что переключатель «только
	# бесплатные» больше нельзя выключить — платных моделей в кэше просто не
	# останется.
	var pid := _api_detail_built_for
	if pid == "":
		return
	set_status(_t("api_models_loading"), "status")
	api_models_refresh_requested.emit(pid, false)


func set_api_models(provider: String, models: Array, models_info: Array = []) -> void:
	# Записи с признаком бесплатности важнее простого списка строк: по ним видна
	# пометка «бесплатная» даже у модели, в имени которой нет ":free" (сервис
	# может отдавать нулевую цену без всякого суффикса). Список строк остаётся
	# запасным вариантом — на случай сервера старой версии.
	var source: Array = models_info if not models_info.is_empty() else models
	var pid := provider if provider != "" else _api_current_provider()
	if pid == "":
		return
	# Запоминаем список за провайдером: сохранение настроек перерисовывает форму
	# из ответа сервера, где загруженных моделей нет, и без кэша список пропадал
	# сразу после выбора модели.
	_api_fetched_models[pid] = source.duplicate()
	if source.is_empty():
		set_status(_t("api_models_none"), "error")
	else:
		set_status(_t("api_models_loaded") % source.size(), "success")
	# Ответ показываем ТОЛЬКО если открыта карточка того же провайдера. Проверка
	# обязательна: пока запрос шёл, человек мог перейти на другую строку, и
	# подставить ответ в чужую карточку значит показать чужие модели под чужим
	# названием.
	if pid == _api_detail_built_for:
		_api_detail_rebuild_models()


# ---------------------------------------------------------------------------
# Выбор провайдера отдельным окном, разделённым надвое.
#
# ПОЧЕМУ ОКНО, А НЕ СПИСОК В ДОКЕ. Панель живёт в правом доке шириной 250–400
# px. Про провайдера нужно показать название, пометки о ключе, число бесплатных
# моделей, описание и его модели; в доке это либо не влезает, либо вытесняет
# саму форму настроек. Окно по центру редактора не ограничено шириной дока.
#
# ПОЧЕМУ НАДВОЕ, А НЕ СПИСКОМ КАРТОЧЕК. Карточка со всем перечисленным занимала
# около 160 px, то есть в окне 720x560 их видно две с половиной, а с включённым
# каталогом записей 165 — шестьдесят экранов прокрутки. При этом сведения на
# карточке нужны про ОДНОГО провайдера, того, которого рассматривают, а
# остальные сто шестьдесят четыре карточки повторяют их впустую. Слева поэтому
# только имена (строка в высоту кнопки, четырнадцать на экран), справа — всё
# про выбранного. Высота списка перестаёт зависеть от того, сколько про
# провайдера известно.
#
# ПОЧЕМУ ГРУППЫ, А НЕ СОРТИРОВКА ПО КОЛОНКАМ. Сравнивать значения в колонках
# можно, когда колонки видны рядом; в списке из одних имён колонок нет вовсе.
# Группы «готов / можно настроить / недоступен» отвечают на единственный
# вопрос, который тут есть: с чего можно начать прямо сейчас. Они же не
# пустуют — в отличие от группы «проверенные», которая была бы пуста, потому
# что живьём не проверялся ни один провайдер.
# ---------------------------------------------------------------------------

func _on_api_pick_open() -> void:
	if _api_pick_dialog == null or not is_instance_valid(_api_pick_dialog):
		_api_build_pick_dialog()
	_api_pick_dialog.title = _t("api_pick_title")
	_api_pick_dialog.get_ok_button().text = _t("api_pick_close")
	# Окно открывается на ТЕКУЩЕМ провайдере: справа сразу видно, с чем человек
	# работает прямо сейчас, а не пустая половина с приглашением что-нибудь
	# выбрать. Выбор при этом не меняется — правая половина только показывает.
	_api_pick_shown = _api_current_provider()
	_api_detail_built_for = ""
	# Числа моделей обновляются САМИ при открытии списка, а не только по кнопке
	# «Обновить список» внутри провайдера. Иначе они есть лишь у провайдеров,
	# которых пользователь успел открыть руками, а фильтр «с бесплатными»
	# отбирает как раз по этим числам — и показывает не тех, у кого есть
	# бесплатные модели, а тех, кого уже спрашивали. Догадаться об этом снаружи
	# нельзя: список ведь показан целиком и выглядит как полный ответ.
	# Лишнего трафика тут нет: кого спрашивать и не пора ли, решает сервер по
	# возрасту данных (providers.models_stale).
	_api_request_scan()
	_api_rebuild_pick_list()
	# Модальное окно: пока выбирают провайдера, трогать форму под ним нечего, а
	# два источника состояния разом (карточка и форма) разошлись бы.
	#
	# ИМЕННО clamped, а не popup_centered с фиксированным размером: 720x560 не
	# влезет в окно редактора на маленьком экране, и окно уедет за его границы
	# (Godot ругается «Window spawned at invalid position» и показывает диалог
	# частично). clamped берёт желаемый размер, но не больше доли родительского
	# окна, поэтому диалог остаётся целиком видимым при любом размере редактора.
	_api_pick_dialog.popup_centered_clamped(Vector2i(940, 640), 0.9)
	if _api_pick_search:
		_api_pick_search.grab_focus()


func _api_request_scan() -> void:
	var now := Time.get_unix_time_from_system()
	# Два обхода разом не нужны: сервер второй всё равно отклонит, а строка
	# «обновляю списки» сбросилась бы по первому же ответу и соврала бы, что всё
	# готово, пока второй ещё идёт.
	#
	# ОГРАНИЧЕНИЕ ПО ВРЕМЕНИ обязательно. Ответ может не прийти вовсе — например,
	# запрос не удалось даже отправить (сервер закрылся между кадрами), и тогда
	# set_api_scan_result никто не вызовет. Без срока флаг остался бы выставленным
	# до перезапуска редактора, и списки моделей в этой сессии не обновились бы
	# больше никогда: снаружи это «плагин один раз сходил и перестал».
	if _api_scan_running and now - _api_scan_asked_at < 90.0:
		return
	# Свой короткий предохранитель поверх серверного. КОГО и НЕ ПОРА ЛИ
	# спрашивать, решает сервер по возрасту данных (providers.models_stale: 12
	# часов), поэтому кнопки «обновить» здесь нет — обновление и так происходит
	# само. Эта проверка нужна для другого: show_api() вызывается не только при
	# открытии раздела, экран ожидания возвращается в него после каждой долгой
	# операции, и без неё каждое такое возвращение слало бы серверу запрос,
	# который тот всё равно отклонит.
	if _api_scan_asked_at > 0.0 and now - _api_scan_asked_at < 30.0:
		return
	_api_scan_asked_at = now
	_api_scan_running = true
	# Прошлая неудача снимается на время новой попытки: держать её на экране,
	# пока идёт следующий обход, значит показывать причину, которой может уже не
	# быть.
	_api_scan_error = ""
	_api_pick_refresh_note()
	# force = false: обновлять всё подряд, не глядя на свежесть, больше некому —
	# ручной кнопки нет, а решение о возрасте данных принимает сервер.
	api_models_scan_requested.emit(false)


func _api_ensure_catalog_on() -> void:
	# ПОЛНЫЙ СПИСОК ПРОВАЙДЕРОВ ВКЛЮЧЁН ВСЕГДА.
	#
	# Раньше он был выключен по умолчанию, а включался флажком «все из
	# каталога». Флажок с длинной подписью занимал место в каждом открытии окна
	# ради решения, которое человек принимает один раз и всегда одинаково: он
	# пришёл выбирать провайдера и хочет видеть всех, кого плагин знает. Разницу
	# между разобранными вручную записями и взятыми из справочника показывает
	# отдельная группа списка, а не отсутствие ста шестидесяти строк.
	#
	# Состояние хранит СЕРВЕР (он же собирает список), поэтому включение — это
	# обычное сохранение настроек. Просим ОДИН раз за сессию: ответ придёт
	# набором настроек и снова попадёт сюда, и без этого условия получился бы
	# бесконечный круг «сохранили — перечитали — сохранили».
	if _api_catalog_asked:
		return
	# Каталога ещё нет вовсе — включать нечего, попробуем при следующем ответе.
	if int(_api_catalog.get("known_providers", 0)) <= 0:
		return
	if bool(_api_catalog.get("show_all", false)):
		_api_catalog_asked = true
		return
	_api_catalog_asked = true
	api_settings_save_requested.emit({"catalog": {"enabled": true}})


func set_api_scan_result(json: Dictionary) -> void:
	# Обход закончился — независимо от того, что он нашёл. Флаг снимается ВСЕГДА:
	# если оставить его выставленным после неудачи, следующее открытие окна
	# решит, что обход ещё идёт, и не станет ничего обновлять уже никогда.
	_api_scan_running = false
	# Сам список уже перерисован из общего ответа (set_api_settings) — здесь
	# остаётся только строка состояния под ним.
	if typeof(json) != TYPE_DICTIONARY:
		_api_pick_refresh_note()
		return
	# Обход не удался целиком (сервер не ответил или он старее панели и не знает
	# этого маршрута). Красной строки на весь экран за это не будет: обход идёт
	# сам, никто о нём не просил, и сообщение о его неудаче выглядело бы как
	# поломка плагина. Причина при этом не теряется — она видна под списком
	# провайдеров, то есть там, где человек и смотрит на эти числа.
	_api_scan_error = str(json.get("error", ""))
	_api_pick_refresh_note()
	if _api_scan_error != "":
		return
	var scanned: Array = json.get("scanned", [])
	var failed_list: Array = json.get("failed", [])
	if not scanned.is_empty() or not failed_list.is_empty():
		set_status(_t("api_scan_done") % [scanned.size(), failed_list.size()],
			"error" if scanned.is_empty() and not failed_list.is_empty() else "success")
	# Обход, который ничего не сделал, заканчивается МОЛЧА. Раньше здесь была
	# ветка «сказать, что обновлять было нечего» — она нужна была кнопке
	# «Обновить все списки»: нажатие без единого следа на экране читается как
	# сломанная кнопка. Кнопки больше нет, обход начинается сам при открытии
	# окна, и сообщение о нём стало бы ответом на вопрос, которого никто не
	# задавал.


func _api_build_pick_dialog() -> void:
	_api_pick_dialog = AcceptDialog.new()
	_api_pick_dialog.exclusive = true
	# Единственную кнопку диалога НЕ скрываем, а переименовываем в «Закрыть».
	# Выбор делается внутри окна, но окно модальное: остаться в нём без
	# видимого выхода нельзя, а надеяться на Esc в модальном окне — значит
	# надеяться, что фокус в нужном месте (в поле поиска он не там).
	add_child(_api_pick_dialog)

	var root := VBoxContainer.new()
	root.size_flags_horizontal = SIZE_EXPAND_FILL
	root.size_flags_vertical = SIZE_EXPAND_FILL
	root.add_theme_constant_override("separation", 8)
	_api_pick_dialog.add_child(root)

	# ИМЕННО HSplitContainer, а не HBoxContainer с фиксированной шириной списка.
	# Окно берётся clamped по размеру редактора (см. _on_api_pick_open), то есть
	# на маленьком экране оно узкое: жёстко заданные 250 px под список оставили
	# бы правой половине меньше половины окна, и описание превратилось бы в
	# столбик по одному слову. Разделитель можно потянуть — это единственный
	# способ починить пропорции, не зная заранее размера чужого экрана.
	var split := HSplitContainer.new()
	split.size_flags_horizontal = SIZE_EXPAND_FILL
	split.size_flags_vertical = SIZE_EXPAND_FILL
	split.split_offset = API_PICK_LIST_GROW
	root.add_child(split)
	split.add_child(_api_build_pick_left())
	split.add_child(_api_build_pick_right())
	_api_build_pick_bar(root)


# Наименьшая ширина списка имён. 300 px — это ровно столько, чтобы три чипа
# фильтра («Все», «С бесплатными», «Настроенные») встали в ОДНУ строку: в
# HFlowContainer перенос происходит по нехватке места, и при 250 px третий чип
# уезжал на вторую строку, отбирая у списка целую строку высоты в каждом
# открытии окна. Левая половина НЕ растягивается (у неё нет SIZE_EXPAND) — всё
# свободное место достаётся правой, где описание и модели.
const API_PICK_LIST_MIN := 300
# Насколько ШИРЕ наименьшего список открывается. Ноль: наименьшая ширина уже
# подобрана под ряд фильтров, и добавлять к ней нечего — лишние пиксели забрала
# бы правая половина, а там ряд пометок ещё длиннее.
#
# ИМЕННО СМЕЩЕНИЕ, А НЕ ШИРИНА. split_offset у SplitContainer отсчитывается от
# положения разделителя «по умолчанию», а оно у нерастягиваемой левой половины
# равно её наименьшей ширине. Написать сюда желаемые 300 значило бы получить
# список шириной 600 и оставить правой половине треть окна.
const API_PICK_LIST_GROW := 0
# Наименьшая ширина правой половины. 470 px подобраны под ряд пометок: «сейчас
# используется» + «ключ есть» + «список моделей без ключа» должны встать в одну
# строку с небольшим запасом, иначе пометки переносятся и карточка провайдера
# растёт в высоту от каждой мелочи. Вместе с левой задаёт наименьшую ширину
# окна.
const API_PICK_DETAIL_MIN := 470


func _api_build_pick_left() -> Control:
	# ЛЕВАЯ ПОЛОВИНА — ТОЛЬКО ИМЕНА. Ни пометок, ни чисел, ни описаний: строка
	# в высоту кнопки не зависит от того, сколько про провайдера известно, и
	# поэтому список одинаково листается что на семи записях, что на ста
	# шестидесяти пяти. Состояние показывает иконка слева от имени — она не
	# занимает ни одной дополнительной строки.
	var T = _T()
	var left := VBoxContainer.new()
	left.custom_minimum_size = Vector2(API_PICK_LIST_MIN, 0)
	# SIZE_EXPAND здесь НЕ ставится намеренно: у SplitContainer растягиваемая
	# половина забирает свободное место, а расти должна правая — там описание с
	# переносом и строки моделей. Заодно от этого зависит смысл split_offset
	# (см. API_PICK_LIST_GROW).
	left.size_flags_vertical = SIZE_EXPAND_FILL
	left.add_theme_constant_override("separation", 6)

	_api_pick_search = LineEdit.new()
	_api_pick_search.placeholder_text = _t("api_pick_search")
	_api_pick_search.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_pick_search.clear_button_enabled = true
	_api_pick_search.text_changed.connect(_on_api_pick_search)
	if T:
		T.style_input(_api_pick_search)
		_api_pick_search.right_icon = T.first_icon(["Search", "Zoom"])
	left.add_child(_api_pick_search)

	# Фильтры чипами, а не выпадающим списком: их три, они всегда видны, и
	# видно, какой включён. Flow — потому что список узкий (от 170 px), три
	# кнопки в один ряд там не встают, и третья уехала бы за край.
	var chips := HFlowContainer.new()
	chips.size_flags_horizontal = SIZE_EXPAND_FILL
	left.add_child(chips)
	var group := ButtonGroup.new()
	_api_add_chip(chips, group, "all", "api_pick_filter_all")
	_api_add_chip(chips, group, "free", "api_pick_filter_free")
	_api_add_chip(chips, group, "ready", "api_pick_filter_ready")

	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = SIZE_EXPAND_FILL
	scroll.size_flags_vertical = SIZE_EXPAND_FILL
	# Горизонтальная прокрутка выключена: имена обрезаются по ширине списка
	# (clip_text у строки), полное видно в подсказке, и прокручивать вбок нечего.
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	left.add_child(scroll)
	var inner := VBoxContainer.new()
	inner.size_flags_horizontal = SIZE_EXPAND_FILL
	inner.add_theme_constant_override("separation", 6)
	scroll.add_child(inner)

	# Разделение между строками 2 px, а не обычные 4–8: строки одного списка
	# должны читаться как список, а воздух между ними работает против этого.
	# Группы отделяются подписью, а не отступом.
	_api_pick_list = VBoxContainer.new()
	_api_pick_list.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_pick_list.add_theme_constant_override("separation", 2)
	inner.add_child(_api_pick_list)

	# Пустой результат объясняется словами, а не пустым экраном: у фильтра
	# «с бесплатными» пусто — это нормальное состояние до первого обновления
	# списков моделей, и человек должен узнать, что нажать.
	#
	# Подпись стоит ВНУТРИ прокрутки: с переносом в списке шириной 170 px она
	# занимает не одну строку, а восемь, и снаружи прокрутки эта высота стала бы
	# обязательной высотой всего окна.
	_api_pick_empty = Label.new()
	_api_pick_empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_api_pick_empty.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_pick_empty.add_theme_color_override("font_color", _color("dim"))
	_api_pick_empty.visible = false
	inner.add_child(_api_pick_empty)
	return left


func _api_build_pick_right() -> Control:
	# ПРАВАЯ ПОЛОВИНА — всё про ОДНОГО провайдера: имя, пометки, описание,
	# статистика, кнопка выбора и его модели с собственным фильтром. Здесь
	# длинные подписи с переносом уместны — ширина известна и не зависит от
	# числа записей в списке.
	var T = _T()
	var right := PanelContainer.new()
	right.custom_minimum_size = Vector2(API_PICK_DETAIL_MIN, 0)
	right.size_flags_horizontal = SIZE_EXPAND_FILL
	right.size_flags_vertical = SIZE_EXPAND_FILL
	if T:
		right.add_theme_stylebox_override("panel", T.panel_style("sunken"))
	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = SIZE_EXPAND_FILL
	scroll.size_flags_vertical = SIZE_EXPAND_FILL
	# Прокрутка обязательна и здесь, и по той же причине: подписи с переносом
	# сообщают контейнеру высоту, посчитанную по текущей ширине, и без
	# прокрутки описание на пять строк добавляло бы эти строки к обязательной
	# высоте окна. Внутри ScrollContainer наименьшая высота равна нулю.
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	right.add_child(scroll)
	_api_detail = VBoxContainer.new()
	_api_detail.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_detail.add_theme_constant_override("separation", 8)
	scroll.add_child(_api_detail)
	return right


func _api_build_pick_bar(root: Node) -> void:
	# НИЖНЯЯ ПОЛОСА — одна строка про список целиком: идёт ли обновление и
	# почему список короче ожидаемого.
	#
	# ЧЕГО ЗДЕСЬ БОЛЬШЕ НЕТ и почему. Кнопка «Обновить все списки» — обновление
	# и так идёт само при открытии окна, а провайдеров со старыми данными
	# отбирает сервер по возрасту (12 часов), то есть кнопка повторяла то, что
	# уже сделано. Флажок «все из каталога» — полный список теперь включён
	# всегда, выбирать нечего. Строка с датой каталога — она отвечала на вопрос,
	# которого никто не задавал, и занимала место рядом с тем, ради чего окно
	# открыли.
	#
	# Осталась одна строка: идёт ли обход, чем он кончился и сколько провайдеров
	# скрыл фильтр «с бесплатными» из-за отсутствия данных. Она объясняет, почему
	# в списке именно то, что в нём есть.
	_api_pick_note = _api_bar_label(root, "")


func _api_bar_label(parent: Node, tip: String) -> Label:
	# Строка нижней полосы: ОДНА строка с обрезкой по краю, полный текст — в
	# подсказке.
	#
	# ПОЧЕМУ БЕЗ ПЕРЕНОСА. Такая подпись стояла над списком с autowrap, и в
	# узком окне одна только строка про каталог занимала 205 px (замерено).
	# Подпись с переносом сообщает контейнеру высоту, посчитанную по текущей
	# ширине, поэтому она попадала в ОБЯЗАТЕЛЬНУЮ высоту окна, и диалог вылезал
	# за края экрана. clip_text убирает текст из наименьшего размера подписи
	# вовсе. Сведения при этом не теряются: весь текст показывается при
	# наведении, а это вторичные пояснения, а не то, ради чего окно открыли.
	var lbl := Label.new()
	lbl.size_flags_horizontal = SIZE_EXPAND_FILL
	lbl.clip_text = true
	lbl.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	# mouse_filter обязателен: у Label он по умолчанию IGNORE, и подсказка
	# никогда бы не показалась.
	lbl.mouse_filter = Control.MOUSE_FILTER_STOP
	lbl.tooltip_text = tip
	lbl.visible = false
	lbl.add_theme_color_override("font_color", _color("dim"))
	parent.add_child(lbl)
	return lbl


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


func _api_pick_query_ok(rec: Dictionary, query: String) -> bool:
	# Совпадение с поиском по НАЗВАНИЮ провайдера.
	if query == "":
		return true
	return str(rec.get("name", "")).to_lower().contains(query) \
		or str(rec.get("id", "")).to_lower().contains(query)


func _api_models_matching(rec: Dictionary, query: String) -> Array:
	# Модели ЭТОГО провайдера, подходящие под поиск. [{id, free}, ...].
	#
	# ПОЧЕМУ НЕ ОТ ОДНОГО СИМВОЛА. По «a» совпадёт почти каждая модель у каждого
	# провайдера, и список превратится в стену из четырёхсот кнопок, в которой
	# ничего не найти. Два символа — первый порог, на котором поиск начинает
	# что-то отсеивать.
	if query.length() < 2:
		return []
	var out: Array = []
	var pid := str(rec.get("id", ""))
	var source = _api_model_index.get(pid, [])
	if typeof(source) != TYPE_ARRAY or (source as Array).is_empty():
		# Запасной источник — зашитый в реестр перечень. У большинства
		# провайдеров он пуст намеренно (идентификаторы меняются слишком часто),
		# но там, где он есть, поиск обязан его видеть: иначе модель, про
		# которую плагин знает без всякой сети, «не находится».
		source = rec.get("models", [])
	if typeof(source) != TYPE_ARRAY:
		return []
	for m in source:
		var mid := ""
		if typeof(m) == TYPE_DICTIONARY:
			mid = str((m as Dictionary).get("id", ""))
			if mid != "" and mid.to_lower().contains(query):
				# Запись передаётся ЦЕЛИКОМ, а не пересобирается из id и free.
				# Кроме них она несёт дополнения каталога models.dev (цена, окно
				# контекста, tool_call, catalog_free), и пересборка молча теряла
				# бы их — подсказка на кнопке модели осталась бы пустой, а
				# пометку «бесплатная по каталогу» стало бы неоткуда взять.
				out.append(m)
		else:
			mid = str(m)
			if mid != "" and mid.to_lower().contains(query):
				out.append({"id": mid, "free": false})
	return out


func _api_pick_search_hit(rec: Dictionary, query: String) -> bool:
	# Провайдер подходит под поиск, если совпало его название ИЛИ у него есть
	# подходящая модель. Второе и есть смысл поиска: человек ищет «kimi», а не
	# «Opencode Zen», и не обязан знать, кто эту модель отдаёт.
	return _api_pick_query_ok(rec, query) \
		or not _api_models_matching(rec, query).is_empty()


func _api_pick_matches(rec: Dictionary, query: String) -> bool:
	if not _api_pick_search_hit(rec, query):
		return false
	match _api_pick_filter:
		"ready":
			# Именно готовность или сохранённый ключ, а НЕ «ключ не обязателен».
			# По прежнему условию под «Настроенные» попадал «Свой адрес», у
			# которого ключ не нужен: то есть провайдер, где не задано вообще
			# ничего, показывался среди настроенных.
			return bool(rec.get("ready", false)) or bool(rec.get("configured", false))
		"free":
			# Только по ИЗМЕРЕННОМУ числу бесплатных моделей. Догадываться по
			# описанию провайдера нельзя: «бесплатный тариф» в тексте реестра —
			# это наше утверждение, которое устареет молча, а число пришло из
			# ответа самого сервиса.
			#
			# УЧИТЫВАЕМ ОБА ИСТОЧНИКА. models_free измерен по ответу
			# провайдера, models_free_catalog — по справочнику models.dev, и они
			# расходятся: у Opencode Zen модель big-pickle имеет в каталоге
			# нулевую цену, а по суффиксу в имени выглядит платной (замерено).
			# Отбирать только по первому значило бы прятать провайдера, у
			# которого бесплатные модели есть, — а именно от этого фильтр и
			# спасает. Откуда сведения, видно на карточке: там два числа с
			# разными подписями, а не одно объединённое.
			var stats: Dictionary = rec.get("stats", {})
			return int(stats.get("models_free", -1)) > 0 \
				or int(stats.get("models_free_catalog", -1)) > 0
	return true


func _api_free_unknown(rec: Dictionary) -> bool:
	# Число бесплатных моделей у провайдера НЕ ИЗМЕРЕНО НИ ОДНИМ источником. Это
	# не то же самое, что «бесплатных нет»: спросить провайдера без ключа обычно
	# нельзя, а каталог знает не всех (agentrouter в нём отсутствует вовсе,
	# «свой адрес» — по своей природе). Пока молчат оба, единственный честный
	# ответ — «неизвестно», и провайдер не выбрасывается молча: сколько таких
	# скрыто, написано над списком.
	var stats: Dictionary = rec.get("stats", {})
	return int(stats.get("models_free", -1)) < 0 \
		and int(stats.get("models_free_catalog", -1)) < 0


func _api_rebuild_pick_list() -> void:
	if _api_pick_list == null or not is_instance_valid(_api_pick_list):
		return
	_clear_container(_api_pick_list)
	_api_pick_pending.clear()
	# Словарь строк и группа переключателей пересоздаются вместе со списком:
	# прежние кнопки только что освобождены, и ссылки на них указывали бы на
	# мёртвые объекты.
	_api_pick_rows.clear()
	_api_row_group = ButtonGroup.new()
	var query := ""
	if _api_pick_search:
		query = _api_pick_search.text.strip_edges().to_lower()
	var ready_recs: Array = []
	var setup_recs: Array = []
	var blocked_recs: Array = []
	# Записи из каталога — ОТДЕЛЬНОЙ группой, а не вперемешку с разобранными.
	# Про наши семь известны их особенности (белый список клиентов AgentRouter,
	# ловушка api.opencode.ai, увеличенный таймаут посредника), а про эти сто
	# шестьдесят не проверено ничего. Смешать их в одном списке значит стереть
	# разницу между «проверено» и «взято из справочника» — и человек выберет
	# незнакомый сервис, думая, что он разобран так же.
	var catalog_recs: Array = []
	# Все подошедшие под фильтр — в порядке показа. Нужны, чтобы решить, что
	# показывать справа: строки свёрнутой группы не собираются вовсе, и по одним
	# кнопкам этого не узнать.
	var visible_ids: Array = []
	_api_pick_hidden_unknown = 0
	for p in _api_data.get("providers", []):
		if typeof(p) != TYPE_DICTIONARY:
			continue
		var rec: Dictionary = p
		if not _api_pick_matches(rec, query):
			# СКОЛЬКО провайдеров фильтр «с бесплатными» скрыл не потому, что у
			# них нет бесплатных моделей, а потому, что их никто не считал. Без
			# этого числа короткий список читается как полный ответ: «бесплатные
			# модели есть только у одного провайдера» — а это неправда.
			# Считаем только подошедших под поиск: про остальных пользователь и
			# не спрашивал, и объяснять их отсутствие незачем.
			if _api_pick_filter == "free" and _api_pick_search_hit(rec, query) \
					and _api_free_unknown(rec) \
					and str(rec.get("unavailable", "")) == "":
				_api_pick_hidden_unknown += 1
			continue
		if str(rec.get("unavailable", "")) != "":
			blocked_recs.append(rec)
		elif bool(rec.get("from_catalog", false)) \
				and not bool(rec.get("configured", false)):
			# Настроенная каталожная запись переезжает в обычные группы: у неё
			# уже есть ключ, то есть человек с ней работает, и держать её среди
			# ста шестидесяти незнакомых значит спрятать своё же.
			catalog_recs.append(rec)
		elif bool(rec.get("ready", false)):
			ready_recs.append(rec)
		else:
			setup_recs.append(rec)
	# «ВОЗМОЖНО БЕСПЛАТНЫЕ» — отдельной группой и только при фильтре «с
	# бесплатными». Это провайдеры, у которых бесплатные модели ЕСТЬ ПО КАТАЛОГУ,
	# а живого подтверждения нет: спросить их список без ключа нельзя, потому что
	# мы у них не зарегистрированы. Держать их вперемешку с измеренными значило бы
	# выдать чужой справочник за наблюдение; выбрасывать — соврать, что
	# бесплатных моделей там нет. Отдельная группа с честным названием оставляет
	# решение человеку: захочет — зарегистрируется и проверит сам.
	var maybe_recs: Array = []
	if _api_pick_filter == "free":
		for lists in [ready_recs, setup_recs, catalog_recs]:
			var keep: Array = []
			for rec in lists:
				if _api_free_by_catalog_only(rec):
					maybe_recs.append(rec)
				else:
					keep.append(rec)
			# clear + append_array, а не assign: тот же результат, но без
			# зависимости от версии Godot, в которой assign появился.
			lists.clear()
			lists.append_array(keep)
		# Сверху — те, у кого каталог обещает больше: если проверять вручную, то
		# начинать с самого щедрого.
		maybe_recs.sort_custom(_api_cmp_catalog_free)
	var shown := ready_recs.size() + setup_recs.size() + blocked_recs.size() \
		+ catalog_recs.size() + maybe_recs.size()
	_api_add_pick_group("ready", "api_pick_group_ready", ready_recs, false)
	# Группа «возможно бесплатные» стоит СРАЗУ под подтверждёнными и раскрытой:
	# она и есть ответ на нажатие «с бесплатными», и закрытая она выглядела бы
	# как её отсутствие.
	_api_add_pick_group("maybe_free", "api_pick_group_maybe_free", maybe_recs,
		false, "api_pick_group_maybe_free_tip")
	# КАТАЛОГ — СРАЗУ ПОСЛЕ ГОТОВЫХ, а не в конце списка. Человек должен видеть,
	# что выбор не ограничен семью разобранными записями: их 165, и узнать об
	# этом, прокрутив мимо «можно настроить» и «недоступны», он не обязан.
	# «Можно настроить» при этом свёрнуто по умолчанию: там провайдеры, до
	# которых ещё надо дойти (получить ключ), и раскрытыми они вытесняют с экрана
	# главное — что доступно прямо сейчас и что вообще есть.
	#
	# Свёрнута: их сто пятьдесят восемь, раскрытыми они вытеснили бы с экрана
	# всё проверенное.
	_api_add_pick_group("catalog", "api_pick_group_catalog", catalog_recs, true)
	_api_add_pick_group("setup", "api_pick_group_setup", setup_recs, true)
	# Недоступные свёрнуты по умолчанию: их нельзя выбрать, и держать их
	# раскрытыми значит каждый раз прокручивать список мимо них.
	_api_add_pick_group("blocked", "api_pick_group_blocked", blocked_recs, true)
	for group_recs in [ready_recs, maybe_recs, catalog_recs, setup_recs, blocked_recs]:
		for rec in group_recs:
			visible_ids.append(str(rec.get("id", "")))
	if _api_pick_empty:
		_api_pick_empty.visible = shown == 0
		if shown == 0:
			_api_pick_empty.text = _t("api_pick_no_free_data") \
				if _api_pick_filter == "free" and query == "" else _t("api_pick_nothing")
	_api_pick_refresh_note()
	_api_pick_sync_selection(visible_ids, query)


func _api_pick_sync_selection(visible_ids: Array, query: String) -> void:
	# Что показывать справа после перестройки списка.
	#
	# ПОЧЕМУ ВСЕГДА ХОТЬ ЧТО-ТО. Пустая правая половина при непустом списке
	# читается как поломка: половина окна есть, в ней ничего нет. Поэтому если
	# показанный провайдер вылетел из списка (сменился фильтр, уточнился поиск),
	# берём текущего, а если и его отфильтровали — первого подошедшего.
	if _api_pick_shown == "" or not visible_ids.has(_api_pick_shown):
		var current := _api_current_provider()
		if visible_ids.has(current):
			_api_pick_shown = current
		elif not visible_ids.is_empty():
			_api_pick_shown = str(visible_ids[0])
		else:
			_api_pick_shown = ""
	# Подсветка строки. Строки свёрнутой группы не собраны вовсе — тогда
	# подсвечивать нечего, но правая половина всё равно показывает провайдера:
	# он подошёл под фильтр, просто его группа закрыта.
	if _api_pick_rows.has(_api_pick_shown):
		var row = _api_pick_rows[_api_pick_shown]
		# is_instance_valid ПЕРВЫМ: у освобождённого объекта проверка типа сама
		# по себе выдаёт ошибку обращения к освобождённому экземпляру.
		if is_instance_valid(row) and row is Button:
			row.button_pressed = true
	# ПОИСК ПЕРЕЕЗЖАЕТ В ФИЛЬТР МОДЕЛЕЙ. Слева ищут и по названию модели (в
	# список попадает провайдер, у которого она есть), поэтому набранное «kimi»
	# должно оказаться и в фильтре справа: иначе человек, нашедший провайдера по
	# модели, обязан набрать её название второй раз, чтобы увидеть среди
	# трёхсот. Перенос делается ТОЛЬКО при смене запроса — иначе он затирал бы
	# фильтр, который человек сам набрал в правой половине.
	var query_changed := query != _api_pick_query
	_api_pick_query = query
	_api_show_detail()
	if query_changed and _api_detail_filter and is_instance_valid(_api_detail_filter):
		# Меньше двух символов фильтр не применяет и сам поиск моделей (см.
		# _api_models_matching): по одной букве совпадает почти каждая модель.
		_api_detail_filter.text = query if query.length() >= 2 else ""
		_api_detail_rebuild_models()


func _api_free_by_catalog_only(rec: Dictionary) -> bool:
	# Бесплатные модели есть ПО КАТАЛОГУ, а живого подтверждения нет.
	#
	# Это третье состояние, и путать его с двумя другими нельзя. «Есть
	# бесплатные» — измерено по ответу самого провайдера нашим ключом или без
	# ключа. «Неизвестно» — не сказал ни один источник. А здесь справочник
	# models.dev утверждает, что у сервиса бесплатные модели есть, но спросить
	# его самого мы не можем: у нас нет там регистрации. Такое утверждение можно
	# показать только с оговоркой — отдельной группой «возможно бесплатные».
	var stats: Dictionary = rec.get("stats", {})
	return int(stats.get("models_free", -1)) <= 0 \
		and int(stats.get("models_free_catalog", -1)) > 0


func _api_catalog_free_of(rec) -> int:
	if typeof(rec) != TYPE_DICTIONARY:
		return 0
	var stats: Dictionary = (rec as Dictionary).get("stats", {})
	return int(stats.get("models_free_catalog", 0))


func _api_cmp_catalog_free(a, b) -> bool:
	return _api_catalog_free_of(a) > _api_catalog_free_of(b)


func _api_pick_refresh_note() -> void:
	# Строка в нижней полосе: что сейчас происходит с данными и почему список
	# короче, чем можно ожидать.
	if _api_pick_note == null or not is_instance_valid(_api_pick_note):
		return
	var text := ""
	var tip := ""
	var tone := "warning"
	if _api_scan_running:
		text = _t("api_pick_scanning")
		tone = "dim"
	elif _api_scan_error != "":
		# Причина неудачи обхода живёт здесь, а не в общей статусной строке:
		# обход идёт сам, и красная строка на весь экран за автоматическое
		# действие выглядит как поломка плагина (см. set_api_scan_result).
		text = _t("api_pick_scan_failed") % _api_scan_error
		tone = "error"
	elif _api_pick_filter == "free" and _api_pick_hidden_unknown > 0:
		# КОРОТКО В СТРОКЕ, ПОДРОБНО В ПОДСКАЗКЕ. Строка нижней полосы
		# однострочная и обрезается по краю окна, а в длинной фразе число стоит
		# в самом конце — оно обрезалось бы первым, то есть пропадало бы ровно
		# то, ради чего строка и показана.
		text = _t("api_pick_free_hidden_short") % _api_pick_hidden_unknown
		tip = _t("api_pick_free_hidden") % _api_pick_hidden_unknown
	_api_pick_note.text = text
	_api_pick_note.tooltip_text = tip if tip != "" else text
	_api_pick_note.visible = text != ""
	_api_pick_note.add_theme_color_override("font_color", _color(tone))


func _api_add_pick_group(key: String, title_key: String, recs: Array,
		collapsed_by_default: bool, tip_key: String = "") -> void:
	if recs.is_empty():
		return
	var T = _T()
	# Отступ ПЕРЕД группой, а не разделение между строками: список из имён должен
	# читаться как список, поэтому строки стоят плотно (2 px), а воздух нужен
	# ровно там, где начинается другая группа.
	if _api_pick_list.get_child_count() > 0:
		var gap := Control.new()
		gap.custom_minimum_size = Vector2(0, 8)
		_api_pick_list.add_child(gap)
	var head := Button.new()
	head.text = _t(title_key) % recs.size()
	# Подсказка группы: у «возможно бесплатных» она обязательна — там надо
	# объяснить, почему «возможно», а не «есть». У остальных подсказка повторяет
	# заголовок: он обрезается по ширине списка, и полностью прочитать его можно
	# только наведением.
	head.tooltip_text = (head.text + "\n\n" + _t(tip_key)) if tip_key != "" \
		else head.text
	head.toggle_mode = true
	head.alignment = HORIZONTAL_ALIGNMENT_LEFT
	# clip_text, а не перенос: заголовок «Из каталога models.dev, не проверены
	# (158)» в списке шириной 250 px занял бы две строки и стал бы выше строк,
	# которые он подписывает, — подпись перевесила бы содержимое.
	head.clip_text = true
	head.size_flags_horizontal = SIZE_EXPAND_FILL
	if not _api_pick_collapsed.has(key):
		_api_pick_collapsed[key] = collapsed_by_default
	var open := not bool(_api_pick_collapsed[key])
	head.button_pressed = open
	if T:
		# ПРИГЛУШЁННЫМ, а не акцентным. Заголовков четыре, и раньше все четыре
		# были жёлтыми: в списке из спокойных строк с именами четыре ярких
		# подписи перетягивали внимание на себя, то есть на служебное деление, а
		# не на провайдеров. Тонкая серая подпись делает ровно то, что должна:
		# помечает границу и не спорит с содержимым.
		T.style_button(head, "dim", true)
		# У Button нет icon_rotation, поэтому стрелка — это две разные иконки
		# темы (тот же приём, что в ToolCallCard).
		head.icon = T.first_icon(["GuiTreeArrowDown"] if open else ["GuiTreeArrowRight"])
	_api_pick_list.add_child(head)

	var box := VBoxContainer.new()
	box.size_flags_horizontal = SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 2)
	box.visible = open
	_api_pick_list.add_child(box)
	# Подключаем ПОСЛЕ установки button_pressed: иначе начальное значение само
	# выглядело бы как нажатие пользователя. И переключаем видимость, а не
	# перестраиваем список целиком — перестройка освободила бы кнопку, чей
	# сигнал прямо сейчас обрабатывается.
	head.toggled.connect(_on_api_pick_group_toggled.bind(key, head, box))
	# СВЁРНУТУЮ ГРУППУ НЕ СОБИРАЕМ ВОВСЕ. Строка теперь дешёвая (одна кнопка
	# вместо панели с пятью блоками), но список перестраивается на КАЖДУЮ букву
	# в поиске, а записей каталога сто шестьдесят три: собирать их все впустую
	# незачем, когда группа закрыта и ни одной из них не видно. Записи
	# запоминаем и собираем при первом раскрытии.
	if open:
		_api_fill_pick_group(box, recs)
	else:
		_api_pick_pending[key] = {"recs": recs, "box": box}


# Список провайдеров показывается ЦЕЛИКОМ, без ограничения на число строк.
#
# Раньше в группе показывалось не больше пятидесяти записей, а остальные
# заменялись подписью «скрыто ещё N — уточните поиск»: ограничение стояло, пока
# запись была карточкой из пяти блоков и собиралась 1.9 мс, то есть весь каталог
# занимал треть секунды на каждую букву в поиске. Теперь строка — одна кнопка, и
# главное ограничение снялось само: группа с каталогом свёрнута по умолчанию и
# не собирается вовсе, пока её не раскроют, а раскрывший её человек как раз и
# хочет увидеть всех.
func _api_fill_pick_group(box: VBoxContainer, recs: Array) -> void:
	for rec in recs:
		_api_add_pick_row(box, rec)


func _on_api_pick_group_toggled(pressed: bool, key: String, head: Button,
		box: VBoxContainer) -> void:
	_api_pick_collapsed[key] = not pressed
	if is_instance_valid(box):
		# Раскрыли впервые — только теперь собираем строки (см. пояснение в
		# _api_add_pick_group).
		if pressed and box.get_child_count() == 0 and _api_pick_pending.has(key):
			var hold: Dictionary = _api_pick_pending[key]
			if hold.get("box") == box:
				_api_fill_pick_group(box, hold.get("recs", []))
				# Раскрытая группа могла принести строку показанного справа
				# провайдера: до раскрытия её не существовало, и подсветить было
				# нечего.
				if _api_pick_rows.has(_api_pick_shown):
					var row = _api_pick_rows[_api_pick_shown]
					if is_instance_valid(row) and row is Button:
						row.button_pressed = true
		box.visible = pressed
	# У Button нет icon_rotation, поэтому стрелка — две разные иконки темы.
	var T = _T()
	if T and is_instance_valid(head):
		head.icon = T.first_icon(["GuiTreeArrowDown"] if pressed else ["GuiTreeArrowRight"])


# Высота строки списка. 26 px — это высота обычной кнопки редактора без запаса:
# строк на экране должно быть видно как можно больше, а нажимать по ним всё ещё
# удобно. Замерено: при 26 px в окне высотой 560 видно четырнадцать строк против
# двух с половиной прежних карточек.
const API_PICK_ROW_HEIGHT := 26


func _api_add_pick_row(parent: Node, rec: Dictionary) -> void:
	# СТРОКА — ЭТО ОДНА КНОПКА. Ни панели, ни вложенных контейнеров: у неё есть
	# и текст, и иконка, и готовая подсветка выбранного состояния от темы
	# редактора. Прежняя карточка была панелью с кнопкой, рядом пометок,
	# описанием и чипами моделей — около двадцати узлов на провайдера и 1.9 мс
	# сборки; здесь узел один.
	var T = _T()
	var pid := str(rec.get("id", ""))
	var blocked := str(rec.get("unavailable", "")) != ""
	var row := Button.new()
	row.text = str(rec.get("name", pid))
	# Какой провайдер работает ПРЯМО СЕЙЧАС — коротким хвостом у имени.
	# Подсветка строки этого сказать не может: она означает «показан справа», а
	# листать описания можно не меняя выбора. Полная фраза — в подсказке.
	if pid == _api_current_provider():
		row.text += "  " + _t("api_pick_in_use_short")
	row.alignment = HORIZONTAL_ALIGNMENT_LEFT
	# clip_text обязателен: наименьшая ширина кнопки с текстом равна ширине
	# текста, а список бывает 170 px — без обрезки самые длинные имена
	# растягивали бы левую половину и отбирали место у правой.
	row.clip_text = true
	row.size_flags_horizontal = SIZE_EXPAND_FILL
	row.custom_minimum_size = Vector2(0, API_PICK_ROW_HEIGHT)
	# toggle_mode с общей группой — и есть «выбрана ровно одна строка»: тема
	# редактора рисует нажатую кнопку иначе, и своей подсветки не требуется.
	row.toggle_mode = true
	row.button_group = _api_row_group
	# Подсказка отвечает на «почему у него такая иконка»: причина неготовности
	# словами, а у недоступного — чем именно он недоступен.
	var tip := str(rec.get("name", pid))
	if blocked:
		tip += "\n" + str(rec.get("unavailable", ""))
	else:
		var why := _api_why(rec)
		if why != "":
			tip += "\n" + why
	row.tooltip_text = tip
	# Значение ставим ДО подключения сигнала. Присваивание button_pressed
	# вызывает toggled, а не pressed, но порядок всё равно этот: следующая
	# правка легко переключится на toggled, и тогда начальное значение
	# выглядело бы как нажатие пользователем.
	row.button_pressed = pid == _api_pick_shown
	row.pressed.connect(_on_api_pick_row.bind(pid))
	if T:
		# СОСТОЯНИЕ ИКОНКОЙ, А НЕ СТРОКОЙ ТЕКСТА. Четыре пометки словами занимали
		# на карточке отдельную строку у каждого провайдера; иконка слева от имени
		# не занимает ни одной, а различить четыре состояния взглядом по цвету и
		# форме проще, чем прочитать четыре подписи.
		var tone := "neutral"
		var icons := ["Key", "Script"]
		if blocked:
			tone = "dim"
			icons = ["StatusError", "NodeWarning", "Unlinked"]
		elif bool(rec.get("ready", false)):
			tone = "success"
			icons = ["StatusSuccess"]
		elif bool(rec.get("configured", false)):
			# Ключ есть, но чего-то не хватает (обычно модели): это НЕ то же
			# самое, что «нужен ключ», и путать их значит отправлять человека
			# искать ключ, который у него уже сохранён.
			tone = "warning"
			icons = ["StatusWarning", "NodeWarning"]
		T.style_button(row, tone, false)
		row.icon = T.first_icon(icons)
	parent.add_child(row)
	_api_pick_rows[pid] = row


func _on_api_pick_row(pid: String) -> void:
	# Нажатие на строку НЕ ВЫБИРАЕТ провайдера — только показывает его справа.
	# Разделение намеренное: список нужен и для того, чтобы почитать, что вообще
	# есть, а выбор при каждом таком чтении отправлял бы на сервер новый
	# провайдер по умолчанию и менял бы форму настроек под окном.
	if pid == "" or pid == _api_pick_shown:
		return
	_api_pick_shown = pid
	_api_show_detail()


func _api_show_detail() -> void:
	# ПРАВАЯ ПОЛОВИНА: всё, что известно про одного провайдера.
	#
	# Собирается ЗАНОВО при смене строки, а не прячется-показывается: полей у
	# провайдера разное число (у недоступного нет ни статистики, ни моделей, у
	# каталожного нет измеренных чисел), и держать все варианты собранными
	# значит держать половину окна из скрытых узлов, которые надо не забыть
	# спрятать в каждой ветке.
	if _api_detail == null or not is_instance_valid(_api_detail):
		return
	var pid := _api_pick_shown
	# Список перестраивается на каждую букву в поиске, а провайдер справа при
	# этом обычно тот же: собирать заново шестьдесят строк моделей незачем.
	if pid == _api_detail_built_for and _api_detail.get_child_count() > 0:
		return
	# Фильтр моделей, «только бесплатные» и НАБРАННЫЙ КЛЮЧ переживают пересборку
	# той же половины. Пересборку заказывает не только нажатие на строку: её же
	# требует любой ответ сервера с настройками, а обход за списками моделей
	# заканчивается через несколько секунд после открытия окна — то есть как раз
	# тогда, когда человек уже вставил ключ и не успел нажать «Сохранить».
	# Стереть его ответом, которого никто не просил, значит заставить искать ключ
	# заново.
	var keep_filter := ""
	var keep_free := false
	var keep_key := ""
	if pid == _api_detail_built_for:
		if _api_detail_filter and is_instance_valid(_api_detail_filter):
			keep_filter = _api_detail_filter.text
		if _api_detail_free and is_instance_valid(_api_detail_free):
			keep_free = _api_detail_free.button_pressed
		if _api_detail_key and is_instance_valid(_api_detail_key):
			keep_key = _api_detail_key.text
	_clear_container(_api_detail)
	# Ссылки на части правой половины — только что освобождённые узлы. Обнуляем
	# СРАЗУ: между очисткой и сборкой стоит проверка на пустого провайдера, и по
	# ней функция может выйти, оставив ссылки на мёртвые объекты.
	_api_detail_models = null
	_api_detail_cap = null
	_api_detail_filter = null
	_api_detail_free = null
	_api_detail_key = null
	_api_detail_built_for = pid
	var rec := _api_provider_rec(pid)
	if pid == "" or rec.is_empty():
		_api_hint(_api_detail, _t("api_pick_detail_hint"))
		return

	var T = _T()
	var blocked := str(rec.get("unavailable", "")) != ""

	# Имя — крупно и первой строкой: это ответ на «о ком тут речь», и он должен
	# читаться раньше всего остального.
	var title := Label.new()
	title.text = str(rec.get("name", pid))
	title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	title.size_flags_horizontal = SIZE_EXPAND_FILL
	title.add_theme_color_override("font_color", _color("text"))
	if T:
		title.add_theme_font_size_override("font_size", T.font_size("Label", 13) + 4)
	_api_detail.add_child(title)

	# Пометки — пилюлями с фоном, а не цветным текстом в строку. Голыми
	# подписями пять пометок подряд читались как одно предложение в трёх цветах.
	var badges := _api_pick_badges(rec)
	if pid == _api_current_provider():
		# «Используется сейчас» стоит ПЕРВОЙ и в акцентном тоне: это единственная
		# пометка, отвечающая не про сервис, а про текущее состояние плагина.
		badges.insert(0, {"text": _t("api_pick_current"), "tone": "accent"})
	if not badges.is_empty():
		var badge_row := HFlowContainer.new()
		badge_row.size_flags_horizontal = SIZE_EXPAND_FILL
		_api_detail.add_child(badge_row)
		for badge in badges:
			_api_add_badge(badge_row, str(badge.get("text", "")),
				str(badge.get("tone", "dim")))

	# КНОПКА ВЫБОРА — ВЫШЕ описания и статистики. Человек, который уже знает, кто
	# ему нужен, не должен прокручивать мимо трёх абзацев, чтобы её найти; тот,
	# кто не знает, прочитает описание под ней и вернётся к ней глазами.
	var pick := Button.new()
	pick.text = _t("api_pick_choose")
	pick.tooltip_text = _t("api_pick_choose_tip")
	pick.size_flags_horizontal = SIZE_EXPAND_FILL
	pick.custom_minimum_size = Vector2(0, 32)
	# Недоступного провайдера нельзя выбрать: он всё равно отклонит запрос, а
	# «выбрал и не работает» выглядит поломкой плагина, а не ограничением сервиса.
	pick.disabled = blocked
	if not blocked:
		pick.pressed.connect(_on_api_pick_choose.bind(pid))
	if T:
		T.style_button(pick, "dim" if blocked else "accent", false)
		pick.icon = T.first_icon(["StatusSuccess", "Play"])
	_api_detail.add_child(pick)

	# Описание провайдера сервер присылает на двух языках, поэтому «русский или
	# английский», а не «не английский»: языков в плагине может быть больше, и
	# немецкому интерфейсу русское описание не поможет.
	var lang_note := "note_ru" if _lang() == "ru" else "note_en"
	var note := str(rec.get(lang_note, ""))
	if blocked:
		# У недоступного провайдера важнее причина, чем описание возможностей:
		# описание обещало бы то, чем нельзя воспользоваться.
		note = str(rec.get("unavailable", ""))
	if note != "":
		var note_lbl := _api_hint(_api_detail, note)
		if blocked:
			note_lbl.add_theme_color_override("font_color", _color("warning"))
	# Чего не хватает до готовности — словами и предупреждающим цветом. На
	# карточке этого не было вовсе: причина жила только в подсказке кнопки
	# «начать чат» на экране под окном, то есть там, куда человек ещё не дошёл.
	if not blocked and not bool(rec.get("ready", false)):
		var why := _api_why(rec)
		if why != "":
			var why_lbl := _api_hint(_api_detail, _t("api_not_ready_note") % why)
			why_lbl.add_theme_color_override("font_color", _color("warning"))
	var stats_line := _api_pick_stats_line(rec)
	if stats_line != "":
		_api_hint(_api_detail, stats_line)

	_api_detail.add_child(HSeparator.new())
	_api_build_detail_key(rec, keep_key)
	_api_detail.add_child(HSeparator.new())
	_api_build_detail_models(rec, keep_filter, keep_free)


func _api_build_detail_key(rec: Dictionary, keep_key: String = "") -> void:
	# КЛЮЧ ЗДЕСЬ, А НЕ В ФОРМЕ ПОД ОКНОМ. В форме поле ключа относилось к
	# «текущему» провайдеру, то есть к тому, кого уже выбрали: чтобы завести ключ
	# другому сервису, надо было сначала переключиться на него, потеряв рабочего.
	# В карточке провайдера поле стоит рядом с его названием и описанием — и
	# заводить ключи можно хоть трём сервисам подряд, не меняя того, через кого
	# работаешь сейчас.
	var T = _T()
	var env := str(rec.get("key_source", "")) == "env"
	var cap := Label.new()
	cap.text = _t("api_key")
	cap.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	cap.size_flags_horizontal = SIZE_EXPAND_FILL
	cap.add_theme_color_override("font_color", _color("accent"))
	_api_detail.add_child(cap)

	# Ключ из переменной окружения: поля нет вовсе. Показать пустое поле рядом с
	# «ключ задан переменной окружения» значило бы предложить перезаписать то,
	# что задано снаружи плагина и им не управляется.
	if not env:
		# Flow, а не HBox: поле и две кнопки в правой половине от 470 px обычно
		# встают в строку, но при утянутом влево разделителе — нет, и «Удалить»
		# уехала бы за край.
		var row := HFlowContainer.new()
		row.size_flags_horizontal = SIZE_EXPAND_FILL
		_api_detail.add_child(row)
		_api_detail_key = LineEdit.new()
		# secret = true: ключ не должен быть виден на экране — в том числе на
		# записи экрана или стриме, где его увидели бы посторонние.
		_api_detail_key.secret = true
		_api_detail_key.placeholder_text = _t("api_key_placeholder")
		_api_detail_key.size_flags_horizontal = SIZE_EXPAND_FILL
		_api_detail_key.custom_minimum_size = Vector2(140, 0)
		# Набранное восстанавливаем ДО подключения сигнала — так же, как в поле
		# фильтра моделей.
		_api_detail_key.text = keep_key
		_api_detail_key.text_submitted.connect(func(_s): _on_api_detail_key_save())
		if T:
			T.style_input(_api_detail_key)
		row.add_child(_api_detail_key)
		var save := Button.new()
		save.text = _t("api_key_save")
		save.pressed.connect(_on_api_detail_key_save)
		if T:
			T.style_button(save, "accent")
			save.icon = T.first_icon(["Save", "FileList"])
		row.add_child(save)
		var del := Button.new()
		del.text = _t("api_key_delete")
		del.tooltip_text = _t("api_key_delete_tip")
		del.pressed.connect(_on_api_detail_key_delete)
		if T:
			T.style_button(del, "warning")
			del.icon = T.first_icon(["Remove", "Close"])
		row.add_child(del)

	# Состояние ключа словами и с маской: «ключ есть» пометкой выше отвечает на
	# «есть или нет», а здесь видно, КАКОЙ именно — по последним символам можно
	# отличить свой ключ от чужого, не показывая его целиком.
	var state := ""
	if env:
		state = _t("api_key_from_env") % str(rec.get("masked", ""))
	elif bool(rec.get("configured", false)):
		state = _t("api_key_set") % str(rec.get("masked", ""))
	elif bool(rec.get("needs_key", true)):
		state = _t("api_key_missing")
	else:
		state = _t("api_key_optional")
	_api_hint(_api_detail, state)


func _api_add_badge(parent: Node, text: String, tone: String) -> void:
	if text == "":
		return
	var T = _T()
	var pill := PanelContainer.new()
	if T:
		pill.add_theme_stylebox_override("panel", T.badge_style(tone))
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_color_override("font_color", _color(tone))
	pill.add_child(lbl)
	parent.add_child(pill)


func _api_build_detail_models(rec: Dictionary, keep_filter: String = "",
		keep_free: bool = false) -> void:
	# МОДЕЛИ ПРОВАЙДЕРА — со своим фильтром и переключателем «только
	# бесплатные». Раньше модели показывались только при поиске от двух букв и
	# только восемь штук: узнать, что вообще есть у провайдера, было нельзя —
	# для этого приходилось выбрать его, вернуться в форму и нажать там
	# «Обновить список». Здесь виден весь список сразу, а фильтр отвечает на
	# «есть ли у него что-то такое».
	var T = _T()
	if str(rec.get("id", "")) == "":
		return
	_api_detail_cap = Label.new()
	_api_detail_cap.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_api_detail_cap.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_detail_cap.add_theme_color_override("font_color", _color("accent"))
	_api_detail.add_child(_api_detail_cap)

	# Flow, а не HBox: поле фильтра, переключатель и кнопка обновления в правой
	# половине (от 470 px) обычно встают в строку, но при утянутом влево
	# разделителе — нет, и кнопка уехала бы за край.
	var row := HFlowContainer.new()
	row.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_detail.add_child(row)
	_api_detail_filter = LineEdit.new()
	_api_detail_filter.placeholder_text = _t("api_pick_models_filter")
	_api_detail_filter.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_detail_filter.custom_minimum_size = Vector2(120, 0)
	_api_detail_filter.clear_button_enabled = true
	# Набранное восстанавливаем ДО подключения сигнала: присваивание text у
	# LineEdit не вызывает text_changed, но следующая правка легко переставит
	# строки местами, и тогда восстановление выглядело бы как ввод пользователя.
	_api_detail_filter.text = keep_filter
	_api_detail_filter.text_changed.connect(_on_api_detail_filter)
	if T:
		T.style_input(_api_detail_filter)
		_api_detail_filter.right_icon = T.first_icon(["Search", "Zoom"])
	row.add_child(_api_detail_filter)
	# КНОПКОЙ-ПЕРЕКЛЮЧАТЕЛЕМ, а не флажком: нажатое состояние кнопки видно
	# издалека, а флажок в ряду с полем ввода читается как подпись к нему.
	_api_detail_free = Button.new()
	_api_detail_free.text = _t("api_pick_models_free_only")
	_api_detail_free.tooltip_text = _t("api_pick_models_free_tip")
	_api_detail_free.toggle_mode = true
	# Состояние ставим ДО подключения сигнала: иначе восстановление прежнего
	# положения выглядело бы как нажатие пользователем и запускало бы сборку
	# списка моделей, которого ещё нет.
	_api_detail_free.button_pressed = keep_free
	_api_detail_free.toggled.connect(_on_api_detail_free)
	if T:
		T.style_button(_api_detail_free, "success", false)
	row.add_child(_api_detail_free)
	# Обновление списка ИМЕННО ЭТОГО провайдера — иконкой без подписи: нужно оно
	# в одном случае из двадцати (сразу после сохранения ключа), а подпись
	# «Обновить список» рядом с полем фильтра и переключателем занимала бы
	# третье место в строке и переносила её на вторую.
	var refresh := Button.new()
	refresh.tooltip_text = _t("api_models_refresh")
	refresh.pressed.connect(_on_api_detail_models_refresh)
	if T:
		T.style_icon_button(refresh, ["Reload", "Loop"], _t("api_models_refresh"))
	row.add_child(refresh)

	_api_detail_models = VBoxContainer.new()
	_api_detail_models.size_flags_horizontal = SIZE_EXPAND_FILL
	_api_detail_models.add_theme_constant_override("separation", 2)
	_api_detail.add_child(_api_detail_models)
	_api_detail_rebuild_models()


func _on_api_detail_filter(_text: String) -> void:
	_api_detail_rebuild_models()


func _on_api_detail_free(_pressed: bool) -> void:
	_api_detail_rebuild_models()


# Список моделей показывается ЦЕЛИКОМ: у OpenRouter их триста с лишним, и
# ограничение в шестьдесят строк отвечало не на тот вопрос. Человек, открывший
# провайдера, хочет знать, что у него есть; «показано 60 из 312» заставляет
# угадывать, что скрыто в остальных двухсот пятидесяти. Прокрутка справа своя, а
# сузить список есть чем — поле фильтра стоит прямо над ним.
func _api_detail_rebuild_models() -> void:
	if _api_detail_models == null or not is_instance_valid(_api_detail_models):
		return
	_clear_container(_api_detail_models)
	# Провайдер берётся из того, ДЛЯ КОГО собрана правая половина, а не из
	# выбранной строки: нажатие на другую строку пересобирает половину целиком, и
	# к моменту вызова отсюда эти два значения всегда совпадают, — но опираться
	# надо на то, что относится к самому списку моделей.
	var pid := _api_detail_built_for
	var rec := _api_provider_rec(pid)
	# Недоступного провайдера показываем целиком, но выбрать у него нельзя
	# ничего — ни его самого, ни модель: запрос всё равно не уйдёт.
	var blocked := str(rec.get("unavailable", "")) != ""
	var all := _api_detail_model_source(rec)
	var found := _api_detail_filtered(all)
	if _api_detail_cap and is_instance_valid(_api_detail_cap):
		# В подписи — число ПОКАЗАННЫХ, то есть подошедших под фильтр: она стоит
		# прямо над списком и должна совпадать с тем, что под ней. Сколько их
		# всего у провайдера — в подсказке: иначе с включённым фильтром подпись
		# «Модели провайдера: 312» стояла бы над тремя строками.
		_api_detail_cap.text = _t("api_pick_models_all") % found.size()
		_api_detail_cap.tooltip_text = _t("api_pick_models_all") % all.size()
		_api_detail_cap.mouse_filter = Control.MOUSE_FILTER_STOP
	if all.is_empty():
		# Пустой список объясняется словами: пустое место под подписью «Модели
		# провайдера: 0» читается как «у него их нет», а это неправда — их просто
		# ещё не спрашивали, и спросить можно только с сохранённым ключом.
		_api_hint(_api_detail_models, _t("api_pick_models_empty"))
		return
	if found.is_empty():
		_api_hint(_api_detail_models, _t("api_pick_models_no_match"))
		return
	var T = _T()
	for m_any in found:
		var m: Dictionary = m_any
		var mid := str(m.get("id", ""))
		var btn := Button.new()
		# Пометка «бесплатная» — в ПОДПИСИ, а сам идентификатор уходит в выбор
		# отдельным аргументом: приклеенная к имени пометка означала бы запрос к
		# провайдеру с несуществующей моделью.
		btn.text = _api_model_caption(m)
		btn.tooltip_text = _api_model_tip(mid, m)
		btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		# ЗДЕСЬ clip_text МОЖНО и нужно: строки лежат в VBox на всю ширину
		# половины, а не в HFlowContainer, который раскладывал бы их по
		# наименьшей ширине и превратил бы в огрызки. Полное имя — в подсказке.
		btn.clip_text = true
		btn.size_flags_horizontal = SIZE_EXPAND_FILL
		btn.custom_minimum_size = Vector2(0, API_PICK_ROW_HEIGHT)
		# У недоступного провайдера модель тоже не выбрать: запрос всё равно не
		# уйдёт, а «выбрал и не работает» выглядит поломкой плагина.
		btn.disabled = blocked
		if not blocked:
			# Нажатие выбирает СРАЗУ и провайдера, и модель: человек искал
			# именно модель, и заставлять его после выбора провайдера искать её
			# ещё раз в выпадающем списке формы значит проделать ту же работу
			# дважды.
			btn.pressed.connect(_on_api_pick_choose.bind(pid, mid))
		if T:
			# Зелёным — только то, что бесплатно ПО ОТВЕТУ ПРОВАЙДЕРА. Каталог
			# говорит о мире, а не об этом ключе, и красить его утверждение так
			# же значило бы обещать бесплатность за чужой справочник: пометка
			# словами у такой модели есть, а цвета «точно бесплатно» — нет.
			# Снятая с обслуживания приглушается независимо от бесплатности: её
			# могут убрать в любой момент, а модель закрепляется за чатом.
			var tone := "neutral"
			if blocked or bool(m.get("deprecated", false)):
				tone = "dim"
			elif bool(m.get("free", false)):
				tone = "success"
			T.style_button(btn, tone, false)
		_api_detail_models.add_child(btn)


func _api_detail_model_source(rec: Dictionary) -> Array:
	# Откуда берутся модели провайдера, в порядке доверия.
	#
	# 1) models_index — списки ВСЕХ провайдеров, какие известны серверу. Он
	#    приходит с обходом и не отфильтрован флажком «только бесплатные», то
	#    есть годится и для поиска платных моделей.
	# 2) _api_fetched_models — ответ на кнопку «Обновить список» в форме. Может
	#    быть отфильтрован, зато свежее.
	# 3) rec.models — зашитый в реестр перечень. У большинства провайдеров он
	#    пуст намеренно (идентификаторы меняются слишком часто), но там, где он
	#    есть, показать его обязательно: про эти модели плагин знает без сети.
	var pid := str(rec.get("id", ""))
	var src = _api_model_index.get(pid, [])
	if typeof(src) != TYPE_ARRAY or (src as Array).is_empty():
		src = _api_fetched_models.get(pid, [])
	if typeof(src) != TYPE_ARRAY or (src as Array).is_empty():
		src = rec.get("models", [])
	if typeof(src) != TYPE_ARRAY:
		return []
	return src


func _api_detail_filtered(source: Array) -> Array:
	var query := ""
	if _api_detail_filter and is_instance_valid(_api_detail_filter):
		query = _api_detail_filter.text.strip_edges().to_lower()
	var free_only := false
	if _api_detail_free and is_instance_valid(_api_detail_free):
		free_only = _api_detail_free.button_pressed
	var out: Array = []
	for m in source:
		var rec: Dictionary = {}
		if typeof(m) == TYPE_DICTIONARY:
			# Запись передаётся ЦЕЛИКОМ, а не пересобирается из id и free: кроме
			# них она несёт дополнения каталога models.dev (цена, окно контекста,
			# tool_call, catalog_free), и пересборка молча теряла бы их —
			# подсказка на строке модели осталась бы пустой.
			rec = m
		else:
			rec = {"id": str(m), "free": false}
		var mid := str(rec.get("id", ""))
		if mid == "":
			continue
		if query != "" and not mid.to_lower().contains(query):
			continue
		# ОБА ИСТОЧНИКА БЕСПЛАТНОСТИ. free измерен по ответу провайдера,
		# catalog_free — по справочнику models.dev, и они расходятся: у Opencode
		# Zen модель big-pickle бесплатна по каталогу и платная по суффиксу в
		# имени (замерено). Отбирать только по первому значило бы прятать модели,
		# которые могут оказаться бесплатными, — а именно их и ищут этой
		# кнопкой. Откуда сведения, написано на самой строке.
		if free_only and not bool(rec.get("free", false)) \
				and not bool(rec.get("catalog_free", false)):
			continue
		out.append(rec)
	return out


func _api_model_caption(m: Dictionary) -> String:
	# Подпись на кнопке модели: идентификатор + пометка С ИМЕНЕМ ИСТОЧНИКА.
	# «бесплатная» — это ответ самого провайдера (суффикс :free/-free или нулевая
	# цена в его pricing), «бесплатная по каталогу» — запись в справочнике
	# models.dev. Разница не в формулировке: числа расходятся (замерено — у
	# Opencode Zen модель big-pickle бесплатна по каталогу и платная по суффиксу),
	# и обещать бесплатность за чужой справочник, не сказав, что это он, значит
	# переложить на пользователя чужую ошибку.
	var mid := str(m.get("id", ""))
	if bool(m.get("deprecated", false)):
		# СНЯТИЕ ВАЖНЕЕ БЕСПЛАТНОСТИ. Модель закрепляется за чатом и потом не
		# меняется, поэтому «её вот-вот уберут» человек обязан увидеть до
		# нажатия, а не в подсказке при наведении. Замерено, что это не
		# гипотетический случай: у Opencode Zen 29 записей из 91 помечены
		# снятыми (правда, живой /models их уже и не отдаёт).
		return _t("api_model_retired") % mid
	if bool(m.get("free", false)):
		return _t("api_model_free") % mid
	if bool(m.get("catalog_free", false)):
		return _t("api_model_free_catalog") % mid
	return mid


func _api_src(m: Dictionary, field: String) -> String:
	# Кто сообщил это число: сам провайдер или справочник. Сервер присылает
	# список полей, которые ДОПИСАЛ каталог (from_catalog); всё остальное пришло
	# из живого ответа провайдера.
	#
	# ЗАЧЕМ ТАК ТОЧНО. Без этого разделения подпись «по каталогу models.dev»
	# встала бы и под живой ценой OpenRouter — а она точнее: замерено, что у
	# moonshotai/kimi-k2.6 каталог отстал и показывал 0.95/4.0 против живых
	# 0.646/2.72, то есть завышал на 47%.
	var from_cat = m.get("from_catalog", [])
	if typeof(from_cat) == TYPE_ARRAY and (from_cat as Array).has(field):
		return _t("api_src_catalog")
	return _t("api_src_live")


func _api_model_tip(mid: String, m: Dictionary) -> String:
	# Подсказка на кнопке модели: что о ней известно и ОТКУДА — у каждой строки
	# свой источник, потому что цену провайдер может присылать сам, а окно
	# контекста нет (или наоборот).
	var lines: Array = []
	lines.append(_t("api_pick_model_tip") % mid)
	if bool(m.get("deprecated", false)):
		lines.append(_t("api_model_deprecated"))
	else:
		var status := str(m.get("status", ""))
		if status != "":
			lines.append(_t("api_model_beta") % status)
	var ctx := int(m.get("context", 0))
	if ctx > 0:
		lines.append(_t("api_model_context") % [_api_thousands(ctx), _api_src(m, "context")])
	var mout := int(m.get("max_output", 0))
	if mout > 0:
		lines.append(_t("api_model_output") % [_api_thousands(mout), _api_src(m, "max_output")])
	if m.has("cost_in") and m.has("cost_out"):
		lines.append(_t("api_model_cost") % [_api_price(float(m["cost_in"])), _api_price(float(m["cost_out"])), _api_src(m, "cost_in")])
	if m.has("tool_call"):
		# ЭТО НЕ ПРО ВОЗМОЖНОСТИ АГЕНТА. tool_call означает родной function
		# calling провайдера, а плагин его КАТЕГОРИЧЕСКИ не использует: действия
		# приходят JSON-блоком ```agent_action в обычном тексте ответа (так
		# написано и в самом мега-промпте). Поэтому «нет function calling» не
		# мешает модели ни читать файлы, ни менять сцену — и подпись обязана это
		# говорить прямо. Иначе строка отпугивает от рабочих моделей, а следующий
		# читатель кода добавит по ней предупреждение, которого быть не должно.
		var src := _api_src(m, "tool_call")
		lines.append((_t("api_model_tools") % src) if bool(m["tool_call"]) else (_t("api_model_no_tools") % src))
	return "\n".join(lines)


func _api_thousands(n: int) -> String:
	# Разряды через пробел. «262144» глазами не читается, а сравнивают окна
	# контекста именно по порядку величины — значит разряды нужны.
	var s := str(absi(n))
	var out := ""
	var seen := 0
	for i in range(s.length() - 1, -1, -1):
		out = s.substr(i, 1) + out
		seen += 1
		if seen % 3 == 0 and i > 0:
			out = " " + out
	return ("-" + out) if n < 0 else out


func _api_price(value: float) -> String:
	# Цена за миллион токенов без лишних нулей. У дешёвых моделей значащие
	# знаки далеко после запятой (0.02 и меньше), у дорогих дробной части нет
	# вовсе — и «30.000000» рядом с ней читается как опечатка.
	var s := "%.6f" % value
	while s.ends_with("0"):
		s = s.substr(0, s.length() - 1)
	if s.ends_with("."):
		s = s.substr(0, s.length() - 1)
	return s if s != "" else "0"


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
	# Сколько моделей у сервиса ПО КАТАЛОГУ — единственное, что известно про
	# каталожную запись до сохранения ключа: живой список у неё не спрашивают.
	#
	# ЧЕГО ЗДЕСЬ БОЛЬШЕ НЕТ. Пометки «из каталога, не проверен» и «живьём не
	# проверялся» стояли у всех подряд: первая — у ста пятидесяти восьми записей
	# из ста шестидесяти пяти, вторая — вообще у всех, потому что живого прогона
	# с настоящим ключом не было ни у кого. Пометка, которая есть у всех, не
	# различает никого: она просто удлиняла ряд на две плашки и переносила его на
	# вторую строку. То, что каталожные записи не разобраны руками, теперь
	# сказано один раз — названием группы, в которой они лежат.
	if bool(rec.get("from_catalog", false)):
		var n := int(rec.get("catalog_models", 0))
		if n > 0:
			out.append({"text": _t("api_badge_catalog_models") % n, "tone": "dim"})
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
	# ВТОРОЕ МНЕНИЕ О ТЕХ ЖЕ МОДЕЛЯХ — отдельной фразой и с названием источника.
	# Числа расходятся не от ошибки: наша эвристика судит по ответу провайдера
	# (суффикс :free/-free, нулевая цена в pricing), каталог — по своей записи о
	# модели. Замерено: у Opencode Zen модель big-pickle бесплатна по каталогу и
	# платная по суффиксу. Показываем ТОЛЬКО при расхождении: совпавшие числа —
	# это два одинаковых предложения подряд, то есть шум, а расхождение как раз
	# и есть то, из-за чего провайдер мог попасть под фильтр «с бесплатными».
	var free_cat := int(stats.get("models_free_catalog", -1))
	if free_cat >= 0 and free_cat != free:
		parts.append(_t("api_stats_free_catalog") % free_cat)
	# Неудачная попытка получить список — ОТДЕЛЬНОЙ строкой, а не вместо чисел:
	# список, полученный вчера, полезнее пустоты, а сегодняшний отказ объясняет,
	# почему числа не обновились. «Список ещё не загружался» на провайдере, к
	# которому мы сходили и получили 401, выглядело бы как бездействие плагина.
	var err := str(stats.get("models_error", ""))
	if err != "":
		var e_when := _api_ago(float(stats.get("models_try_at", 0.0)))
		if e_when == "":
			parts.append(_t("api_stats_models_error") % err)
		else:
			parts.append(_t("api_stats_models_error_at") % [err, e_when])
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


func _on_api_pick_choose(pid: String, model: String = "") -> void:
	if pid == "":
		return
	_api_selected_provider = pid
	_api_filling = true
	_api_fill_provider_fields()
	_api_filling = false
	# Модель ставим ПОСЛЕ заполнения полей: _api_fill_provider_fields() берёт её
	# из ответа сервера, то есть прежнюю, и порядок наоборот стёр бы только что
	# выбранное. На сервер она уходит тем же сохранением ниже.
	if model != "":
		_api_model = model
		if _api_model_state:
			_api_model_state.text = _t("api_model_current") % model
			_api_model_state.add_theme_color_override("font_color", _color("dim"))
	if _api_pick_dialog and is_instance_valid(_api_pick_dialog):
		_api_pick_dialog.hide()
	# Выбор запоминается на сервере как провайдер по умолчанию. Иначе он жил бы
	# только до закрытия панели: после перезапуска редактора экран снова
	# открывался бы на прежнем провайдере, хотя человек уже выбрал другой, — и
	# выбор пришлось бы делать заново каждый раз.
	var save := {"provider": pid, "make_default": true}
	if model != "":
		save["model"] = model
	api_settings_save_requested.emit(save)


func _on_api_test() -> void:
	var pid := _api_current_provider()
	if pid == "":
		return
	if _api_test_state:
		_api_test_state.text = _t("api_test_running")
		_api_test_state.add_theme_color_override("font_color", _color("dim"))
	api_test_requested.emit(
		pid, _api_model)


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
		pid, _api_model)


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
	# Списки моделей обновляются УЖЕ ЗДЕСЬ, а не только при открытии списка
	# провайдеров: обход занимает несколько секунд, и если начать его в момент
	# открытия окна, человек успеет посмотреть на список с пустыми числами и
	# сделать неверный вывод раньше, чем придут настоящие. Кого спрашивать и не
	# пора ли — решает сервер по возрасту данных, поэтому лишних запросов к
	# провайдерам этот вызов не создаёт.
	_api_request_scan()


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
