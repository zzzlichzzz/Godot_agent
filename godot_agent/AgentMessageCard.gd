@tool
extends PanelContainer
class_name AgentMessageCard

@onready var content: RichTextLabel = $Row/MessageBox/Content
@onready var name_label: Label = $Row/MessageBox/Header/NameLabel
@onready var status_label: Label = $Row/MessageBox/Header/StatusLabel
@onready var avatar: TextureRect = $Row/MessageBox/Header/Avatar
@onready var copy_btn: Button = $Row/MessageBox/Header/CopyButton
@onready var expand_btn: Button = $Row/MessageBox/Header/ExpandButton
@onready var tool_calls_container: VBoxContainer = $Row/MessageBox/ToolCallsContainer

# Кнопка отката создаётся КОДОМ, а не в .tscn — намеренно.
# Карточка помечена @tool: когда её сцена открыта во вкладке редактора,
# _ready() отрабатывает прямо в редакторе, присваивает иконки и шрифты из
# темы, и Godot запекает их в .tscn при сохранении (так сцена однажды
# распухла с 4 КБ до 3 МБ). Узлы, созданные кодом, в файл не попадают.
var rollback_btn: Button = null

# Порог, после которого длинный ответ схлопывается до COLLAPSED_HEIGHT.
const COLLAPSE_THRESHOLD := 1200
const COLLAPSED_HEIGHT := 260.0

var _full_text: String = ""
var _is_expanded: bool = true
var _needs_collapse: bool = false

# Откат ИМЕННО ТОГО изменения, о котором сообщает эта карточка.
# Саму логику отката карточка не знает: только просит, а подтверждение и
# запрос на сервер делает agent_panel (см. agent_chat_view.add_agent_message).
#
# Сигнал несёт адрес записи журнала. Раньше он был пустым, и панель могла
# попросить только «откатить последнее» — кнопка на любом облачке отменяла
# самое свежее изменение проекта, а не своё. Пустой адрес = кнопки нет.
signal rollback_requested(entry_id: String)

# Адрес записи журнала изменений (history_manager). Пустая строка означает,
# что этой карточке нечего откатывать: обычный текстовый ответ без действий
# или восстановленное из архива сообщение, чей адрес не сохранён.
var rollback_entry_id: String = ""


# Цвета, иконки и стили — единый модуль agent_theme.gd (см. _T()).
static var _theme_script = null
static var _locale_script = null


func _T():
	# Путь считается от расположения скрипта, чтобы аддон работал из любой папки.
	if _theme_script == null:
		var sc := get_script() as Script
		if sc:
			var p := sc.resource_path.get_base_dir() + "/agent_theme.gd"
			if FileAccess.file_exists(p):
				_theme_script = load(p)
	return _theme_script


func _t(key: String) -> String:
	if _locale_script == null:
		var sc := get_script() as Script
		if sc:
			var p := sc.resource_path.get_base_dir() + "/agent_locale.gd"
			if FileAccess.file_exists(p):
				_locale_script = load(p)
	if _locale_script:
		return _locale_script.t(key)
	return key


func _ready() -> void:
	_ensure_rollback_button()
	_setup_theme()
	if not copy_btn.pressed.is_connected(_on_copy_pressed):
		copy_btn.pressed.connect(_on_copy_pressed)
	if rollback_btn and not rollback_btn.pressed.is_connected(_on_rollback_pressed):
		rollback_btn.pressed.connect(_on_rollback_pressed)
	if not expand_btn.pressed.is_connected(_on_expand_pressed):
		expand_btn.pressed.connect(_on_expand_pressed)
	if not mouse_entered.is_connected(_show_actions):
		mouse_entered.connect(_show_actions)
	if not mouse_exited.is_connected(_hide_actions):
		mouse_exited.connect(_hide_actions)
	_set_actions_shown(false)


func _ensure_rollback_button() -> void:
	# Создаём кнопку рядом с «Копировать» (слева от неё) — см. комментарий
	# у объявления rollback_btn о том, почему не в .tscn.
	if rollback_btn != null and is_instance_valid(rollback_btn):
		return
	var header := copy_btn.get_parent()
	if header == null:
		return
	rollback_btn = Button.new()
	rollback_btn.name = "RollbackButton"
	rollback_btn.custom_minimum_size = Vector2(22, 22)
	rollback_btn.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	rollback_btn.focus_mode = Control.FOCUS_NONE
	rollback_btn.flat = true
	rollback_btn.modulate.a = 0.0
	rollback_btn.disabled = true
	header.add_child(rollback_btn)
	header.move_child(rollback_btn, copy_btn.get_index())


func _setup_theme() -> void:
	var T = _T()
	if T == null:
		return
	# Сцена открыта во вкладке редактора — не трогаем оформление, иначе Godot
	# запечёт иконки и шрифты в .tscn при сохранении (см. is_edited_scene).
	if T.is_edited_scene(self):
		return
	add_theme_stylebox_override("panel", T.panel_style("agent"))

	var accent: Color = T.color("accent")
	var agent_icon: Texture2D = T.first_icon(["Node", "Script"])
	if agent_icon != null:
		avatar.texture = agent_icon
		avatar.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		avatar.modulate = accent
		avatar.visible = true
	else:
		avatar.visible = false

	name_label.add_theme_color_override("font_color", accent)
	status_label.add_theme_color_override("font_color", T.color("dim"))

	# style_rich_text ставит fit_content/scroll_active/цвета: без fit_content
	# RichTextLabel внутри контейнера получает нулевую высоту и текст не виден.
	T.style_rich_text(content)
	content.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.add_theme_color_override("table_odd_row_bg", Color(0, 0, 0, 0.15))

	T.style_icon_button(copy_btn, ["ActionCopy"], "⧉")
	copy_btn.tooltip_text = _t("copy")
	# Откат: иконка «отменить» из темы редактора, запасной вариант — символ.
	if rollback_btn:
		T.style_icon_button(rollback_btn, ["UndoRedo", "Undo", "Reload"], "⟲", "warning")
		rollback_btn.tooltip_text = _t("msg_rollback_tip")
	T.style_button(expand_btn, "dim")


func setup(text: String, _time_str: String = "") -> void:
	_full_text = text
	content.text = text
	_refresh_collapse_state()


func append_text(delta: String) -> void:
	if delta == "":
		return
	_full_text += delta
	# append_text дописывает инкрементально: полный re-parse BBCode на каждый чанк
	# стрима подвешивал панель на длинных ответах.
	content.append_text(delta)
	_refresh_collapse_state()


func set_status(status: String) -> void:
	status_label.text = status
	status_label.visible = status != ""


func add_tool_call(tool_name: String, params: Dictionary) -> void:
	var tool_card: ToolCallCard = null
	var sc := get_script() as Script
	if sc:
		var tp := sc.resource_path.get_base_dir() + "/ToolCallCard.tscn"
		if FileAccess.file_exists(tp):
			var packed := load(tp) as PackedScene
			if packed:
				tool_card = packed.instantiate() as ToolCallCard
	if tool_card == null:
		return
	tool_calls_container.add_child(tool_card)
	tool_card.setup(tool_name, params)
	tool_calls_container.visible = true


func _refresh_collapse_state() -> void:
	# Кнопка «Развернуть» нужна только длинным ответам.
	var need_collapse := _full_text.length() > COLLAPSE_THRESHOLD
	_needs_collapse = need_collapse
	# Видимость и прозрачность кнопок держит _set_actions_shown: если выставить
	# visible здесь, во время стрима кнопка проступит без наведения.
	_set_actions_shown(copy_btn.modulate.a > 0.5)
	if not need_collapse:
		content.custom_minimum_size.y = 0
		content.clip_contents = false
		content.fit_content = true
		return
	_apply_expand_state()


func _apply_expand_state() -> void:
	if _is_expanded:
		content.fit_content = true
		content.clip_contents = false
		content.custom_minimum_size.y = 0
		expand_btn.text = _t("collapse")
	else:
		content.fit_content = false
		content.clip_contents = true
		content.custom_minimum_size.y = COLLAPSED_HEIGHT
		expand_btn.text = _t("expand")


func _on_copy_pressed() -> void:
	# Копируем видимый текст без BBCode-разметки.
	DisplayServer.clipboard_set(content.get_parsed_text())


func _on_rollback_pressed() -> void:
	# Подтверждение и сам откат делает agent_panel — карточка только просит,
	# но обязательно указывает, ЧТО откатывать.
	rollback_requested.emit(rollback_entry_id)


func set_rollback_target(entry_id: String) -> void:
	# Кнопка отката появляется ТОЛЬКО у карточки, за которой стоит настоящее
	# изменение на диске. Раньше её получала каждая карточка агента, включая
	# обычный текстовый ответ, и нажатие откатывало последнее изменение
	# проекта — совсем не то, на что нажимал пользователь.
	rollback_entry_id = entry_id
	set_rollback_available(entry_id != "")


func set_rollback_available(available: bool) -> void:
	# Живой карточке (пока идёт стрим) откат не предлагаем: изменения ещё
	# не зафиксированы на сервере.
	if rollback_btn == null or not is_instance_valid(rollback_btn):
		return
	rollback_btn.visible = available
	if not available:
		rollback_btn.disabled = true


func _on_expand_pressed() -> void:
	_is_expanded = not _is_expanded
	_apply_expand_state()


func _set_actions_shown(shown: bool) -> void:
	# Кнопки всегда занимают своё место в шапке: прячем прозрачностью, а не
	# visible, иначе появление кнопки при наведении дёргает верстку карточки.
	var alpha := 1.0 if shown else 0.0
	var filter := Control.MOUSE_FILTER_STOP if shown else Control.MOUSE_FILTER_IGNORE
	copy_btn.modulate.a = alpha
	copy_btn.mouse_filter = filter
	copy_btn.disabled = not shown
	# Кнопка отката ведёт себя так же; visible ею управляет
	# set_rollback_available (у живой карточки её нет вовсе).
	if rollback_btn and is_instance_valid(rollback_btn) and rollback_btn.visible:
		rollback_btn.modulate.a = alpha
		rollback_btn.mouse_filter = filter
		rollback_btn.disabled = not shown
	# Кнопка сворачивания резервирует место только у длинных ответов.
	expand_btn.visible = _needs_collapse
	expand_btn.modulate.a = alpha
	expand_btn.mouse_filter = filter
	expand_btn.disabled = not shown


func _show_actions() -> void:
	_set_actions_shown(true)


func _hide_actions() -> void:
	if get_global_rect().has_point(get_global_mouse_position()):
		return
	_set_actions_shown(false)


func get_text() -> String:
	return _full_text
