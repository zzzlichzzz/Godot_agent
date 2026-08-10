@tool
extends HBoxContainer
class_name PlanStepItem

@onready var status_icon: TextureRect = $StatusIcon
@onready var step_label: Label = $StepLabel
@onready var description_label: Label = $DescriptionLabel

var _spin_tween: Tween = null


# Цвета и иконки — единый модуль agent_theme.gd.
static var _theme_script = null


func _T():
	if _theme_script == null:
		var sc := get_script() as Script
		if sc:
			var p := sc.resource_path.get_base_dir() + "/agent_theme.gd"
			if FileAccess.file_exists(p):
				_theme_script = load(p)
	return _theme_script


func _ready() -> void:
	_setup_theme()


func _exit_tree() -> void:
	stop_spinner()


func _setup_theme() -> void:
	var T = _T()
	if T == null:
		return
	# Сцена открыта во вкладке редактора — оформление не применяем, иначе
	# Godot запечёт иконки и шрифты в .tscn при сохранении (см. is_edited_scene).
	if T.is_edited_scene(self):
		return
	step_label.add_theme_color_override("font_color", T.color("text"))
	description_label.add_theme_color_override("font_color", T.color("dim"))
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
	var T = _T()
	if T == null:
		return
	match status:
		"done":
			_set_icon("StatusSuccess", T.color("success"))
		"active", "running", "working":
			_set_icon("Progress1", T.color("accent"))
			if is_current:
				_animate_spinner()
		"error", "failed":
			_set_icon("StatusError", T.color("error"))
		_:
			_set_icon("GuiRadioUnchecked", T.color("dim"))


func _set_icon(icon_name: StringName, tint: Color) -> void:
	var T = _T()
	if T == null:
		return
	var icon: Texture2D = T.first_icon([icon_name, "StatusWarning"])
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
