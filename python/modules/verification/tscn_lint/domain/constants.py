"""C.8 literal rule vocabulary; specification port, ba0535d4 tscn_lint.py."""
_NODE_CLASSES = {'Node', 'Node2D', 'Node3D', 'Control', 'CanvasLayer', 'ColorRect', 'TextureRect', 'Label', 'RichTextLabel', 'Button', 'TextureButton', 'Panel', 'PanelContainer', 'NinePatchRect', 'VBoxContainer', 'HBoxContainer', 'GridContainer', 'MarginContainer', 'CenterContainer', 'ScrollContainer', 'ProgressBar', 'LineEdit', 'TextEdit', 'ItemList', 'OptionButton', 'CheckBox', 'CheckButton', 'Sprite2D', 'AnimatedSprite2D', 'Camera2D', 'CollisionShape2D', 'CollisionPolygon2D', 'Area2D', 'CharacterBody2D', 'RigidBody2D', 'StaticBody2D', 'AnimatableBody2D', 'AnimationPlayer', 'Timer', 'AudioStreamPlayer', 'AudioStreamPlayer2D', 'TileMap', 'TileMapLayer', 'Marker2D', 'Path2D', 'PathFollow2D', 'RayCast2D', 'VisibleOnScreenNotifier2D'}
_VARIANT_TYPES = {'Color', 'Vector2', 'Vector2i', 'Vector3', 'Vector3i', 'Vector4', 'Vector4i', 'Rect2', 'Rect2i', 'Transform2D', 'Transform3D', 'Quaternion', 'Basis', 'Plane', 'AABB', 'String', 'StringName', 'NodePath', 'bool', 'int', 'float', 'Array', 'Dictionary', 'PackedByteArray', 'PackedInt32Array', 'PackedInt64Array', 'PackedFloat32Array', 'PackedFloat64Array', 'PackedStringArray', 'PackedVector2Array', 'PackedVector3Array', 'PackedColorArray'}
_CHUNK_TYPE_RANK = {'gd_scene': 0, 'ext_resource': 1, 'sub_resource': 2, 'resource': 2, 'node': 3, 'connection': 4}
_COLLISION_SHAPE_2D = {'CollisionShape2D', 'CollisionPolygon2D'}
_COLLISION_SHAPE_3D = {'CollisionShape3D', 'CollisionPolygon3D'}
_COLLISION_OWNER_2D = {'Area2D', 'StaticBody2D', 'AnimatableBody2D', 'CharacterBody2D', 'RigidBody2D', 'PhysicsBody2D', 'PhysicalBone2D'}
_COLLISION_OWNER_3D = {'Area3D', 'StaticBody3D', 'AnimatableBody3D', 'CharacterBody3D', 'RigidBody3D', 'VehicleBody3D', 'PhysicsBody3D', 'PhysicalBone3D'}
_RESOURCE_PROPS = ('mesh', 'texture', 'material', 'material_override', 'shader', 'environment', 'sky', 'font', 'skeleton', 'skin', 'animation', 'sprite_frames', 'stylebox', 'shape', 'script')
_SCENE_EXTS = ('.tscn', '.scn', '.res')
_BAD_NAME_CHARS_V83 = set('./:@%"')
