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

# Порог, после которого длинный ответ схлопывается до COLLAPSED_HEIGHT.
const COLLAPSE_THRESHOLD := 1200
const COLLAPSED_HEIGHT := 260.0

var _full_text: String = ""
var _is_expanded: bool = true
var _needs_collapse: bool = false


# --- безопасное чтение темы редактора ---

func _tc(theme_item: StringName, theme_type: StringName, fallback: Color) -> Color:
	if has_theme_color(theme_item, theme_type):
		return get_theme_color(theme_item, theme_type)
	return fallback


func _tf(theme_item: StringName, theme_type: StringName) -> Font:
	if has_theme_font(theme_item, theme_type):
		return get_theme_font(theme_item, theme_type)
	return null


func _tfs(theme_item: StringName, theme_type: StringName, fallback: int) -> int:
	if has_theme_font_size(theme_item, theme_type):
		return get_theme_font_size(theme_item, theme_type)
	return fallback


func _ti(theme_item: StringName) -> Texture2D:
	if has_theme_icon(theme_item, "EditorIcons"):
		return get_theme_icon(theme_item, "EditorIcons")
	return null


func _ready() -> void:
	_setup_theme()
	if not copy_btn.pressed.is_connected(_on_copy_pressed):
		copy_btn.pressed.connect(_on_copy_pressed)
	if not expand_btn.pressed.is_connected(_on_expand_pressed):
		expand_btn.pressed.connect(_on_expand_pressed)
	if not mouse_entered.is_connected(_show_actions):
		mouse_entered.connect(_show_actions)
	if not mouse_exited.is_connected(_hide_actions):
		mouse_exited.connect(_hide_actions)
	_set_actions_shown(false)


func _setup_theme() -> void:
	var accent := _tc("accent_color", "Editor", Color("#ffd54f"))
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = _tc("dark_color_2", "Editor", Color("#26303d"))
	panel_style.border_color = Color(accent.r, accent.g, accent.b, 0.35)
	panel_style.set_border_width_all(1)
	panel_style.set_corner_radius_all(8)
	panel_style.content_margin_left = 12
	panel_style.content_margin_right = 12
	panel_style.content_margin_top = 8
	panel_style.content_margin_bottom = 8
	add_theme_stylebox_override("panel", panel_style)

	var agent_icon := _ti("Node")
	if agent_icon == null:
		agent_icon = _ti("Script")
	if agent_icon != null:
		avatar.texture = agent_icon
		avatar.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		avatar.modulate = accent
	else:
		avatar.visible = false

	name_label.add_theme_color_override("font_color", accent)
	status_label.add_theme_color_override("font_color", _tc("font_disabled_color", "Button", Color(0.6, 0.6, 0.6)))

	content.add_theme_color_override("default_color", _tc("font_color", "Label", Color.WHITE))
	content.add_theme_color_override("selection_color", accent)
	content.fit_content = true
	content.scroll_active = false
	content.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	# Моно-шрифт для блоков кода внутри ответа.
	var mono := _tf("font", "CodeEdit")
	if mono != null:
		content.add_theme_font_override("mono_font", mono)
	content.add_theme_font_size_override("mono_size", _tfs("font_size", "CodeEdit", 13))
	content.add_theme_color_override("table_odd_row_bg", Color(0, 0, 0, 0.15))

	var dim := _tc("font_disabled_color", "Button", Color(0.6, 0.6, 0.6))
	var copy_icon := _ti("ActionCopy")
	if copy_icon != null:
		copy_btn.icon = copy_icon
		copy_btn.text = ""
	else:
		copy_btn.text = "⧉"
	copy_btn.add_theme_color_override("font_color", dim)
	copy_btn.add_theme_color_override("icon_normal_color", dim)
	copy_btn.add_theme_color_override("icon_hover_color", accent)
	expand_btn.add_theme_color_override("font_color", dim)
	expand_btn.add_theme_color_override("font_hover_color", accent)


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
		expand_btn.text = "Свернуть"
	else:
		content.fit_content = false
		content.clip_contents = true
		content.custom_minimum_size.y = COLLAPSED_HEIGHT
		expand_btn.text = "Развернуть"


func _on_copy_pressed() -> void:
	# Копируем видимый текст без BBCode-разметки.
	DisplayServer.clipboard_set(content.get_parsed_text())


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
