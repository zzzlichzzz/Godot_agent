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


# Цвета, иконки и стили — единый модуль agent_theme.gd.
static var _theme_script = null


func _T():
	if _theme_script == null:
		var sc := get_script() as Script
		if sc:
			var p := sc.resource_path.get_base_dir() + "/agent_theme.gd"
			if FileAccess.file_exists(p):
				_theme_script = load(p)
	return _theme_script


func _ready() -> void:
	_setup_theme()
	if not toggle_btn.pressed.is_connected(_on_toggle):
		toggle_btn.pressed.connect(_on_toggle)


func _setup_theme() -> void:
	var T = _T()
	if T == null:
		return
	# Сцена открыта во вкладке редактора — оформление не применяем, иначе
	# Godot запечёт иконки и шрифты в .tscn при сохранении (см. is_edited_scene).
	if T.is_edited_scene(self):
		return
	add_theme_stylebox_override("panel", T.panel_style("tool"))
	title_label.add_theme_color_override("font_color", T.color("text"))

	# Без fit_content параметры инструмента обрезались фиксированной высотой.
	T.style_rich_text(params_label)
	params_label.add_theme_color_override("default_color", T.color("code_text"))
	params_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART


func setup(tool_name: String, params: Dictionary) -> void:
	# Иконка — отдельным TextureRect: Label не умеет рисовать Texture2D,
	# поэтому раньше в заголовок попадал результат and/or (bool).
	var T = _T()
	var icon: Texture2D = null
	if T:
		icon = T.icon(_icon_for_tool(tool_name))
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
	var T = _T()
	var accent: String = "ffd54f" if T == null else str(T.hex("accent"))
	var result := ""
	for key in params:
		var val: String = str(params[key])
		result += "[color=#%s]%s[/color]: %s\n" % [accent, _escape_bbcode(str(key)), _escape_bbcode(val)]
	return result


func _escape_bbcode(text: String) -> String:
	var T = _T()
	if T:
		return T.escape_bbcode(text)
	return text


func _on_toggle() -> void:
	_expanded = not _expanded
	_apply_expand_state()


func _apply_expand_state() -> void:
	content_box.visible = _expanded
	# У Button нет свойства icon_rotation — берём две разные иконки темы.
	var T = _T()
	var icon: Texture2D = null
	if T:
		icon = T.icon("GuiTreeArrowDown" if _expanded else "GuiTreeArrowRight")
	if icon != null:
		toggle_btn.icon = icon
		toggle_btn.text = ""
	else:
		toggle_btn.icon = null
		toggle_btn.text = "▾" if _expanded else "▸"
