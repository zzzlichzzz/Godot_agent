extends Node

var hero

func hit() -> void:
	hero.take_damage(4)

func hit_by_name() -> void:
	hero.call("take_damage", 1)

func peek() -> int:
	return hero.hp
