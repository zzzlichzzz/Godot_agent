extends Control
const DEFAULT = {"a": [1, 2]}
@export var state: int = 3
func alpha(
	x: Dictionary[String, int] = DEFAULT,
	y = [1, 2]
) -> int:
	var f = func(state: int, other = 0): return state + other
	for index in y:
		state += index
	return f.call(x.size())
