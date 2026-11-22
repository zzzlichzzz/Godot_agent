extends Control
var state = 2
func alpha():
	var first := get_tree()
	var second := first
	var third := [
		second,
		self
	]
	var safe := 1
	return third
