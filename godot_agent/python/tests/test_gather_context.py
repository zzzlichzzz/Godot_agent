# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import gather_context
import parser_base


def _write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _project():
    root = tempfile.mkdtemp(prefix="gather_context_")
    _write(root, "project.godot", '''[application]
config/name="Gather"

[autoload]
GameState="*res://src/game_state.gd"

[input]
jump={
"deadzone": 0.5,
"events": []
}
''')
    _write(root, "src/player.gd", '''class_name Player
extends CharacterBody2D

func take_damage(amount):
	health -= amount

func jump():
	velocity.y = -300
''')
    _write(root, "src/enemy_a.gd", "extends Node\nfunc attack():\n\tpass\n")
    _write(root, "src/enemy_b.gd", "extends Node\nfunc attack():\n\tpass\n")
    _write(root, "src/game_state.gd", "extends Node\n")
    _write(root, "levels/main.tscn", '''[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://src/player.gd" id="1"]

[node name="Main" type="Node2D"]
[node name="Player" type="CharacterBody2D" parent="."]
script = ExtResource("1")
[connection signal="tree_entered" from="Player" to="Player" method="jump"]
''')
    return root


def test_validation_and_parser_normalization():
    spec, errors = gather_context.validate_request({
        "action": "gather_context", "query": "x", "symbols": ["A.f"] * 20,
        "godot_api": ["Node", "bad-name"], "max_chars": 999999,
    })
    assert not errors
    assert len(spec["symbols"]) == 8
    assert spec["godot_api"] == ["Node"]
    assert spec["max_chars"] == 20000
    obj, fixes = parser_base.coerce_action_schema({"action": "Gather-Context"})
    assert obj["action"] == "gather_context" and fixes


def test_exact_symbol_scene_dependencies_and_settings():
    root = _project()
    try:
        snapshot = {
            "schema_version": 1,
            "scene": {"active": "res://levels/main.tscn"},
            "script": {"path": "res://src/player.gd", "dirty": True,
                       "caret_context": {"start_line": 1, "end_line": 2,
                                         "text": "class_name Player"}},
        }
        result = gather_context.gather(root, {
            "action": "gather_context", "query": "player jump",
            "symbols": ["Player.take_damage"], "godot_api": [],
            "max_chars": 12000,
        }, editor_snapshot=snapshot)
        text = gather_context.format_result(result)
        assert "SYMBOL Player.take_damage" in text
        assert "health -= amount" in text
        assert "ACTIVE SCENE res://levels/main.tscn" in text
        assert "res://levels/main.tscn" in text and "references res://src/player.gd" in text
        assert "GameState -> res://src/game_state.gd" in text
        assert "InputMap actions: jump" in text
        assert "unsaved; diagnostics below use disk content" in text
        assert len(text) <= 12000 and text.endswith("[/Gather context]")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_ambiguous_symbol_is_not_guessed():
    root = _project()
    try:
        result = gather_context.gather(root, {
            "action": "gather_context", "symbols": ["attack"],
            "editor": False, "active_scene": False, "diagnostics": False,
        })
        text = gather_context.format_result(result)
        assert "attack: ambiguous" in text
        assert "src/enemy_a.gd" in text and "src/enemy_b.gd" in text
        assert "```gdscript" not in text
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_budget_and_no_mutation():
    root = _project()
    try:
        before = {}
        for base, _dirs, files in os.walk(root):
            for name in files:
                path = os.path.join(base, name)
                if ".agent_history" in path.split(os.sep):
                    continue
                with open(path, "rb") as handle:
                    before[os.path.relpath(path, root)] = handle.read()
        result = gather_context.gather(root, {
            "action": "gather_context", "query": "player " * 500,
            "symbols": ["Player.take_damage"], "max_chars": 2000,
        })
        text = gather_context.format_result(result)
        assert len(text) <= 2000 and text.endswith("[/Gather context]")
        after = {}
        for base, _dirs, files in os.walk(root):
            for name in files:
                path = os.path.join(base, name)
                if ".agent_history" in path.split(os.sep):
                    continue
                with open(path, "rb") as handle:
                    after[os.path.relpath(path, root)] = handle.read()
        assert before == after
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_all():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All gather_context tests passed: %d" % len(tests))


if __name__ == "__main__":
    run_all()
