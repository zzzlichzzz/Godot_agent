extends Node

# reset() is never called, and that is fine.

func run(entity: LabEntity) -> void:
	entity.take_damage(9)  # take_damage in a comment is not a usage
	print("take_damage")
	entity.call("take_damage", 1)

func inspect(value: Variant) -> void:
	if value is LabEntity:
		pass
	var copy = value as LabEntity
	print(LabEntity.new())

# fire() is not called anywhere yet.
