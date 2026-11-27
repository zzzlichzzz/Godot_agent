extends RefCounted

## Лаборатория функций: порядок объявления, static, дубли, аннотации, вложенный класс.
var counter := 0


func _process(delta: float) -> void:
	counter += 1


static func make() -> RefCounted:
	return RefCounted.new()


func compute_score(value: int) -> int:
	return value * 2


# Прилегающий комментарий: он входит в сниппет функции ниже.
# Второй комментарий тоже.
@tool
@rpc("any_peer")
func rpc_ping() -> void:
	pass


func spaced_lines() -> int:
	var first := 1

	var second := 2
	return first + second



class Inner:
	func inner_helper() -> String:
		return "inner"


# func fake() -> void:
# 	pass
func duplicated() -> String:
	return "first"


func duplicated() -> String:
	return "second"
