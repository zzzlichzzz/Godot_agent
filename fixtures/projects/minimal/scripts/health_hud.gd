class_name HealthHud
extends Control

signal HealthChanged(value: int)

@onready var label: Label = $Label


func set_Health(value: int) -> void:
	label.text = "HP: %d" % value
	HealthChanged.emit(value)
