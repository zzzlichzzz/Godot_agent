extends Node
func attack(target):
	target.take_damage(2)
	target.call("take_damage", 3)
	target.take_damage.bind(4).call()
	target.health_changed.connect(_on_health_changed)
	await target.health_changed
func _on_health_changed(value):
	print(value)
func shared_action():
	return 2
