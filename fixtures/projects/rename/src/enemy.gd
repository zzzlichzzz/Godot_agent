extends LabHero

func bite(target) -> void:
	target.take_damage(2)

func bite_unknown(anyone) -> void:
	anyone.take_damage(5)

func roar() -> void:
	super.take_damage(3)
