@tool
extends PanelContainer
class_name DiffPreviewCard

@onready var title_label: Label = $RootVBox/HeaderBox/TitleLabel
@onready var file_path_label: Label = $RootVBox/HeaderBox/FilePathLabel
@onready var diff_container: RichTextLabel = $RootVBox/DiffContainer
@onready var actions_box: HBoxContainer = $RootVBox/ActionsBox
@onready var apply_btn: Button = $RootVBox/ActionsBox/ApplyButton
@onready var reject_btn: Button = $RootVBox/ActionsBox/RejectButton
@onready var view_full_btn: Button = $RootVBox/ActionsBox/ViewFullButton
@onready var apply_all_btn: Button = $RootVBox/ActionsBox/ApplyAllButton

var _file_path: String = ""
var _diff_data: String = ""

signal diff_applied(file_path: String)
signal diff_rejected(file_path: String)
signal view_full_requested(file_path: String, diff_text: String)
# «Разрешить всё»: клик по кнопке на карточке включает автоподтверждение
# и применяет текущий дифф. Обработчик подключает agent_chat_view.gd.
signal apply_all_requested


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


func _ready() -> void:
	_setup_theme()
	if not apply_btn.pressed.is_connected(_on_apply_pressed):
		apply_btn.pressed.connect(_on_apply_pressed)
	if not reject_btn.pressed.is_connected(_on_reject_pressed):
		reject_btn.pressed.connect(_on_reject_pressed)
	if not view_full_btn.pressed.is_connected(_on_view_full_pressed):
		view_full_btn.pressed.connect(_on_view_full_pressed)
	if not apply_all_btn.pressed.is_connected(_on_apply_all_pressed):
		apply_all_btn.pressed.connect(_on_apply_all_pressed)


func _setup_theme() -> void:
	var accent := _tc("accent_color", "Editor", Color("#ffd54f"))
	var style := StyleBoxFlat.new()
	style.bg_color = _tc("dark_color_2", "Editor", Color("#1e1e2e"))
	style.border_color = Color(accent.r, accent.g, accent.b, 0.35)
	style.set_border_width_all(1)
	style.set_corner_radius_all(8)
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 8
	style.content_margin_bottom = 8
	add_theme_stylebox_override("panel", style)

	title_label.add_theme_color_override("font_color", accent)
	title_label.add_theme_font_size_override("font_size", _tfs("font_size", "Label", 13))

	file_path_label.add_theme_color_override("font_color", _tc("font_disabled_color", "Button", Color(0.6, 0.6, 0.6)))
	# Длинный res:// путь не должен растягивать карточку — обрезаем троеточием.
	file_path_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	file_path_label.clip_text = true

	# Тело диффа: моно-шрифт редактора, свой фон и собственный скролл.
	var code_style := StyleBoxFlat.new()
	code_style.bg_color = _tc("dark_color_3", "Editor", Color("#16161f"))
	code_style.set_corner_radius_all(6)
	code_style.content_margin_left = 8
	code_style.content_margin_right = 8
	code_style.content_margin_top = 6
	code_style.content_margin_bottom = 6
	diff_container.add_theme_stylebox_override("normal", code_style)
	diff_container.add_theme_color_override("default_color", _tc("font_color", "Label", Color.WHITE))
	diff_container.add_theme_color_override("selection_color", accent)
	var mono := _tf("font", "CodeEdit")
	if mono != null:
		diff_container.add_theme_font_override("normal_font", mono)
		diff_container.add_theme_font_override("mono_font", mono)
	diff_container.add_theme_font_size_override("normal_font_size", _tfs("font_size", "CodeEdit", 13))

	_style_button(apply_btn, _tc("success_color", "Editor", Color("#7ddc84")))
	_style_button(reject_btn, _tc("error_color", "Editor", Color("#f44336")))
	_style_button(view_full_btn, _tc("font_color", "Button", Color.WHITE))
	_style_button(apply_all_btn, accent)


func _style_button(btn: Button, color: Color) -> void:
	btn.flat = true
	btn.add_theme_color_override("font_color", color)
	btn.add_theme_color_override("font_hover_color", Color.WHITE)
	btn.add_theme_color_override("font_pressed_color", color)


func setup(file_path: String, diff_text: String) -> void:
	_file_path = file_path
	_diff_data = diff_text
	file_path_label.text = file_path
	file_path_label.tooltip_text = file_path
	diff_container.text = _highlight_diff(diff_text)


func _highlight_diff(diff_text: String) -> String:
	# Нативные цвета редактора вместо захардкоженных.
	var add_color := _tc("success_color", "Editor", Color("#7ddc84")).to_html(false)
	var del_color := _tc("error_color", "Editor", Color("#f44336")).to_html(false)
	var hunk_color := _tc("accent_color", "Editor", Color("#ffd54f")).to_html(false)
	var ctx_color := _tc("font_color", "Label", Color(0.78, 0.78, 0.78)).to_html(false)

	var lines := diff_text.split("\n")
	var result := ""
	for line in lines:
		var safe := _escape_bbcode(line)
		if line.begins_with("@@"):
			result += "[color=#%s]%s[/color]\n" % [hunk_color, safe]
		elif line.begins_with("+"):
			result += "[color=#%s]%s[/color]\n" % [add_color, safe]
		elif line.begins_with("-"):
			result += "[color=#%s]%s[/color]\n" % [del_color, safe]
		else:
			result += "[color=#%s]%s[/color]\n" % [ctx_color, safe]
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


func get_file_path() -> String:
	return _file_path


func set_allow_all_texts(label: String, tip: String) -> void:
	# Текст приходит из agent_locale, чтобы карточка не знала про язык.
	apply_all_btn.text = label
	apply_all_btn.tooltip_text = tip


func mark_auto_approved(note: String) -> void:
	# Режим «Разрешить всё»: кнопки не нужны, показываем что применено само.
	_lock_actions()
	actions_box.visible = false
	title_label.text = note


func _on_apply_pressed() -> void:
	_lock_actions()
	diff_applied.emit(_file_path)


func _on_reject_pressed() -> void:
	_lock_actions()
	diff_rejected.emit(_file_path)


func _on_apply_all_pressed() -> void:
	_lock_actions()
	apply_all_requested.emit()


func _lock_actions() -> void:
	# Защита от повторного нажатия, пока сервер обрабатывает ответ.
	apply_btn.disabled = true
	reject_btn.disabled = true
	apply_all_btn.disabled = true


func _on_view_full_pressed() -> void:
	view_full_requested.emit(_file_path, _diff_data)
