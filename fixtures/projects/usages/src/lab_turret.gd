extends LabEntity

func take_damage(amount: int) -> int:
	return super.take_damage(amount)

func fire() -> void:
	take_damage(1)
