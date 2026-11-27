extends Node

var counter: int = 0

func bump() -> void:
	counter += 1

func shadowed() -> void:
	var counter := 5
	counter += 1
