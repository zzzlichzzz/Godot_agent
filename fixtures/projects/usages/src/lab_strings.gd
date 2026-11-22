extends Node

func trigger(node: Node) -> void:
	node.call("on_hit", 1)

func on_hit() -> void:
	pass
