extends Node
@onready var item = $New/Old
@onready var tip = $"New/Old/Tip"
@onready var end = get_node_or_null('New/Old/Tip/End')
@onready var unique = %Old
func _ready():
    var a = get_node("New/Old")
    var b = has_node('New/Old/Tip')
    var c = find_child("Old")
    # $New/Old stays a literal reference even in this comment during reparent.
