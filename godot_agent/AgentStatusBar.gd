@tool
extends PanelContainer
class_name AgentStatusBar

@onready var spinner: TextureRect = $Margin/HBoxContainer/Spinner
@onready var status_label: Label = $Margin/HBoxContainer/StatusLabel
@onready var elapsed_label: Label = $Margin/HBoxContainer/ElapsedLabel
@onready var chars_label: Label = $Margin/HBoxContainer/CharsLabel
@onready var timer: Timer = $Timer

var _start_time: int = 0
var _active: bool = false
var _spin: float = 0.0


# Цвета, иконки и стили — единый модуль agent_theme.gd.
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
	# Надпись из .tscn («Думает...») остаётся на экране, пока не придёт первая
	# фаза от сервера, — а по-английски она была русской. Ставим из словаря сразу.
	status_label.text = _t("status_thinking")
	if not timer.timeout.is_connected(_on_timer_tick):
		timer.timeout.connect(_on_timer_tick)
	visible = false


func _setup_theme() -> void:
	var T = _T()
	if T == null:
		return
	# Сцена открыта во вкладке редактора — оформление не применяем, иначе
	# Godot запечёт иконки и шрифты в .tscn при сохранении (см. is_edited_scene).
	if T.is_edited_scene(self):
		return
	add_theme_stylebox_override("panel", T.panel_style("status"))

	var accent: Color = T.color("accent")
	var spinner_icon: Texture2D = T.first_icon(["ProgressIndicator", "Progress1"])
	if spinner_icon != null:
		spinner.texture = spinner_icon
		spinner.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		spinner.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	spinner.modulate = accent
	# Центр вращения — середина иконки.
	spinner.pivot_offset = spinner.custom_minimum_size / 2.0

	status_label.add_theme_color_override("font_color", T.color("text"))
	elapsed_label.add_theme_color_override("font_color", T.color("dim"))
	chars_label.add_theme_color_override("font_color", T.color("dim"))

	timer.wait_time = 0.5
	timer.one_shot = false


func _chars_text(chars: int) -> String:
	return ("%s %s" % [chars, _t("unit_chars")]) if chars > 0 else ""


func show_status(phase: String, elapsed: int = 0, chars: int = 0) -> void:
	_start_time = Time.get_ticks_msec() - (elapsed * 1000)
	_active = true
	visible = true
	status_label.text = phase
	elapsed_label.text = _format_time(elapsed)
	chars_label.text = _chars_text(chars)
	if timer.is_stopped():
		timer.start()


func hide_status() -> void:
	_active = false
	visible = false
	timer.stop()


func update_status(phase: String, elapsed: int = -1, chars: int = -1) -> void:
	if not _active:
		return
	if phase != "":
		status_label.text = phase
	if elapsed >= 0:
		elapsed_label.text = _format_time(elapsed)
	if chars >= 0:
		chars_label.text = _chars_text(chars)


func _on_timer_tick() -> void:
	if not _active:
		return
	var elapsed := (Time.get_ticks_msec() - _start_time) / 1000
	elapsed_label.text = _format_time(int(elapsed))
	# Вращение спиннера через собственный счётчик (плавно, на любом движке таймера).
	_spin += PI / 4
	spinner.rotation = fmod(_spin, TAU)


func _format_time(seconds: int) -> String:
	var m := seconds / 60
	var s := seconds % 60
	return "%02d:%02d" % [m, s]
