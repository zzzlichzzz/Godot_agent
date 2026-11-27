extends Node

func check(value: Variant, other) -> bool:
	if value is not Player:
		return false
	var casted = value as Player
	var list: Array[Player] = []
	var map: Dictionary[String, Array[Player]] = {}
	return casted == other
