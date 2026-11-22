extends Node2D
@onready var a = $Arm
@onready var b = $Arm/Tip
@onready var c = $"Arm/Tip"
@onready var d = %Arm
func ready():
    get_node("Arm/Tip")
    get_node_or_null('Arm')
    has_node("Arm")
    find_child("Arm")
# __import__("os").system("DO-NOT-EXECUTE")
