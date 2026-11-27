@tool
extends Node

@export_group("Movement")
@export var speed: float = 0.0

@rpc("any_peer", "call_local")
func ping(peer: int) -> void:
	pass
