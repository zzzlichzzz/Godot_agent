# -*- coding: utf-8 -*-
import copy
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import high_level_actions as actions
import parser_base


def write(root, rel, text):
    absolute = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def project():
    root = tempfile.mkdtemp(prefix="high_level_project_")
    write(root, "project.godot", "config_version=5\n")
    write(root, "scenes/main.tscn", '[gd_scene format=3]\n\n[node name="Main" type="Node"]\n')
    write(root, "src/health.gd", "extends Node\nsignal died\n")
    write(root, "src/game_state.gd", "extends Node\n")
    write(root, "src/player.gd", "extends Node\nfunc run():\n\tpass\n")
    return root


def test_scene_component_compiles_in_safe_order():
    root = project()
    try:
        source = {"action": "project_command", "summary": "health", "command": {
            "type": "create_scene_component", "scene": "res://scenes/main.tscn",
            "parent": ".", "name": "Health", "node_type": "Node",
            "script": "res://src/health.gd",
            "properties": [{"name": "process_mode", "value": {"type": "int", "value": 0}}],
            "signals": [{"signal": "died", "target": ".", "method": "_on_health_died"}]}}
        before = copy.deepcopy(source)
        compiled = actions.compile_action(root, source)
        assert source == before
        assert compiled["action"] == "edit_scene"
        assert [item["op"] for item in compiled["operations"]] == [
            "add_node", "attach_script", "set_node_property", "connect_signal"]
        assert all(item.get("node", item.get("source")) == "Health"
                   for item in compiled["operations"][1:])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_settings_rename_and_atomic_compilers():
    root = project()
    try:
        input_action = actions.compile_action(root, {"action": "project_command", "command": {
            "type": "create_input_action", "name": "jump", "events": [
                {"type": "key", "key": "space", "physical": True}]}})
        assert [item["op"] for item in input_action["operations"]] == [
            "add_input_action", "add_input_event"]
        assert input_action["operations"][1]["event"]["key"] == "SPACE"
        autoload = actions.compile_action(root, {"action": "project_command", "command": {
            "type": "register_autoload", "name": "GameState", "path": "res://src/game_state.gd"}})
        assert autoload["operations"] == [{"op": "add_autoload", "name": "GameState",
                                            "path": "res://src/game_state.gd"}]
        rename = actions.compile_action(root, {"action": "project_command", "command": {
            "type": "rename_symbol", "kind": "function",
            "declaration": "res://src/player.gd:2", "old_name": "run", "new_name": "start"}})
        assert rename["action"] == "rename_symbol" and rename["declaration"].endswith(":2")
        atomic = actions.compile_action(root, {"action": "project_command", "command": {
            "type": "atomic_files", "operations": [{"action": "patch_file",
                "path": "res://src/player.gd", "search": "pass", "replace": "print(1)"}]}})
        assert atomic["action"] == "transaction" and len(atomic["operations"]) == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_schema_parser_refs_and_no_writes():
    root = project()
    try:
        with open(os.path.join(root, "src", "player.gd"), "rb") as handle:
            before = handle.read()
        raw = ("```agent_action\n{\"action\":\"project-command\",\"command\":{"
               "\"type\":\"atomic_files\",\"operations\":[{\"action\":\"Create\","
               "\"path\":\"res://src/new.gd\",\"content_ref\":\"BODY\","
               "\"content_ref_lines\":1}]}}\n===BODY===\nextends Node\n===END_BODY===\n```\n===DONE===")
        parsed, error = parser_base.parse_action_json(raw)
        assert error is None and parsed["action"] == "project_command"
        assert parsed["command"]["operations"][0]["action"] == "create_file"
        assert parsed["command"]["operations"][0]["content"] == "extends Node"
        for bad in (
                {"action": "project_command", "command": {"type": "unknown"}},
                {"action": "project_command", "command": {"type": "register_autoload",
                    "name": "GameState", "path": "res://src/game_state.gd", "executor": "raw"}},
                {"action": "project_command", "command": {"type": "atomic_files", "operations": []}},
                {"action": "project_command", "command": {"type": "create_input_action",
                    "name": "jump", "events": [{"type": "key", "key": "SPACE", "extra": True}]}}):
            try:
                actions.compile_action(root, bad)
                raise AssertionError("invalid project_command accepted")
            except actions.HighLevelActionError:
                pass
        with open(os.path.join(root, "src", "player.gd"), "rb") as handle:
            assert handle.read() == before
        assert not os.path.exists(os.path.join(root, "src", "new.gd"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All high-level action tests passed: %d" % len(tests))
