# plugin.gd - вход плагина. Тонкая обёртка, логики здесь нет.
# Правила: R-01 (всё внутри папки), R-14 (мост не содержит логики фич).
# `@tool` обязателен: без него редактор не инстанцирует скрипт плагина (4.6).
@tool
extends EditorPlugin

const LifecycleScript := preload("res://addons/godot_agent/editor/core/lifecycle.gd")
const T1PanelScript := preload("res://addons/godot_agent/editor/t1_panel.gd")

var _lifecycle = null
var _panel: Control = null


func _enter_tree() -> void:
	_lifecycle = LifecycleScript.new()
	add_child(_lifecycle)
	var started: Dictionary = _lifecycle.start()
	if not bool(started.get("ok", false)):
		push_warning("godot_agent: bridge start failed: %s" % str(started))
	_panel = T1PanelScript.new()
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _panel)
	print("T1_PLUGIN_READY")


func _exit_tree() -> void:
	if _panel != null:
		remove_control_from_docks(_panel)
		_panel.queue_free()
		_panel = null
	if _lifecycle == null:
		return
	_lifecycle.stop()
	_lifecycle.queue_free()
	_lifecycle = null
