extends Node

class Inner extends RefCounted:
	var value: int = 0

	func bump() -> int:
		value += 1
		return value

func make_inner() -> Inner:
	return Inner.new()
