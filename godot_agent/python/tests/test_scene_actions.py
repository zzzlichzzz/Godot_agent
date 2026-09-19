# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import scene_actions


def write(root, rel, text=""):
    absolute = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return absolute


def raises(action, text):
    try:
        action()
    except scene_actions.SceneActionError as exc:
        assert text.lower() in str(exc).lower(), (text, str(exc))
        return
    raise AssertionError("Expected SceneActionError containing %r" % text)


def fixture():
    root = tempfile.mkdtemp(prefix="scene_actions_")
    write(root, "project.godot", "config_version=5\n")
    write(root, "scenes/main.tscn", '[gd_scene format=3]\n\n[node name="Main" type="Node"]\n')
    write(root, "src/hud.gd", "extends CanvasLayer\n")
    return root


def test_full_schema_and_digest_are_deterministic():
    root = fixture()
    try:
        action = {
            "action": "edit_scene", "scene": "res://scenes/main.tscn",
            "summary": "HUD",
            "operations": [
                {"op": "add_node", "parent": ".", "name": "HUD", "type": "CanvasLayer"},
                {"op": "set_node_property", "node": "HUD", "property": "visible",
                 "value": {"type": "bool", "value": True}},
                {"op": "attach_script", "node": "HUD", "script": "res://src/hud.gd"},
                {"op": "add_node", "parent": "HUD", "name": "Button", "type": "Button"},
                {"op": "connect_signal", "source": "HUD/Button", "signal": "pressed",
                 "target": "HUD", "method": "show"},
                {"op": "reparent_node", "node": "HUD/Button", "new_parent": ".",
                 "keep_global_transform": False},
            ],
        }
        normalized, absolute = scene_actions.normalize_action(root, action)
        assert absolute.endswith(os.path.join("scenes", "main.tscn"))
        assert normalized["operations"][1]["value"] == {"type": "bool", "value": True}
        assert scene_actions.canonical_digest(normalized) == scene_actions.canonical_digest(
            dict(reversed(list(normalized.items()))))
        prepared = scene_actions.prepare(root, action)
        assert prepared["before_hash"] == scene_actions.file_sha256(absolute)
        public = scene_actions.public_prepared(prepared)
        assert public["prepare_in_editor"] is True
        assert "before_hash" not in public and "action" not in public
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_paths_variants_and_unknown_fields_are_rejected():
    root = fixture()
    try:
        base = {"action": "edit_scene", "scene": "res://scenes/main.tscn"}
        for bad_path in ("/root/HUD", "../HUD", "HUD//Label", "HUD/", "%HUD"):
            action = dict(base, operations=[{
                "op": "set_node_property", "node": bad_path, "property": "visible",
                "value": {"type": "bool", "value": True},
            }])
            raises(lambda action=action: scene_actions.normalize_action(root, action), "node")
        raises(lambda: scene_actions.normalize_variant({"type": "Vector3", "value": [1, 2]}),
               "массив")
        raises(lambda: scene_actions.normalize_variant({"type": "float", "value": float("inf")}),
               "конечное")
        raises(lambda: scene_actions.normalize_action(root, dict(base, operations=[{
            "op": "add_node", "parent": ".", "name": "HUD", "type": "Node", "extra": 1,
        }])), "неизвестные")
        raises(lambda: scene_actions.normalize_action(root, dict(base, operations=[])), "от 1")
        raises(lambda: scene_actions.normalize_action(root, dict(base, operations=[{
            "op": "attach_script", "node": ".", "script": "res://src/missing.gd",
        }])), "не найден")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_sequence_and_addon_policy_are_conservative():
    root = fixture()
    try:
        write(root, "addons/demo/tool.tscn", '[gd_scene format=3]\n')
        raises(lambda: scene_actions.normalize_action(root, {
            "action": "edit_scene", "scene": "res://addons/demo/tool.tscn",
            "operations": [{"op": "add_node", "parent": ".", "name": "N", "type": "Node"}],
        }), "явному запросу")
        scene_actions.normalize_action(root, {
            "action": "edit_scene", "scene": "res://addons/demo/tool.tscn",
            "operations": [{"op": "add_node", "parent": ".", "name": "N", "type": "Node"}],
        }, allow_addons=True)
        raises(lambda: scene_actions.normalize_action(root, {
            "action": "edit_scene", "scene": "res://scenes/main.tscn",
            "operations": [
                {"op": "reparent_node", "node": "HUD", "new_parent": "."},
                {"op": "set_node_property", "node": "HUD", "property": "visible",
                 "value": {"type": "bool", "value": True}},
            ],
        }), "старый путь")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_create_scene_schema_requires_absent_target_and_existing_script():
    root = fixture()
    try:
        action = {
            "action": "create_scene", "scene": "res://scenes/player.tscn",
            "root": {"name": "Player", "type": "CharacterBody2D",
                     "script": "res://src/hud.gd"},
            "operations": [], "summary": "Player scene",
        }
        normalized, absolute = scene_actions.normalize_action(root, action)
        assert normalized["root"]["type"] == "CharacterBody2D"
        assert not os.path.exists(absolute)
        prepared = scene_actions.prepare(root, action)
        assert prepared["before_hash"] is None
        assert scene_actions.public_prepared(prepared)["expected_scene_hash"] == ""
        assert scene_actions.operation_summary(normalized)[0].startswith("0. создать корень")
        write(root, "scenes/player.tscn", "collision")
        raises(lambda: scene_actions.normalize_action(root, action), "уже существует")
        action["scene"] = "res://scenes/missing_script.tscn"
        action["root"]["script"] = "res://src/missing.gd"
        raises(lambda: scene_actions.normalize_action(root, action), "не найден")
        action["root"] = {"name": "Bad/Name", "type": "Node"}
        raises(lambda: scene_actions.normalize_action(root, action), "корня")
        action["root"] = {"name": "Main", "type": "Node"}
        action["summary"] = "x" * 501
        raises(lambda: scene_actions.normalize_action(root, action), "summary")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_all():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All scene action tests passed: %d" % len(tests))


if __name__ == "__main__":
    run_all()
