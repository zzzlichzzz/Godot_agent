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

# Состояние разворота: по умолчанию показываем первые 40 строк диффа,
# «Полный дифф» открывает остальное прямо в карточке.
const PREVIEW_MAX_LINES := 40
const COLLAPSED_HEIGHT := 180.0
var _full_diff_text: String = ""
var _show_full: bool = false
var _view_full_label: String = "Полный дифф"
var _view_hide_label: String = "Свернуть дифф"

signal diff_applied(file_path: String)
signal diff_rejected(file_path: String)
# «Разрешить всё»: клик по кнопке на карточке включает автоподтверждение
# и применяет текущий дифф. Обработчик подключает agent_chat_view.gd.
signal apply_all_requested


# Цвета, шрифты и стили — единый модуль agent_theme.gd.
static var _theme_script = null
static var _locale_script = null


func _T():
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
	var T = _T()
	if T == null:
		return
	add_theme_stylebox_override("panel", T.panel_style("agent"))

	title_label.add_theme_color_override("font_color", T.color("accent"))
	title_label.add_theme_font_size_override("font_size", T.font_size("Label", 13))

	file_path_label.add_theme_color_override("font_color", T.color("dim"))
	# Длинный res:// путь не должен растягивать карточку — обрезаем троеточием.
	file_path_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	file_path_label.clip_text = true

	# Тело диффа: моно-шрифт редактора, свой фон и собственный скролл.
	# Здесь scroll_active/fit_content выставляет _apply_diff_view(), поэтому
	# style_rich_text не используем — он бы включил fit_content всегда.
	diff_container.add_theme_stylebox_override("normal", T.panel_style("code_plain"))
	diff_container.add_theme_color_override("default_color", T.color("text"))
	diff_container.add_theme_color_override("selection_color", T.color("accent"))
	var mono: Font = T.mono_font()
	if mono != null:
		diff_container.add_theme_font_override("normal_font", mono)
		diff_container.add_theme_font_override("mono_font", mono)
	diff_container.add_theme_font_size_override("normal_font_size", T.font_size("CodeEdit", 13))

	T.style_button(apply_btn, "success")
	T.style_button(reject_btn, "error")
	T.style_button(view_full_btn, "neutral")
	T.style_button(apply_all_btn, "accent")


func setup(file_path: String, diff_text: String) -> void:
	_file_path = file_path
	_diff_data = diff_text
	file_path_label.text = file_path
	file_path_label.tooltip_text = file_path
	_full_diff_text = _highlight_diff(diff_text)
	_show_full = false
	_apply_diff_view()


func set_view_full_texts(show_label: String, hide_label: String) -> void:
	_view_full_label = show_label
	_view_hide_label = hide_label
	_apply_diff_view()


func _apply_diff_view() -> void:
	# Раньше «Полный дифф» лишь слал сигнал view_full_requested, который никто
	# не слушал — кнопка ничего не делала. Теперь она реально доклеивает
	# скрытый хвост диффа прямо в карточке.
	var total := _diff_data.split("\n").size()
	var need_cut := total > PREVIEW_MAX_LINES
	view_full_btn.visible = need_cut
	if not need_cut or _show_full:
		diff_container.text = _full_diff_text
		view_full_btn.text = _view_hide_label
		# Развёрнутый дифф показываем целиком, без внутреннего скролла.
		diff_container.fit_content = _show_full
		diff_container.scroll_active = not _show_full
		diff_container.custom_minimum_size.y = 0.0 if _show_full else COLLAPSED_HEIGHT
		return
	var head := _diff_data.split("\n").slice(0, PREVIEW_MAX_LINES)
	diff_container.text = _highlight_diff("\n".join(head))
	diff_container.fit_content = false
	diff_container.scroll_active = true
	diff_container.custom_minimum_size.y = COLLAPSED_HEIGHT
	view_full_btn.text = "%s (%d)" % [_view_full_label, total]


func _highlight_diff(diff_text: String) -> String:
	# Нативные цвета редактора вместо захардкоженных.
	var T = _T()
	if T == null:
		return _escape_bbcode(diff_text)
	var add_color: String = T.hex("success")
	var del_color: String = T.hex("error")
	var hunk_color: String = T.hex("accent")
	var ctx_color: String = T.hex("text")

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
	var T = _T()
	if T:
		return T.escape_bbcode(text)
	return text


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
	_show_full = not _show_full
	_apply_diff_view()
