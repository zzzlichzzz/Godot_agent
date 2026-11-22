extends Node
@export var title: String
@onready var node = null
signal custom_signal
@rpc("any_peer")
func ping():
	pass
