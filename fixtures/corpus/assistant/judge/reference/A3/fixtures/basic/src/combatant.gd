class_name Combatant
extends Node
signal injured
@export var health: int = 10
const LIMIT = 20
enum Phase { WAIT, ACTIVE }
func receive(amount: int) -> int:
	injured.emit()
	health -= amount
	return health
func loop_call() -> int:
	return self.receive(1)
