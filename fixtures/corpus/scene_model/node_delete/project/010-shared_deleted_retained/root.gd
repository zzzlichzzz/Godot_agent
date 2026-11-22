extends Node
@onready var item = $Old
@onready var tip = $"Old/Tip"
@onready var end = get_node_or_null('Old/Tip/End')
@onready var unique = %Old
func _ready():
    var a = get_node("Old")
    var b = has_node('Old/Tip')
    var c = find_child("Old")
    # $Old stays a literal reference even in this comment during reparent.
@onready var myself = get_node(".")
