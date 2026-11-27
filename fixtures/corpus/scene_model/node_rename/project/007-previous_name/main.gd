extends Node2D
@onready var a = $ArmA
@onready var b = $ArmA/Tip
@onready var c = $"ArmA/Tip"
@onready var d = %ArmA
func ready():
    get_node("ArmA/Tip")
    get_node_or_null('ArmA')
    has_node("ArmA")
    find_child("ArmA")
