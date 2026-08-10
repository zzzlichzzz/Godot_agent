@tool
extends PanelContainer
class_name UserMessageCard

# Доля ширины панели, которую максимум занимает пузырь. Короткие сообщения
# обжимаются по тексту, длинные переносятся, не растягиваясь на весь чат.
const MAX_WIDTH_RATIO := 0.78
const MIN_BUBBLE_WIDTH := 120.0

@onready var bubble: PanelContainer = $Row/Bubble
@onready var content: RichTextLabel = $Row/Bubble/MessageBox/Content
@onready var name_label: Label = $Row/Bubble/MessageBox/Header/NameLabel
@onready var time_label: Label = $Row/Bubble/MessageBox/Header/TimeLabel
@onready var copy_btn: Button = $Row/Bubble/MessageBox/Header/CopyButton

var _hovered: bool = false


# --- безопасное чтение темы редактора (has_* обязателен: иначе Godot спамит ошибками) ---

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
	if not copy_btn.pressed.is_connected(_on_copy_pressed):
		copy_btn.pressed.connect(_on_copy_pressed)
	if not mouse_entered.is_connected(_show_actions):
		mouse_entered.connect(_show_actions)
	if not mouse_exited.is_connected(_hide_actions):
		mouse_exited.connect(_hide_actions)
	if not resized.is_connected(_recalc_bubble_width):
		resized.connect(_recalc_bubble_width)
	_set_actions_shown(false)
	_recalc_bubble_width()


func _setup_theme() -> void:
	# Внешняя карточка — только позиционирование, фон рисует сам пузырь.
	add_theme_stylebox_override("panel", StyleBoxEmpty.new())

	var accent := _tc("success_color", "Editor", Color("#7ddc84"))
	var bubble_style := StyleBoxFlat.new()
	bubble_style.bg_color = _tc("dark_color_1", "Editor", Color("#1f3320"))
	bubble_style.border_color = Color(accent.r, accent.g, accent.b, 0.45)
	bubble_style.set_border_width_all(1)
	bubble_style.set_corner_radius_all(8)
	# PanelContainer не умеет margin-константы, внутренние отступы задаёт сам стиль.
	bubble_style.content_margin_left = 12
	bubble_style.content_margin_right = 12
	bubble_style.content_margin_top = 8
	bubble_style.content_margin_bottom = 8
	bubble.add_theme_stylebox_override("panel", bubble_style)

	name_label.add_theme_color_override("font_color", accent)

	# У RichTextLabel цвет текста называется default_color, а не font_color.
	content.add_theme_color_override("default_color", _tc("font_color", "Label", Color.WHITE))
	content.add_theme_color_override("selection_color", _tc("accent_color", "Editor", Color("#ffd54f")))
	# Без fit_content RichTextLabel в контейнере получает нулевую высоту и текст не виден.
	content.fit_content = true
	content.scroll_active = false
	content.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	time_label.add_theme_color_override("font_color", _tc("font_disabled_color", "Button", Color(0.6, 0.6, 0.6)))

	var copy_icon := _ti("ActionCopy")
	if copy_icon != null:
		copy_btn.icon = copy_icon
		copy_btn.text = ""
	else:
		copy_btn.text = "⧉"
	copy_btn.add_theme_color_override("font_color", _tc("font_disabled_color", "Button", Color(0.6, 0.6, 0.6)))
	copy_btn.add_theme_color_override("icon_normal_color", _tc("font_disabled_color", "Button", Color(0.6, 0.6, 0.6)))
	copy_btn.add_theme_color_override("icon_hover_color", accent)


func setup(text: String, time_str: String = "") -> void:
	content.text = text
	if time_str != "":
		time_label.text = time_str
	else:
		var now := Time.get_time_dict_from_system()
		time_label.text = "%02d:%02d" % [int(now.get("hour", 0)), int(now.get("minute", 0))]
	_recalc_bubble_width()


func _recalc_bubble_width() -> void:
	# Пузырь обжимается по самой длинной строке, но не шире MAX_WIDTH_RATIO
	# панели — тогда текст переносится. Ширина фиксируется здесь, а не зависит
	# от появления кнопки копирования, поэтому при наведении ничего не прыгает.
	if content == null or not is_instance_valid(content):
		return
	var avail := size.x
	if avail <= 0.0:
		return
	var max_w := maxf(MIN_BUBBLE_WIDTH, avail * MAX_WIDTH_RATIO)
	var font := content.get_theme_font("normal_font")
	if font == null:
		font = ThemeDB.fallback_font
	var font_size := content.get_theme_font_size("normal_font_size")
	if font_size <= 0:
		font_size = ThemeDB.fallback_font_size
	var longest := 0.0
	for line in content.get_parsed_text().split("\n"):
		longest = maxf(longest, font.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x)
	# +2px — компенсация округления, иначе последняя буква иногда переносится.
	content.custom_minimum_size.x = clampf(longest + 2.0, 0.0, max_w)


func _on_copy_pressed() -> void:
	DisplayServer.clipboard_set(content.get_parsed_text())


func _set_actions_shown(shown: bool) -> void:
	# Кнопка всегда занимает своё место в шапке: прячем прозрачностью, а не
	# visible, чтобы размер пузыря при наведении не менялся.
	copy_btn.modulate.a = 1.0 if shown else 0.0
	copy_btn.mouse_filter = Control.MOUSE_FILTER_STOP if shown else Control.MOUSE_FILTER_IGNORE
	copy_btn.disabled = not shown


func _show_actions() -> void:
	_hovered = true
	_set_actions_shown(true)


func _hide_actions() -> void:
	# mouse_exited приходит и при переходе на дочерний Control (текст, кнопки),
	# поэтому прячем только когда курсор реально ушёл с карточки.
	if get_global_rect().has_point(get_global_mouse_position()):
		return
	_hovered = false
	_set_actions_shown(false)


func get_text() -> String:
	return content.text
