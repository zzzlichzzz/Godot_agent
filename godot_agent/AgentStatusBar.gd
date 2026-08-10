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
	if not timer.timeout.is_connected(_on_timer_tick):
		timer.timeout.connect(_on_timer_tick)
	visible = false


func _setup_theme() -> void:
	var accent := _tc("accent_color", "Editor", Color("#ffd54f"))
	var style := StyleBoxFlat.new()
	style.bg_color = _tc("dark_color_1", "Editor", Color("#232333"))
	style.border_color = Color(accent.r, accent.g, accent.b, 0.35)
	style.set_border_width_all(1)
	style.set_corner_radius_all(6)
	add_theme_stylebox_override("panel", style)

	var spinner_icon := _ti("ProgressIndicator")
	if spinner_icon == null:
		spinner_icon = _ti("Progress1")
	if spinner_icon != null:
		spinner.texture = spinner_icon
		spinner.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		spinner.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	spinner.modulate = accent
	# Центр вращения — середина иконки.
	spinner.pivot_offset = spinner.custom_minimum_size / 2.0

	status_label.add_theme_color_override("font_color", _tc("font_color", "Label", Color.WHITE))
	elapsed_label.add_theme_color_override("font_color", _tc("font_disabled_color", "Button", Color(0.6, 0.6, 0.6)))
	chars_label.add_theme_color_override("font_color", _tc("font_disabled_color", "Button", Color(0.6, 0.6, 0.6)))

	timer.wait_time = 0.5
	timer.one_shot = false


func show_status(phase: String, elapsed: int = 0, chars: int = 0) -> void:
	_start_time = Time.get_ticks_msec() - (elapsed * 1000)
	_active = true
	visible = true
	status_label.text = phase
	elapsed_label.text = _format_time(elapsed)
	chars_label.text = ("%s симв." % chars) if chars > 0 else ""
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
		chars_label.text = ("%s симв." % chars) if chars > 0 else ""


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
