class_name LabEntity
extends Node

signal damaged(amount: int)

const MAX_HP := 100

var hp: int = 0

enum State { IDLE, RUN }

func take_damage(amount: int) -> int:
	hp -= amount
	damaged.emit(amount)
	return hp

func reset() -> void:
	hp = MAX_HP

static func make() -> LabEntity:
	return LabEntity.new()
