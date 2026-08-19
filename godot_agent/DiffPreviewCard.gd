@tool
extends PanelContainer
class_name DiffPreviewCard

# ============================================================================
# Карточка изменений файла.
#
# Свёрнутый вид — ОДНА строка: «▸ res://путь.gd  +12 -3». Клик по строке
# разворачивает сам код: добавленные строки зелёные, удалённые красные,
# слева номера строк. Так лента чата не превращается в простыню кода, а
# посмотреть правку по-прежнему можно, не открывая файл.
#
# Данные приходят двумя способами:
#   setup_diff(path, diff)  — разобранный дифф с сервера (pending_action_diff),
#                             это основной путь;
#   setup(path, code)       — только предлагаемый код, без «до/после».
#                             Запасной путь: старая сборка сервера или патч,
#                             который не сошёлся с диском (дифф не посчитать).
# ============================================================================

@onready var header_box: HBoxContainer = $RootVBox/HeaderBox
@onready var title_label: Label = $RootVBox/HeaderBox/TitleLabel
@onready var file_path_label: Label = $RootVBox/HeaderBox/FilePathLabel
@onready var diff_container: RichTextLabel = $RootVBox/DiffContainer
@onready var actions_box: HBoxContainer = $RootVBox/ActionsBox
@onready var apply_btn: Button = $RootVBox/ActionsBox/ApplyButton
@onready var reject_btn: Button = $RootVBox/ActionsBox/RejectButton
@onready var view_full_btn: Button = $RootVBox/ActionsBox/ViewFullButton
@onready var apply_all_btn: Button = $RootVBox/ActionsBox/ApplyAllButton

# Узлы шапки, которых нет в .tscn: стрелка сворачивания и счётчики строк.
# Создаются кодом намеренно — иконки и шрифты темы, присвоенные в редакторе,
# Godot запекает в .tscn при сохранении сцены (см. agent_theme.is_edited_scene).
var expand_btn: Button = null
var stats_add_label: Label = null
var stats_del_label: Label = null

var _file_path: String = ""
var _diff_data: String = ""

# Разобранный дифф: массив строк [пометка, номер_старой, номер_новой, текст].
# Пометки те же, что у сервера: "+", "-", " " (контекст), "@" (заголовок куска).
var _diff_lines: Array = []
var _added: int = 0
var _removed: int = 0
var _truncated: bool = false
var _has_diff: bool = false

# Свёрнуто по умолчанию: в ленте карточка занимает одну строку.
var _expanded: bool = false
# Сколько строк показываем без внутреннего скролла. Дальше у тела появляется
# своя полоса прокрутки, иначе одна большая правка занимала бы весь экран.
const FIT_MAX_LINES := 30
const BODY_HEIGHT := 260.0
# Полный показ по кнопке «Полный дифф» — верхний предел строк на карточку.
const PREVIEW_MAX_LINES := 400
var _show_full: bool = false
# Подписи кнопки «весь дифф». Заполняются из словаря в _apply_locale(); здесь
# пусто НАМЕРЕННО — русский литерал по умолчанию однажды уже уехал на экран при
# английском языке, потому что переписать его никто не обязан был.
var _view_full_label: String = ""
var _view_hide_label: String = ""

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
	_ensure_header_controls()
	_apply_locale()
	_setup_theme()
	if not apply_btn.pressed.is_connected(_on_apply_pressed):
		apply_btn.pressed.connect(_on_apply_pressed)
	if not reject_btn.pressed.is_connected(_on_reject_pressed):
		reject_btn.pressed.connect(_on_reject_pressed)
	if not view_full_btn.pressed.is_connected(_on_view_full_pressed):
		view_full_btn.pressed.connect(_on_view_full_pressed)
	if not apply_all_btn.pressed.is_connected(_on_apply_all_pressed):
		apply_all_btn.pressed.connect(_on_apply_all_pressed)


func _apply_locale() -> void:
	# ПОЧЕМУ ЭТО ОБЯЗАТЕЛЬНО. Надписи кнопок лежат в .tscn по-русски — их видно
	# в редакторе сцен, и это удобно. Но значение из .tscn остаётся на экране,
	# пока код его не перепишет: у «Применить» и «Отклонить» этого не делал никто,
	# и на английском языке они так и оставались русскими. Ставим ВСЕ надписи
	# карточки здесь, а не по месту: тогда забыть одну нельзя — их видно списком.
	title_label.text = _t("diff_title")
	apply_btn.text = _t("diff_apply")
	reject_btn.text = _t("reject")
	apply_all_btn.text = _t("allow_all")
	apply_all_btn.tooltip_text = _t("allow_all_tip")
	# Подписи кнопки «весь дифф» держим в полях: у неё две надписи (показать и
	# свернуть), и переключаются они при каждом нажатии.
	_view_full_label = _t("diff_show_full")
	_view_hide_label = _t("diff_hide_full")
	view_full_btn.text = _t("diff_show_full")


func _ensure_header_controls() -> void:
	if expand_btn != null and is_instance_valid(expand_btn):
		return
	# Вся строка шапки — кликабельная: попасть по крохотной стрелке в узком
	# доке неудобно. Клик по кнопке и по строке делают одно и то же.
	header_box.mouse_filter = Control.MOUSE_FILTER_STOP
	header_box.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	if not header_box.gui_input.is_connected(_on_header_gui_input):
		header_box.gui_input.connect(_on_header_gui_input)
	# PASS, а не IGNORE: подсказка с полным путём остаётся, но клик всё равно
	# доходит до шапки и разворачивает карточку.
	title_label.mouse_filter = Control.MOUSE_FILTER_PASS
	file_path_label.mouse_filter = Control.MOUSE_FILTER_PASS

	expand_btn = Button.new()
	expand_btn.name = "ExpandButton"
	expand_btn.flat = true
	expand_btn.focus_mode = Control.FOCUS_NONE
	expand_btn.custom_minimum_size = Vector2(20, 20)
	expand_btn.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	expand_btn.pressed.connect(_toggle_expanded)
	header_box.add_child(expand_btn)
	header_box.move_child(expand_btn, 0)

	stats_add_label = Label.new()
	stats_add_label.name = "StatsAddLabel"
	stats_add_label.mouse_filter = Control.MOUSE_FILTER_PASS
	stats_add_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	header_box.add_child(stats_add_label)

	stats_del_label = Label.new()
	stats_del_label.name = "StatsDelLabel"
	stats_del_label.mouse_filter = Control.MOUSE_FILTER_PASS
	stats_del_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	header_box.add_child(stats_del_label)


func _setup_theme() -> void:
	var T = _T()
	if T == null:
		return
	# Сцена открыта во вкладке редактора — оформление не применяем, иначе
	# Godot запечёт иконки и шрифты в .tscn при сохранении (см. is_edited_scene).
	if T.is_edited_scene(self):
		return
	add_theme_stylebox_override("panel", T.panel_style("agent"))

	title_label.add_theme_color_override("font_color", T.color("accent"))
	title_label.add_theme_font_size_override("font_size", T.font_size("Label", 13))

	file_path_label.add_theme_color_override("font_color", T.color("dim"))
	# Длинный res:// путь не должен растягивать карточку — обрезаем троеточием.
	file_path_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	file_path_label.clip_text = true

	if stats_add_label:
		stats_add_label.add_theme_color_override("font_color", T.color("success"))
		stats_add_label.add_theme_font_size_override("font_size", T.font_size("Label", 13))
	if stats_del_label:
		stats_del_label.add_theme_color_override("font_color", T.color("error"))
		stats_del_label.add_theme_font_size_override("font_size", T.font_size("Label", 13))

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


# --- вход данных ---

func setup(file_path: String, diff_text: String) -> void:
	# Запасной путь: сервер прислал только предлагаемый код, без «до/после».
	_file_path = file_path
	_diff_data = diff_text
	_has_diff = false
	_diff_lines = []
	_added = 0
	_removed = 0
	_truncated = false
	_expanded = false
	_show_full = false
	_fill_header()
	_apply_diff_view()


func setup_diff(file_path: String, diff: Dictionary) -> void:
	_file_path = file_path
	_diff_data = ""
	var raw = diff.get("lines")
	_diff_lines = raw if raw is Array else []
	_added = int(diff.get("added", 0))
	_removed = int(diff.get("removed", 0))
	_truncated = bool(diff.get("truncated", false))
	_has_diff = not _diff_lines.is_empty()
	_expanded = false
	_show_full = false
	_fill_header()
	_apply_diff_view()


func _fill_header() -> void:
	file_path_label.text = _file_path
	file_path_label.tooltip_text = _file_path
	# В режиме диффа шапка — одна строка «путь +N -M»; слово «предпросмотр»
	# в узком доке только съедало бы место.
	title_label.visible = not _has_diff
	if stats_add_label:
		# Нулевой счётчик не показываем: у нового файла «-0» только мусорит
		# строку, которая должна быть предельно короткой.
		stats_add_label.visible = _has_diff and _added > 0
		stats_add_label.text = "+%d" % _added
	if stats_del_label:
		stats_del_label.visible = _has_diff and _removed > 0
		stats_del_label.text = "-%d" % _removed
	if _has_diff:
		var tip := "%s\n+%d / -%d" % [_file_path, _added, _removed]
		header_box.tooltip_text = tip
		file_path_label.tooltip_text = tip


func set_view_full_texts(show_label: String, hide_label: String) -> void:
	_view_full_label = show_label
	_view_hide_label = hide_label
	_apply_diff_view()


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
	title_label.visible = true
	title_label.text = note
	# Путь уже есть внутри note — второй раз его не показываем.
	file_path_label.visible = false


func mark_applied() -> void:
	# Отчёт о том, что УЖЕ применено (шаг плана): спрашивать нечего, поэтому
	# кнопок нет вовсе. Шапка со статистикой и разворот кода остаются —
	# ради них карточка и показывается.
	_lock_actions()
	actions_box.visible = false


# --- сворачивание ---

func _on_header_gui_input(event: InputEvent) -> void:
	var mb := event as InputEventMouseButton
	if mb and mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
		_toggle_expanded()
		header_box.accept_event()


func _toggle_expanded() -> void:
	_expanded = not _expanded
	if not _expanded:
		# Свернули — «полный дифф» тоже сбрасываем, иначе следующее
		# разворачивание сразу вывалит простыню на весь экран.
		_show_full = false
	_apply_diff_view()


func _update_expand_button() -> void:
	if expand_btn == null or not is_instance_valid(expand_btn):
		return
	var T = _T()
	var names := ["GuiTreeArrowDown", "ArrowDown"] if _expanded else ["GuiTreeArrowRight", "ArrowRight"]
	if T:
		T.style_icon_button(expand_btn, names, "▾" if _expanded else "▸", "dim")
	else:
		expand_btn.text = "▾" if _expanded else "▸"
	expand_btn.tooltip_text = _t("diff_collapse_tip") if _expanded else _t("diff_expand_tip")


# --- отрисовка ---

func _apply_diff_view() -> void:
	_update_expand_button()
	diff_container.visible = _expanded
	if not _expanded:
		# Свёрнутую карточку не рисуем вовсе: BBCode на сотни строк стоит
		# дорого, а в ленте таких карточек могут быть десятки.
		diff_container.text = ""
		view_full_btn.visible = false
		return

	var total := _total_lines()
	var limit := PREVIEW_MAX_LINES if _show_full else FIT_MAX_LINES
	var need_cut := total > FIT_MAX_LINES
	view_full_btn.visible = need_cut
	if need_cut:
		view_full_btn.text = _view_hide_label if _show_full else ("%s (%d)" % [_view_full_label, total])

	if _has_diff:
		diff_container.text = _render_diff(limit)
	else:
		diff_container.text = _highlight_diff(_cut_text(_diff_data, limit))

	# Короткий дифф показываем целиком; длинный получает свою полосу прокрутки,
	# иначе одна правка растянет карточку на весь экран.
	var fits := total <= limit
	diff_container.fit_content = fits
	diff_container.scroll_active = not fits
	diff_container.custom_minimum_size.y = 0.0 if fits else BODY_HEIGHT


func _total_lines() -> int:
	if _has_diff:
		return _diff_lines.size()
	return _diff_data.split("\n").size()


func _cut_text(text: String, limit: int) -> String:
	var lines := text.split("\n")
	if lines.size() <= limit:
		return text
	return "\n".join(lines.slice(0, limit))


func _render_diff(limit: int) -> String:
	# Цвет — из темы редактора, поэтому дифф читаем и на светлой теме.
	var T = _T()
	var add_hex: String = T.hex("success") if T else "7ddc84"
	var del_hex: String = T.hex("error") if T else "f44336"
	var hunk_hex: String = T.hex("accent") if T else "ffd54f"
	var ctx_hex: String = T.hex("text") if T else "ffffff"
	var num_hex: String = T.hex("dim") if T else "999999"
	# Фон строки полупрозрачный: подложка под текстом, а не заливка в упор —
	# иначе на светлой теме код становится нечитаемым.
	var add_bg := _bg_hex(T, "success")
	var del_bg := _bg_hex(T, "error")

	var width := _line_number_width(limit)
	var out := ""
	var shown := 0
	for entry in _diff_lines:
		if shown >= limit:
			break
		shown += 1
		if not (entry is Array) or (entry as Array).size() < 4:
			continue
		var op := str(entry[0])
		var body: String = _escape_bbcode(str(entry[3]))
		if op == "@":
			out += "[color=#%s]%s[/color]\n" % [hunk_hex, body]
			continue
		var num := _line_number(entry, op)
		var gutter := "[color=#%s]%s[/color]" % [num_hex, _pad_left(num, width)]
		if op == "+":
			out += "%s [bgcolor=#%s][color=#%s]+ %s[/color][/bgcolor]\n" % [gutter, add_bg, add_hex, body]
		elif op == "-":
			out += "%s [bgcolor=#%s][color=#%s]- %s[/color][/bgcolor]\n" % [gutter, del_bg, del_hex, body]
		else:
			out += "%s [color=#%s]  %s[/color]\n" % [gutter, ctx_hex, body]
	if _truncated or shown < _diff_lines.size():
		out += "[color=#%s]%s[/color]\n" % [num_hex, _escape_bbcode(_t("diff_truncated"))]
	return out


func _bg_hex(T, key: String) -> String:
	if T == null:
		return "00000000"
	# to_html(true) даёт RRGGBBAA — ровно тот формат, что понимает [bgcolor].
	return T.alpha(key, 0.16).to_html(true)


func _line_number(entry: Array, op: String) -> String:
	# У добавленной строки нет номера в старом файле, у удалённой — в новом.
	var value = entry[2] if op != "-" else entry[1]
	if value == null:
		return ""
	return str(int(value))


func _line_number_width(limit: int) -> int:
	var width := 2
	var shown := 0
	for entry in _diff_lines:
		if shown >= limit:
			break
		shown += 1
		if not (entry is Array) or (entry as Array).size() < 4:
			continue
		var op := str(entry[0])
		if op == "@":
			continue
		width = maxi(width, _line_number(entry, op).length())
	return width


func _pad_left(text: String, width: int) -> String:
	var pad := width - text.length()
	if pad <= 0:
		return text
	return " ".repeat(pad) + text


func _highlight_diff(diff_text: String) -> String:
	# Запасной режим: пришёл только предлагаемый код, «до/после» неизвестно.
	# Красить строки по +/- здесь нельзя — в обычном коде это просто минус
	# в начале строки, а не удаление.
	var T = _T()
	if T == null:
		return _escape_bbcode(diff_text)
	return "[color=#%s]%s[/color]" % [T.hex("code_text"), _escape_bbcode(diff_text)]


func _escape_bbcode(text: String) -> String:
	var T = _T()
	if T:
		return T.escape_bbcode(text)
	return text


# --- кнопки ---

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
