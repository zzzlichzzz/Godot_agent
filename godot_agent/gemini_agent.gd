@tool
extends EditorPlugin

var dock_panel

func _enter_tree() -> void:
	# ВНИМАНИЕ: Здесь теперь прописан ваш НОВЫЙ путь до файла сцены (.tscn)
	dock_panel = preload("res://addons/Godot_agent/godot_agent/agent_panel.tscn").instantiate()
	
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, dock_panel)

func _exit_tree() -> void:
	if dock_panel:
		remove_control_from_docks(dock_panel)
		dock_panel.queue_free()
