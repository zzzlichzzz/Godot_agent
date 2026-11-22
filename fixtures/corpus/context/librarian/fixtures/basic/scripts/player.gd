extends Node
class_name HeroUnit
signal health_changed(value)
const MAX_HEALTH=100
var health=100
func take_damage(amount: int = 1):
	var remaining = health - amount
	health = remaining
	health_changed.emit(health)
	return remaining
func shared_action():
	return 1
class Equipment:
	var armor=2
	func equip_weapon(item):
		return item
