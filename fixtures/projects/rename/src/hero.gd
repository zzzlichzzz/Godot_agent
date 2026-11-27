class_name LabHero
extends Node

var hp: int = 10

func take_damage(amount: int) -> int:
	hp -= amount
	return hp

func strike() -> void:
	take_damage(1)
