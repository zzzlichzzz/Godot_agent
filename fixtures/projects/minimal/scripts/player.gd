extends CharacterBody2D

## Игрок: запас сил, урон, смерть.
var health := 100
var health_max := 100
var speed := 300.0


func _ready() -> void:
	health = health_max
	position = Vector2.ZERO


func take_damage(amount: int) -> void:
	health = max(0, health - amount)
	if health == 0:
		die()


func die() -> void:
	queue_free()
