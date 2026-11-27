extends Node
var actor: Combatant
func dispatch() -> int:
	return actor.receive(2)
