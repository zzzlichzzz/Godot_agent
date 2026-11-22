extends RefCounted

# Вложенная функция: видна в списке имён, тело по запросу не извлекается.
func nested_outer() -> int:
	var total := 0
	func nested_inner() -> int:
		return 1
	total += 1
	return total


func nested_after() -> void:
	pass
