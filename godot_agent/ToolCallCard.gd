@tool
extends PanelContainer
class_name ToolCallCard

@onready var root_vbox: VBoxContainer = $RootVBox
@onready var header: HBoxContainer = $RootVBox/Header
@onready var tool_icon: TextureRect = $RootVBox/Header/ToolIcon
@onready var title_label: Label = $RootVBox/Header/TitleLabel
@onready var toggle_btn: Button = $RootVBox/Header/ToggleButton
@onready var content_box: VBoxContainer = $RootVBox/ContentBox
@onready var params_label: RichTextLabel = $RootVBox/ContentBox/ParamsLabel

var _expanded: bool = true


func _tc(theme_item: StringName, theme_type: StringName, fallback: Color) -> Color:
	if has_theme_color(theme_item, theme_type):
		return get_theme_color(theme_item, theme_type)
	return fallback


func _ti(theme_item: StringName) -> Texture2D:
	if has_theme_icon(theme_item, "EditorIcons"):
		return get_theme_icon(theme_item, "EditorIcons")
	return null


func _ready() -> void:
	_setup_theme()
	if not toggle_btn.pressed.is_connected(_on_toggle):
		toggle_btn.pressed.connect(_on_toggle)


func _setup_theme() -> void:
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = _tc("dark_color_2", "Editor", Color("#232333"))
	panel_style.border_color = _tc("contrast_color_1", "Editor", Color("#3a4a63"))
	panel_style.set_border_width_all(1)
	panel_style.set_corner_radius_all(6)
	panel_style.content_margin_left = 10
	panel_style.content_margin_right = 10
	panel_style.content_margin_top = 6
	panel_style.content_margin_bottom = 6
	add_theme_stylebox_override("panel", panel_style)

	title_label.add_theme_color_override("font_color", _tc("font_color", "Label", Color.WHITE))

	params_label.add_theme_color_override("default_color", _tc("code_font_color", "CodeEdit", Color("#8ab4f8")))
	params_label.add_theme_color_override("selection_color", _tc("accent_color", "Editor", Color("#ffd54f")))
	params_label.bbcode_enabled = true
	params_label.context_menu_enabled = true
	params_label.selection_enabled = true
	# Без fit_content параметры инструмента обрезались фиксированной высотой.
	params_label.fit_content = true
	params_label.scroll_active = false
	params_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART


func setup(tool_name: String, params: Dictionary) -> void:
	# Иконка — отдельным TextureRect: Label не умеет рисовать Texture2D,
	# поэтому раньше в заголовок попадал результат and/or (bool).
	var icon := _ti(_icon_for_tool(tool_name))
	if icon != null:
		tool_icon.texture = icon
		tool_icon.visible = true
		title_label.text = tool_name
	else:
		tool_icon.visible = false
		title_label.text = "%s %s" % [_emoji_for_tool(tool_name), tool_name]
	params_label.text = _format_params(params)
	_apply_expand_state()


func _icon_for_tool(tool_name: String) -> StringName:
	match tool_name.to_lower():
		"read_file", "read":
			return "File"
		"write_file", "write", "edit_file", "edit":
			return "Script"
		"list_files", "list", "glob":
			return "Folder"
		"run_command", "exec", "terminal":
			return "Play"
		"search", "grep":
			return "Search"
		_:
			return "Tools"


func _emoji_for_tool(tool_name: String) -> String:
	match tool_name.to_lower():
		"read_file", "read":
			return "📄"
		"write_file", "write", "edit_file", "edit":
			return "📝"
		"list_files", "list", "glob":
			return "📁"
		"run_command", "exec", "terminal":
			return "💻"
		"search", "grep":
			return "🔍"
		_:
			return "🔧"


func _format_params(params: Dictionary) -> String:
	var accent := _tc("accent_color", "Editor", Color("#ffd54f")).to_html(false)
	var result := ""
	for key in params:
		var val: String = str(params[key])
		result += "[color=#%s]%s[/color]: %s\n" % [accent, _escape_bbcode(str(key)), _escape_bbcode(val)]
	return result


func _escape_bbcode(text: String) -> String:
	var result := ""
	for i in range(text.length()):
		var c = text[i]
		if c == "[":
			result += "[lb]"
		elif c == "]":
			result += "[rb]"
		else:
			result += c
	return result


func _on_toggle() -> void:
	_expanded = not _expanded
	_apply_expand_state()


func _apply_expand_state() -> void:
	content_box.visible = _expanded
	# У Button нет свойства icon_rotation — берём две разные иконки темы.
	var icon := _ti("GuiTreeArrowDown") if _expanded else _ti("GuiTreeArrowRight")
	if icon != null:
		toggle_btn.icon = icon
		toggle_btn.text = ""
	else:
		toggle_btn.text = "▾" if _expanded else "▸"
