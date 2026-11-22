class_name Unit
extends Node

signal died(who: String)

const MAX_HP := 10
@export var speed: float = 1.0
@export_range(0, 10) var armor: int = 0
static var registry: Dictionary = {}
var roster: Dictionary[String, Player] = {}

enum State { IDLE, RUN = 2, JUMP }

func _ready() -> void:
	var unit: Unit = self
	unit.take_damage(1)

static func make(speed: float) -> Unit:
	return Unit.new()
