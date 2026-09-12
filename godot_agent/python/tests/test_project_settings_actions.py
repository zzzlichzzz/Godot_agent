# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401
import project_settings_actions as actions


def write(root, rel, text=""):
    absolute = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return absolute


def fixture():
    root = tempfile.mkdtemp(prefix="project_settings_actions_")
    write(root, "project.godot", "config_version=5\n")
    write(root, "src/game_state.gd", "extends Node\n")
    write(root, "scenes/main.tscn", '[gd_scene format=3]\n\n[node name="Main" type="Node"]\n')
    return root


def raises(callback, expected):
    try:
        callback()
    except actions.ProjectSettingsActionError as exc:
        assert expected.lower() in str(exc).lower(), (expected, str(exc))
        return
    raise AssertionError("Expected ProjectSettingsActionError containing %r" % expected)


def test_full_schema_digest_and_prepare():
    root = fixture()
    try:
        action = {"action": "edit_project_settings", "summary": "Bootstrap", "operations": [
            {"op": "add_input_action", "name": "jump", "deadzone": 0.25},
            {"op": "add_input_event", "action": "jump",
             "event": {"type": "key", "key": "space", "physical": True}},
            {"op": "add_autoload", "name": "GameState", "path": "res://src/game_state.gd"},
            {"op": "set_main_scene", "scene": "res://scenes/main.tscn"},
            {"op": "set_layer_name", "layer": "2d_physics", "index": 1, "name": "Player"},
            {"op": "set_display_settings", "viewport_width": 1280,
             "viewport_height": 720, "stretch_mode": "canvas_items"},
        ]}
        normalized, project_file = actions.normalize_action(root, action)
        assert normalized["operations"][1]["event"]["key"] == "SPACE"
        assert actions.canonical_digest(normalized) == actions.canonical_digest(
            dict(reversed(list(normalized.items()))))
        prepared = actions.prepare(root, action)
        assert prepared["before_hash"] == actions.file_sha256(project_file)
        public = actions.public_prepared(prepared)
        assert public["prepare_in_editor"] is True and "action" not in public
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_invalid_events_fields_and_ranges_are_rejected():
    root = fixture()
    try:
        base = {"action": "edit_project_settings"}
        raises(lambda: actions.normalize_action(root, dict(base, operations=[])), "от 1")
        raises(lambda: actions.normalize_action(root, dict(base, operations=[{
            "op": "add_input_action", "name": "bad name"}])), "InputMap")
        raises(lambda: actions.normalize_action(root, dict(base, operations=[{
            "op": "add_input_event", "action": "jump",
            "event": {"type": "joypad_motion", "axis": 0, "axis_value": float("inf")}}])),
            "axis_value")
        raises(lambda: actions.normalize_action(root, dict(base, operations=[{
            "op": "set_layer_name", "layer": "2d_physics", "index": 40, "name": "X"}])),
            "диапазона")
        raises(lambda: actions.normalize_action(root, dict(base, operations=[{
            "op": "set_display_settings", "renderer": "gl_compatibility"}])), "неизвестные")
        raises(lambda: actions.normalize_action(root, dict(base, operations=[{
            "op": "set_main_scene", "scene": "res://scenes/missing.tscn"}])), "не найден")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_addon_and_sequence_policy_are_conservative():
    root = fixture()
    try:
        write(root, "addons/demo/tool.gd", "extends Node\n")
        action = {"action": "edit_project_settings", "operations": [{
            "op": "add_autoload", "name": "Tool", "path": "res://addons/demo/tool.gd"}]}
        raises(lambda: actions.normalize_action(root, action), "явному запросу")
        actions.normalize_action(root, action, allow_addons=True)
        raises(lambda: actions.normalize_action(root, {
            "action": "edit_project_settings", "operations": [
                {"op": "add_autoload", "name": "Temp", "path": "res://src/game_state.gd"},
                {"op": "remove_autoload", "name": "Temp"},
            ]}), "той же транзакцией")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_all():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All project settings action tests passed: %d" % len(tests))


if __name__ == "__main__":
    run_all()
