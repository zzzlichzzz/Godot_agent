@tool
extends HBoxContainer
class_name PlanStepItem

@onready var status_icon: TextureRect = $StatusIcon
@onready var step_label: Label = $StepLabel
@onready var description_label: Label = $DescriptionLabel

var _spin_tween: Tween = null


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


func _exit_tree() -> void:
	stop_spinner()


func _setup_theme() -> void:
	step_label.add_theme_color_override("font_color", _tc("font_color", "Label", Color.WHITE))
	description_label.add_theme_color_override("font_color", _tc("font_disabled_color", "Button", Color(0.62, 0.62, 0.62)))
	description_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART


func setup(step_num: int, description: String, is_current: bool = false) -> void:
	step_label.text = "%d." % step_num
	description_label.text = description
	_update_icon(is_current, "pending")


func update_status(index: int, current_index: int, status: String) -> void:
	if index < current_index:
		_update_icon(false, "done")
	elif index == current_index:
		_update_icon(true, status)
	else:
		_update_icon(false, "pending")


func _update_icon(is_current: bool, status: String) -> void:
	stop_spinner()
	match status:
		"done":
			_set_icon("StatusSuccess", _tc("success_color", "Editor", Color("#7ddc84")))
		"active", "running", "working":
			_set_icon("Progress1", _tc("accent_color", "Editor", Color("#ffd54f")))
			if is_current:
				_animate_spinner()
		"error", "failed":
			_set_icon("StatusError", _tc("error_color", "Editor", Color("#f44336")))
		_:
			_set_icon("GuiRadioUnchecked", Color(0.5, 0.5, 0.5))


func _set_icon(icon_name: StringName, tint: Color) -> void:
	var icon := _ti(icon_name)
	if icon == null:
		icon = _ti("StatusWarning")
	status_icon.visible = icon != null
	if icon != null:
		status_icon.texture = icon
	status_icon.modulate = tint


func _animate_spinner() -> void:
	stop_spinner()
	if not is_inside_tree():
		return
	# pivot_offset нужен до старта: иначе иконка вращается вокруг левого угла.
	status_icon.pivot_offset = status_icon.custom_minimum_size / 2.0
	_spin_tween = create_tween().set_loops()
	_spin_tween.tween_property(status_icon, "rotation", TAU, 1.2).from(0.0)


func stop_spinner() -> void:
	if _spin_tween != null and _spin_tween.is_valid():
		_spin_tween.kill()
	_spin_tween = null
	if is_instance_valid(status_icon):
		status_icon.rotation = 0.0
