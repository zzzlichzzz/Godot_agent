"""New cases from captured native applications, not native test code."""
import hashlib

ANIMATION = b'[gd_resource type="Animation" format=3 uid="uid://c24probe1"]\n\n; input comment must not be mistaken for an operation\n[resource]\nresource_name = "Preserve this name"\nlength = 1.0'
THEME = b'[gd_resource type="Theme" load_steps=2 format=3 uid="uid://c24probe2"]\r\n\r\n; keep spacing and comment in proposed textual variant\r\n[ext_resource type="Texture2D" path="res://old.tres" id="old_texture"]\r\n\r\n[resource]\r\ndefault_font_size = 16\r\nButton/icons/probe_icon = ExtResource("old_texture")\r\n'
SPRITE = b'[gd_resource type="SpriteFrames" format=3 uid="uid://c24probe3"]\r\r[resource]\r'
TILESET = b'[gd_resource type="TileSet" format=3 uid="uid://c24probe4"]\n\n[resource]\n'
TEXTURE = b'[gd_resource type="GradientTexture2D" format=3]\n\n[resource]\nwidth = 64\nheight = 64\n'
DEPENDENCIES = {"res://old.tres": TEXTURE, "res://new.tres": TEXTURE}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def tagged(kind, value):
    return {"type": kind, "value": value}


CASES = [
    ("set_property", ANIMATION, {"op": "set_property", "target": [], "property": "length", "value": tagged("float", 2.0)}, b"length = 2.0"),
    ("replace_reference", THEME, {"op": "replace_reference", "target": [], "old": "res://old.tres", "new": "res://new.tres", "expected_count": 1}, b'path="res://new.tres"'),
    ("animation_add_value_track", ANIMATION, {"op": "animation_add_value_track", "path": "Node:position", "keys": [{"time": 0.0, "value": tagged("Vector2", [0.0, 0.0])}, {"time": 1.0, "value": tagged("Vector2", [2.0, 3.0])}]}, b'tracks/0/type = "value"'),
    ("sprite_frames_add_animation", SPRITE, {"op": "sprite_frames_add_animation", "name": "walk", "fps": 12, "loop": True, "frames": [{"texture": tagged("ResourcePath", "res://new.tres"), "duration": 1.5}]}, b'"name": &"walk"'),
    ("theme_set_item", THEME, {"op": "theme_set_item", "data_type": "stylebox", "theme_type": "Button", "name": "probe_style", "value": {"type": "NewSubresource", "class": "StyleBoxFlat", "properties": [{"property": "bg_color", "value": tagged("Color", [0.2, 0.3, 0.4, 1.0])}]}}, b"Button/styles/probe_style = SubResource("),
    ("tileset_add_atlas_source", TILESET, {"op": "tileset_add_atlas_source", "source_id": 7, "texture": tagged("ResourcePath", "res://new.tres"), "texture_region_size": [16, 16], "tiles": [[0, 0], [1, 0]]}, b"sources/7 = SubResource("),
]


def action(operation, resource="res://data.tres"):
    return {"action": "edit_resource", "resource": resource, "operations": [operation]}


def context(tmp_path, raw=ANIMATION):
    from python.kernel.paths import PathPolicy
    from python.runtime.bootstrap import build_agent, default_ports
    from python.runtime.context import ModuleContext
    project, state = tmp_path / "project", tmp_path / "state"
    project.mkdir(exist_ok=True)
    (project / "data.tres").write_bytes(raw)
    for name in ("old.tres", "new.tres"):
        (project / name).write_bytes(TEXTURE)
    ports = default_ports(str(project), "test", str(state))
    agent = build_agent(str(project), "test", state_dir=str(state), ports=ports)
    ctx = ModuleContext("test", ports=ports, path_policy=PathPolicy(str(project)), call_tool=agent._dispatcher.call)
    return project, ctx, agent
