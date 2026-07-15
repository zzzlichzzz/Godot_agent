@tool
extends EditorPlugin

# Переменная, в которой мы будем хранить нашу сцену
var dock_panel

func _enter_tree() -> void:
	# 1. Загружаем сцену, которую мы только что создали
	dock_panel = preload("res://addons/gemini_agent/agent_panel.tscn").instantiate()
	
	# 2. Добавляем её в правую часть редактора (DOCK_SLOT_RIGHT_UL - это там же, где Инспектор)
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, dock_panel)

func _exit_tree() -> void:
	# 1. Убираем панель из редактора при выключении плагина
	if dock_panel:
		remove_control_from_docks(dock_panel)
		# 2. Удаляем её из памяти
		dock_panel.queue_free()
