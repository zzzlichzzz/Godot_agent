extends Node2D

@export var score: int = 3

func on_timeout() -> void:
	score += 1
