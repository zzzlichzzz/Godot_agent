extends Node2D
func ready():
    find_child("Arm")
    get_node("../Tip")
