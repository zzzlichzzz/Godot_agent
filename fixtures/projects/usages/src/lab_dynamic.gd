extends Node

func hit(target) -> void:
	target.hit(1)

func call_dynamic(unknown) -> void:
	unknown.hit(2)
