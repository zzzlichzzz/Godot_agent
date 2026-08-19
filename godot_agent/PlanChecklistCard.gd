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


# Цвета и стили — единый модуль agent_theme.gd.
static var _theme_script = null
# Словарь надписей — agent_locale.gd. Держим отдельной ссылкой от темы: тема
# может не загрузиться (сцена открыта в редакторе), а надписи нужны всегда.
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
	if not pause_btn.pressed.is_connected(_on_pause_pressed):
		pause_btn.pressed.connect(_on_pause_pressed)
	if not continue_btn.pressed.is_connected(_on_continue_pressed):
		continue_btn.pressed.connect(_on_continue_pressed)
	if not rollback_btn.pressed.is_connected(_on_rollback_pressed):
		rollback_btn.pressed.connect(_on_rollback_pressed)
	_apply_locale()


func _apply_locale() -> void:
	# Надписи кнопок лежат в .tscn по-русски (так их видно в редакторе сцен), и
	# на экране остаются ровно до того, как код их перепишет. Раньше их не
	# переписывал никто — «Пауза», «Продолжить» и «Откатить цепочку» оставались
	# русскими при английском языке. Ставим все три здесь, списком: тогда забыть
	# одну нельзя.
	pause_btn.text = _t("plan_pause")
	continue_btn.text = _t("plan_continue")
	rollback_btn.text = _t("plan_rollback_chain")


func _setup_theme() -> void:
	var T = _T()
	if T == null:
		return
	# Сцена открыта во вкладке редактора — оформление не применяем, иначе
	# Godot запечёт иконки и шрифты в .tscn при сохранении (см. is_edited_scene).
	if T.is_edited_scene(self):
		return
	# Фон плана — bg_1 (как было: dark_color_1), рамка акцентная.
	add_theme_stylebox_override("panel", T.make_panel_style(T.color("bg_1"), T.alpha("accent", 0.35), 8, 12, 8))

	title_label.add_theme_color_override("font_color", T.color("text"))
	title_label.add_theme_font_size_override("font_size", T.font_size("Label", 14) + 1)

	var bg_style := StyleBoxFlat.new()
	bg_style.bg_color = T.color("bg_3")
	bg_style.set_corner_radius_all(4)
	progress_bar.add_theme_stylebox_override("background", bg_style)
	var fill_style := StyleBoxFlat.new()
	fill_style.bg_color = T.color("accent")
	fill_style.set_corner_radius_all(4)
	progress_bar.add_theme_stylebox_override("fill", fill_style)

	for btn: Button in [pause_btn, continue_btn, rollback_btn]:
		T.style_button(btn, "neutral")


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
