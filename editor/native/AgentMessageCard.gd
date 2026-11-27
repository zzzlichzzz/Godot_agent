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
var _prose_length: int = 0
var _payload_toggle: Button
var _payload_text: RichTextLabel

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
	_apply_locale()
	_setup_theme()
	if not copy_btn.pressed.is_connected(_on_copy_pressed):
		copy_btn.pressed.connect(_on_copy_pressed)
	if rollback_btn and not rollback_btn.pressed.is_connected(_on_rollback_pressed):
		rollback_btn.pressed.connect(_on_rollback_pressed)
	if not expand_btn.pressed.is_connected(_on_expand_pressed):
		expand_btn.pressed.connect(_on_expand_pressed)
	for button in [copy_btn, expand_btn, rollback_btn]:
		button.modulate.a = 1.0
		button.mouse_filter = Control.MOUSE_FILTER_STOP
		button.focus_mode = Control.FOCUS_ALL
		button.disabled = false
	rollback_btn.hide()


func _apply_locale() -> void:
	# Подпись автора и надпись кнопки сворачивания лежат в .tscn по-русски и
	# остаются на экране, пока код их не перепишет. У «ИИ-Агент» этого не делал
	# никто, а «Свернуть» переписывалось только при обновлении содержимого —
	# то есть на английском языке в шапке карточки оставался русский текст.
	name_label.text = _t("agent_name")
	copy_btn.tooltip_text = _t("copy")
	expand_btn.text = _t("collapse") if _is_expanded else _t("expand")


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
	$Row/Spacer.hide()  # Ответ читается как документ: вся ширина дока отдана тексту.

	var agent_icon: Texture2D = T.first_icon(["Godot", "Script"])
	if agent_icon != null:
		avatar.texture = agent_icon
		avatar.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		avatar.modulate = Color.WHITE
		avatar.visible = true
	else:
		avatar.visible = false

	name_label.add_theme_color_override("font_color", T.color("text"))
	name_label.add_theme_stylebox_override("normal", T.make_panel_style(T.alpha("accent", 0.12), Color.TRANSPARENT, T.px(4), T.px(6), T.px(2)))
	$Row/MessageBox.add_theme_constant_override("separation", T.px(7))
	status_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	status_label.add_theme_color_override("font_color", T.color("dim"))

	# style_rich_text ставит fit_content/scroll_active/цвета: без fit_content
	# RichTextLabel внутри контейнера получает нулевую высоту и текст не виден.
	T.style_rich_text(content)
	content.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.add_theme_constant_override("line_separation", T.px(3))
	content.add_theme_color_override("table_odd_row_bg", Color(0, 0, 0, 0.15))

	T.style_icon_button(copy_btn, ["ActionCopy"], "⧉")
	copy_btn.tooltip_text = _t("copy")
	# Откат: иконка «отменить» из темы редактора, запасной вариант — символ.
	if rollback_btn:
		T.style_icon_button(rollback_btn, ["UndoRedo", "Undo", "Reload"], "⟲", "warning")
		rollback_btn.tooltip_text = _t("msg_rollback_tip")
	expand_btn.custom_minimum_size = copy_btn.custom_minimum_size


func setup(text: String, _time_str: String = "") -> void:
	_full_text = text
	content.text = _T().answer_markup(_present_answer(text), content.get_theme_font_size("normal_font_size"))
	_prose_length = content.text.length()
	_is_expanded = true
	_refresh_collapse_state()


func _present_answer(text: String) -> String:
	# Presentation only. Keep the verbatim response for history and copying. Never dispatch JSON here.
	if _payload_toggle:
		_payload_toggle.set_pressed_no_signal(false)
		_payload_toggle.hide()
		_payload_text.hide()
		_payload_text.text = ""
	var trimmed := text.rstrip(" \n\r\t")
	if not trimmed.ends_with("}"): return text
	var split := trimmed.rfind("\n")
	if split < 1 or trimmed.length() - split > 8192: return text
	var body := trimmed.left(split).rstrip(" \r\n\t")
	if body.is_empty() or body.count("```") % 2 or body.count("[code]") != body.count("[/code]"): return text
	var raw := trimmed.substr(split + 1).strip_edges().replace("[rb]", "]").replace("[lb]", "[")
	if not raw.begins_with("{"): return text
	var json := JSON.new()
	if json.parse(raw) != OK or not (json.data is Dictionary): return text
	var kind = json.data.get("action", null)
	if not (kind is String) or kind.length() > 64 or not kind.is_valid_ascii_identifier(): return text
	if not _payload_toggle: _build_disclosure()
	var english: bool = _locale_script != null and _locale_script.get_lang() == "en"
	_payload_toggle.text = ("Tool request" if english else "Запрос инструмента")
	_payload_toggle.tooltip_text = kind
	_payload_text.text = raw
	_payload_open(false)
	_payload_toggle.show()
	return body


func _build_disclosure() -> void:
	var T = _T()
	var box = $Row/MessageBox
	_payload_toggle = Button.new()
	_payload_toggle.name = "PayloadToggle"
	_payload_toggle.toggle_mode = true
	_payload_toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	T.style_button(_payload_toggle, "dim")
	box.add_child(_payload_toggle)
	_payload_text = RichTextLabel.new()
	_payload_text.name = "PayloadText"
	T.style_rich_text(_payload_text, true)
	_payload_text.bbcode_enabled = false
	_payload_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_payload_text.add_theme_stylebox_override("normal", T.panel_style("code"))
	box.add_child(_payload_text)
	_payload_toggle.toggled.connect(_payload_open)


func _payload_open(open: bool) -> void:
	_payload_text.visible = open
	_payload_toggle.icon = _T().first_icon(["GuiTreeArrowDown"] if open else ["GuiTreeArrowRight"])


func append_text(delta: String) -> void:
	if delta == "":
		return
	_full_text += delta
	_prose_length += delta.length()
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
	var need_collapse := _prose_length > COLLAPSE_THRESHOLD
	expand_btn.visible = need_collapse
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
		expand_btn.tooltip_text = _t("collapse")
		_T().style_icon_button(expand_btn, ["Collapse", "GuiTreeArrowDown"], "−")
	else:
		content.fit_content = false
		content.clip_contents = true
		content.custom_minimum_size.y = _T().px(int(COLLAPSED_HEIGHT))
		expand_btn.tooltip_text = _t("expand")
		_T().style_icon_button(expand_btn, ["Expand", "GuiTreeArrowRight"], "+")


func _on_copy_pressed() -> void:
	# Копируем видимый текст без BBCode-разметки.
	DisplayServer.clipboard_set(_copy_text())


func _copy_text() -> String:
	var plain := content.get_parsed_text()
	return plain + "\n" + _payload_text.text if _payload_toggle and _payload_toggle.visible else plain


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
	rollback_btn.disabled = not available


func _on_expand_pressed() -> void:
	_is_expanded = not _is_expanded
	_apply_expand_state()


func get_text() -> String:
	return _full_text
