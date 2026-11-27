@tool
extends PanelContainer
class_name UserMessageCard

# Доля ширины панели, которую максимум занимает пузырь. Короткие сообщения
# обжимаются по тексту, длинные переносятся, не растягиваясь на весь чат.
const MAX_WIDTH_RATIO := 0.90

@onready var bubble: PanelContainer = $Row/Bubble
@onready var content: RichTextLabel = $Row/Bubble/MessageBox/Content
@onready var name_label: Label = $Row/Bubble/MessageBox/Header/NameLabel
@onready var time_label: Label = $Row/Bubble/MessageBox/Header/TimeLabel
@onready var copy_btn: Button = $Row/Bubble/MessageBox/Header/CopyButton


# Цвета, иконки и стили — единый модуль agent_theme.gd.
static var _theme_script = null
# Словарь надписей — agent_locale.gd. Отдельной ссылкой от темы: оформление в
# открытой во вкладке сцене намеренно не применяется, а надписи нужны всегда.
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
	_apply_locale()
	if not copy_btn.pressed.is_connected(_on_copy_pressed):
		copy_btn.pressed.connect(_on_copy_pressed)
	copy_btn.focus_mode = Control.FOCUS_ALL
	copy_btn.mouse_filter = Control.MOUSE_FILTER_STOP
	copy_btn.modulate.a = 1.0
	copy_btn.disabled = false
	if not resized.is_connected(_recalc_bubble_width):
		resized.connect(_recalc_bubble_width)
	_recalc_bubble_width()


func _apply_locale() -> void:
	# «Вы» и подсказка «Копировать» лежат в .tscn по-русски и остаются на экране,
	# пока код их не перепишет. Раньше не переписывал никто — на английском
	# языке подпись автора сообщения так и оставалась русской.
	name_label.text = _t("you")
	copy_btn.tooltip_text = _t("copy")


func _setup_theme() -> void:
	var T = _T()
	if T == null:
		return
	# Сцена открыта во вкладке редактора — оформление не применяем, иначе
	# Godot запечёт иконки и шрифты в .tscn при сохранении (см. is_edited_scene).
	if T.is_edited_scene(self):
		return
	# Внешняя карточка — только позиционирование, фон рисует сам пузырь.
	add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	var surface: StyleBoxFlat = T.panel_style("user")
	surface.border_color = T.alpha("accent", 0.65)
	surface.border_width_right = T.px(3)
	bubble.add_theme_stylebox_override("panel", surface)

	name_label.add_theme_color_override("font_color", T.color("text"))
	name_label.add_theme_stylebox_override("normal", T.badge_style("accent"))
	$Row/Bubble/MessageBox.add_theme_constant_override("separation", T.px(8))
	time_label.add_theme_color_override("font_color", T.color("dim"))
	time_label.add_theme_font_size_override("font_size", T.font_size("Label", 14) - T.px(1))

	# style_rich_text ставит fit_content: без него текст в контейнере не виден.
	T.style_rich_text(content)
	content.bbcode_enabled = false
	content.add_theme_constant_override("line_separation", T.px(2))
	content.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	T.style_icon_button(copy_btn, ["ActionCopy"], "⧉")


func setup(text: String, time_str: String = "", restored: bool = false) -> void:
	content.text = text
	if restored or time_str != "":
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
	var inset := bubble.get_theme_stylebox("panel").get_minimum_size().x
	var max_w := maxf(1.0, avail * MAX_WIDTH_RATIO - inset)
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


func get_text() -> String:
	return content.text
