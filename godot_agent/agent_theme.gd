@tool
extends Object

# ---------------------------------------------------------------------------
# Единый источник визуального стиля аддона.
#
# Раньше хелперы чтения темы (_tc/_tf/_tfs/_ti) были скопированы в семь файлов
# карточек, а панель, диалоги и стартовый экран рисовались дефолтными
# контролами с захардкоженными цветами. Теперь цвета, иконки и стили берутся
# отсюда — один источник правды на весь аддон.
#
# Использование из любого скрипта аддона:
#   var T = load("...папка аддона.../agent_theme.gd")
#   T.color("accent")            -> Color из темы редактора (или fallback)
#   T.icon("Script")             -> Texture2D из EditorIcons (или null)
#   panel.add_theme_stylebox_override("panel", T.panel_style("agent"))
#   T.style_button(btn, "success")
#
# ВАЖНО: цвета читаются из темы редактора Godot, поэтому аддон подстраивается
# и под тёмную, и под светлую тему. Fallback-значения совпадают с теми, что
# были в карточках до вынесения, — внешний вид не меняется, если тема недоступна.
# ---------------------------------------------------------------------------

# Кэш живёт между вызовами: get_editor_theme() на каждый цвет заметно
# тормозил при отрисовке длинной истории чата.
static var _colors: Dictionary = {}
static var _icons: Dictionary = {}

# Семантическое имя -> [имя в теме, тип в теме, запасной цвет].
# "dark_color_*" в светлой теме редактора светлые — отсюда и берётся
# автоматическая подстройка под тему.
const _COLOR_MAP := {
	"accent": ["accent_color", "Editor", Color("#ffd54f")],
	"success": ["success_color", "Editor", Color("#7ddc84")],
	"warning": ["warning_color", "Editor", Color("#ffb74d")],
	"error": ["error_color", "Editor", Color("#f44336")],
	"bg_1": ["dark_color_1", "Editor", Color("#232333")],
	"bg_2": ["dark_color_2", "Editor", Color("#26303d")],
	"bg_3": ["dark_color_3", "Editor", Color("#1f2430")],
	"contrast": ["contrast_color_1", "Editor", Color("#3a4a63")],
	"text": ["font_color", "Label", Color.WHITE],
	"dim": ["font_disabled_color", "Button", Color(0.6, 0.6, 0.6)],
	"btn_text": ["font_color", "Button", Color.WHITE],
}

# Цвет кода берётся не из Theme, а из настроек редактора кода: в Theme
# "code_font_color" не существует (проверено на 4.6 — has_color вернул false),
# а "font_color"/"CodeEdit" совпадает с обычным текстом, и код переставал
# выделяться. Здесь — настоящий цвет подсветки из темы пользователя.
const _CODE_COLOR_SETTING := "text_editor/theme/highlighting/symbol_color"
const _CODE_COLOR_FALLBACK := Color("#8ab4f8")


static func _editor_theme() -> Theme:
	if Engine.is_editor_hint():
		return EditorInterface.get_editor_theme()
	return null


static func invalidate() -> void:
	# Вызывать при смене темы редактора: кэш цветов и иконок сбрасывается,
	# следующий запрос перечитает тему заново.
	_colors.clear()
	_icons.clear()


# --- цвета ---

static func color(key: String) -> Color:
	if _colors.has(key):
		return _colors[key]
	if key == "code_text":
		var code := _CODE_COLOR_FALLBACK
		if Engine.is_editor_hint():
			var es := EditorInterface.get_editor_settings()
			if es and es.has_setting(_CODE_COLOR_SETTING):
				code = es.get_setting(_CODE_COLOR_SETTING)
		_colors[key] = code
		return code
	var spec = _COLOR_MAP.get(key)
	if spec == null:
		push_warning("agent_theme: неизвестный цвет " + key)
		return Color.WHITE
	var result: Color = spec[2]
	var th := _editor_theme()
	if th and th.has_color(spec[0], spec[1]):
		result = th.get_color(spec[0], spec[1])
	_colors[key] = result
	return result


static func alpha(key: String, a: float) -> Color:
	var c := color(key)
	return Color(c.r, c.g, c.b, a)


static func hex(key: String) -> String:
	# Для BBCode-тегов [color=#...]: нужен цвет без альфы.
	return color(key).to_html(false)


# --- иконки и шрифты редактора ---

static func icon(icon_name: StringName) -> Texture2D:
	if _icons.has(icon_name):
		return _icons[icon_name]
	var result: Texture2D = null
	var th := _editor_theme()
	if th and th.has_icon(icon_name, "EditorIcons"):
		result = th.get_icon(icon_name, "EditorIcons")
	_icons[icon_name] = result
	return result


static func first_icon(names: Array) -> Texture2D:
	# Имена иконок между версиями Godot меняются — берём первую доступную.
	for n in names:
		var tex := icon(StringName(str(n)))
		if tex != null:
			return tex
	return null


static func mono_font() -> Font:
	var th := _editor_theme()
	if th and th.has_font("font", "CodeEdit"):
		return th.get_font("font", "CodeEdit")
	return null


static func font_size(theme_type: String, fallback: int) -> int:
	# ВНИМАНИЕ: тема редактора отвечает на has_font_size() для ЛЮБОГО типа
	# (проверено на 4.6: даже для несуществующего вернётся размер по умолчанию),
	# поэтому fallback срабатывает только когда темы нет вообще — вне редактора.
	# Размер кода и текста в теме редактора совпадают; так же вело себя
	# прежнее _tfs() в карточках, поэтому внешний вид не меняется.
	var th := _editor_theme()
	if th and th.has_font_size("font_size", theme_type):
		return th.get_font_size("font_size", theme_type)
	return fallback


# --- панели ---

static func make_panel_style(bg: Color, border: Color, radius: int, margin_h: int, margin_v: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = bg
	if border.a > 0.0:
		style.border_color = border
		style.set_border_width_all(1)
	style.set_corner_radius_all(radius)
	# PanelContainer не понимает margin-константы (они есть только у
	# MarginContainer) — внутренние отступы задаёт сам StyleBox.
	style.content_margin_left = margin_h
	style.content_margin_right = margin_h
	style.content_margin_top = margin_v
	style.content_margin_bottom = margin_v
	return style


static func panel_style(variant: String) -> StyleBoxFlat:
	# Готовые варианты панелей — ровно те, что использовались в карточках.
	match variant:
		"agent":
			return make_panel_style(color("bg_2"), alpha("accent", 0.35), 8, 12, 8)
		"user":
			return make_panel_style(color("bg_1"), alpha("success", 0.45), 8, 12, 8)
		"hint":
			return make_panel_style(color("bg_1"), alpha("warning", 0.45), 8, 12, 8)
		"error":
			return make_panel_style(color("bg_1"), alpha("error", 0.45), 8, 12, 8)
		"code":
			return make_panel_style(color("bg_3"), alpha("accent", 0.35), 6, 12, 8)
		"code_plain":
			return make_panel_style(color("bg_3"), Color(0, 0, 0, 0), 6, 8, 6)
		"tool":
			return make_panel_style(color("bg_2"), color("contrast"), 6, 10, 6)
		"status":
			return make_panel_style(color("bg_1"), alpha("accent", 0.35), 6, 0, 0)
		_:
			return make_panel_style(color("bg_2"), alpha("accent", 0.35), 8, 12, 8)


# --- кнопки ---

static func tone_color(tone: String) -> Color:
	match tone:
		"success":
			return color("success")
		"error":
			return color("error")
		"warning":
			return color("warning")
		"accent":
			return color("accent")
		"dim":
			return color("dim")
		_:
			return color("btn_text")


static func style_button(btn: Button, tone: String = "neutral", flat: bool = true) -> void:
	if btn == null:
		return
	var c := tone_color(tone)
	btn.flat = flat
	btn.add_theme_color_override("font_color", c)
	btn.add_theme_color_override("font_hover_color", color("text"))
	btn.add_theme_color_override("font_pressed_color", c)
	btn.add_theme_color_override("icon_normal_color", c)
	btn.add_theme_color_override("icon_hover_color", color("accent"))


static func style_icon_button(btn: Button, icon_names: Array, fallback_text: String, tone: String = "dim") -> void:
	# Кнопка-иконка: если иконки редактора нет (старая версия Godot),
	# честно показываем текстовый запасной вариант, а не пустой квадрат.
	if btn == null:
		return
	var tex := first_icon(icon_names)
	if tex != null:
		btn.icon = tex
		btn.text = ""
	else:
		btn.icon = null
		btn.text = fallback_text
	style_button(btn, tone)


# --- поля ввода ---

static func style_input(ctrl: Control) -> void:
	# TextEdit/LineEdit: фон и рамка как у панелей, при фокусе рамка акцентная.
	if ctrl == null:
		return
	var normal := make_panel_style(color("bg_3"), alpha("contrast", 0.8), 6, 8, 6)
	var focus := make_panel_style(color("bg_3"), alpha("accent", 0.7), 6, 8, 6)
	ctrl.add_theme_stylebox_override("normal", normal)
	ctrl.add_theme_stylebox_override("focus", focus)
	ctrl.add_theme_color_override("font_color", color("text"))
	ctrl.add_theme_color_override("font_placeholder_color", alpha("dim", 0.8))
	ctrl.add_theme_color_override("caret_color", color("accent"))
	ctrl.add_theme_color_override("selection_color", alpha("accent", 0.35))


# --- текстовые блоки ---

static func style_rich_text(rt: RichTextLabel, mono: bool = false) -> void:
	# Без fit_content RichTextLabel внутри контейнера получает нулевую высоту
	# и текст просто не виден — это уже ловилось при первой сборке карточек.
	if rt == null:
		return
	rt.fit_content = true
	rt.scroll_active = false
	rt.bbcode_enabled = true
	rt.selection_enabled = true
	rt.context_menu_enabled = true
	rt.add_theme_color_override("default_color", color("text"))
	rt.add_theme_color_override("selection_color", color("accent"))
	var mono_f := mono_font()
	if mono_f != null:
		rt.add_theme_font_override("mono_font", mono_f)
		if mono:
			rt.add_theme_font_override("normal_font", mono_f)
	var code_size := font_size("CodeEdit", 13)
	rt.add_theme_font_size_override("mono_size", code_size)
	if mono:
		rt.add_theme_font_size_override("normal_font_size", code_size)


static func escape_bbcode(text: String) -> String:
	# Одна реализация вместо пяти копий по файлам аддона.
	var result := ""
	for i in range(text.length()):
		var c := text[i]
		if c == "[":
			result += "[lb]"
		elif c == "]":
			result += "[rb]"
		else:
			result += c
	return result
