@tool
extends PanelContainer
class_name PlanChecklistCard

@onready var title_label: Label = $RootVBox/TitleLabel
@onready var progress_bar: ProgressBar = $RootVBox/ProgressBar
@onready var steps_container: VBoxContainer = $RootVBox/StepsContainer
@onready var controls_box: HBoxContainer = $RootVBox/ControlsBox
@onready var pause_btn: Button = $RootVBox/ControlsBox/PauseButton
@onready var continue_btn: Button = $RootVBox/ControlsBox/ContinueButton
@onready var rollback_btn: Button = $RootVBox/ControlsBox/RollbackButton

var _steps: Array = []
var _current_step: int = 0
var _total_steps: int = 0
var _paused: bool = false

signal plan_paused
signal plan_continued
signal plan_rollback_requested


func _tc(theme_item: StringName, theme_type: StringName, fallback: Color) -> Color:
	if has_theme_color(theme_item, theme_type):
		return get_theme_color(theme_item, theme_type)
	return fallback


func _tfs(theme_item: StringName, theme_type: StringName, fallback: int) -> int:
	if has_theme_font_size(theme_item, theme_type):
		return get_theme_font_size(theme_item, theme_type)
	return fallback


func _ready() -> void:
	_setup_theme()
	if not pause_btn.pressed.is_connected(_on_pause_pressed):
		pause_btn.pressed.connect(_on_pause_pressed)
	if not continue_btn.pressed.is_connected(_on_continue_pressed):
		continue_btn.pressed.connect(_on_continue_pressed)
	if not rollback_btn.pressed.is_connected(_on_rollback_pressed):
		rollback_btn.pressed.connect(_on_rollback_pressed)


func _setup_theme() -> void:
	var accent := _tc("accent_color", "Editor", Color("#ffd54f"))
	var style := StyleBoxFlat.new()
	style.bg_color = _tc("dark_color_1", "Editor", Color("#232333"))
	style.border_color = Color(accent.r, accent.g, accent.b, 0.35)
	style.set_border_width_all(1)
	style.set_corner_radius_all(8)
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 8
	style.content_margin_bottom = 8
	add_theme_stylebox_override("panel", style)

	title_label.add_theme_color_override("font_color", _tc("font_color", "Label", Color.WHITE))
	title_label.add_theme_font_size_override("font_size", _tfs("font_size", "Label", 14) + 1)

	var bg_style := StyleBoxFlat.new()
	bg_style.bg_color = _tc("dark_color_3", "Editor", Color("#2a2a3a"))
	bg_style.set_corner_radius_all(4)
	progress_bar.add_theme_stylebox_override("background", bg_style)
	var fill_style := StyleBoxFlat.new()
	fill_style.bg_color = accent
	fill_style.set_corner_radius_all(4)
	progress_bar.add_theme_stylebox_override("fill", fill_style)

	for btn: Button in [pause_btn, continue_btn, rollback_btn]:
		btn.flat = true
		btn.add_theme_color_override("font_color", _tc("font_color", "Button", Color.WHITE))
		btn.add_theme_color_override("font_hover_color", accent)


func setup(plan_title: String, steps: Array) -> void:
	_steps = steps
	_total_steps = steps.size()
	_current_step = 0
	title_label.text = plan_title
	# max_value = 0 ломает ProgressBar, поэтому минимум 1.
	progress_bar.max_value = maxi(_total_steps, 1)
	progress_bar.value = 0

	for child in steps_container.get_children():
		steps_container.remove_child(child)
		child.queue_free()

	var packed := _step_scene()
	for i in range(_total_steps):
		if packed == null:
			break
		var step_item := packed.instantiate() as PlanStepItem
		if step_item == null:
			continue
		steps_container.add_child(step_item)
		step_item.setup(i + 1, str(steps[i]), i == 0)


func _step_scene() -> PackedScene:
	var sc := get_script() as Script
	if sc == null:
		return null
	var path := sc.resource_path.get_base_dir() + "/PlanStepItem.tscn"
	if not FileAccess.file_exists(path):
		return null
	return load(path) as PackedScene


func update_step(step_index: int, status: String) -> void:
	_current_step = step_index
	progress_bar.value = clampf(float(step_index + 1), 0.0, progress_bar.max_value)
	for i in range(steps_container.get_child_count()):
		var child := steps_container.get_child(i) as PlanStepItem
		if child:
			child.update_status(i, step_index, status)


func set_paused(paused: bool) -> void:
	_paused = paused
	pause_btn.visible = not paused
	continue_btn.visible = paused


func _on_pause_pressed() -> void:
	set_paused(true)
	plan_paused.emit()


func _on_continue_pressed() -> void:
	set_paused(false)
	plan_continued.emit()


func _on_rollback_pressed() -> void:
	plan_rollback_requested.emit()
