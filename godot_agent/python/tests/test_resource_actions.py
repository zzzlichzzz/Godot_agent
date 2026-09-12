# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import parser_base
import resource_actions


def write(root, rel, text="resource"):
    absolute = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return absolute


def expect_error(root, action, fragment):
    try:
        resource_actions.normalize_action(root, action)
    except resource_actions.ResourceActionError as exc:
        assert fragment.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError("Expected ResourceActionError: %s" % fragment)


def fixture():
    root = tempfile.mkdtemp(prefix="resource_actions_")
    write(root, "project.godot", "config_version=5\n")
    write(root, "resources/data.tres", '[gd_resource type="Resource" format=3]\n')
    write(root, "resources/old.tres", '[gd_resource type="Resource" format=3]\n')
    write(root, "resources/new.tres", '[gd_resource type="Resource" format=3]\n')
    write(root, "textures/frame.png", "png")
    write(root, "addons/tool/private.tres", '[gd_resource type="Resource" format=3]\n')
    return root


def test_full_schema_digest_and_public_payload():
    root = fixture()
    try:
        action = {"action": "edit_resource", "resource": "res://resources/data.tres",
                  "wait_for_import": ["res://textures/frame.png"], "operations": [
            {"op": "set_property", "target": [], "property": "metadata",
             "value": {"type": "NewSubresource", "class": "Gradient",
                       "properties": [{"property": "offsets",
                                       "value": {"type": "String", "value": "safe"}}]}},
            {"op": "replace_reference", "target": [], "old": "res://resources/old.tres",
             "new": "res://resources/new.tres", "expected_count": 1},
            {"op": "animation_add_value_track", "path": "Node:position:x",
             "keys": [{"time": 0, "value": {"type": "float", "value": 0}},
                      {"time": 1, "value": {"type": "float", "value": 1},
                       "transition": 1.5}]},
            {"op": "sprite_frames_add_animation", "name": "idle", "fps": 8,
             "loop": True, "frames": [{"texture": {
                 "type": "ResourcePath", "value": "res://textures/frame.png"}}]},
            {"op": "theme_set_item", "data_type": "color", "theme_type": "Button",
             "name": "font_color", "value": {"type": "Color", "value": [1, 1, 1, 1]},
             "overwrite": True},
            {"op": "tileset_add_atlas_source", "source_id": 2,
             "texture": {"type": "ResourcePath", "value": "res://textures/frame.png"},
             "texture_region_size": [16, 16], "tiles": [[0, 0], [1, 0]]},
        ]}
        normalized, absolute = resource_actions.normalize_action(root, action)
        assert set(normalized["wait_for_import"]) == {
            "res://textures/frame.png", "res://resources/old.tres", "res://resources/new.tres"}
        assert normalized["operations"][0]["value"]["type"] == "NewSubresource"
        assert resource_actions.canonical_digest(normalized) == resource_actions.canonical_digest(normalized)
        prepared = resource_actions.prepare(root, action)
        public = resource_actions.public_prepared(prepared)
        assert public["prepare_in_editor"] and public["expected_resource_hash"] == resource_actions.file_sha256(absolute)
        assert "action" not in public and "before_hash" not in public
        assert len(resource_actions.operation_summary(normalized)) == 6
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_schema_limits_paths_and_addon_policy():
    root = fixture()
    try:
        base = {"action": "edit_resource", "resource": "res://resources/data.tres",
                "operations": [{"op": "set_property", "target": [], "property": "value",
                                "value": {"type": "int", "value": 1}}]}
        expect_error(root, dict(base, operations=[]), "operations")
        expect_error(root, dict(base, resource="res://resources/missing.tres"), "не найден")
        expect_error(root, dict(base, resource="res://addons/tool/private.tres"), "аддонов")
        normalized, _ = resource_actions.normalize_action(
            root, dict(base, resource="res://addons/tool/private.tres"), allow_addons=True)
        assert normalized["resource"].startswith("res://addons/")
        bad = dict(base)
        bad["operations"] = [{"op": "sprite_frames_add_animation", "name": "idle",
                              "fps": 8, "loop": "yes", "frames": [{"texture": {
                                  "type": "ResourcePath", "value": "res://textures/frame.png"}}]}]
        expect_error(root, bad, "loop")
        bad["operations"] = [{"op": "theme_set_item", "data_type": "color",
                              "theme_type": "Button", "name": "font_color",
                              "value": {"type": "Color", "value": [1, 1, 1, 1]},
                              "overwrite": 1}]
        expect_error(root, bad, "overwrite")
        expect_error(root, dict(base, summary=42), "summary")
        same = dict(base)
        same["operations"] = [{"op": "replace_reference", "target": [],
                               "old": "res://resources/old.tres", "new": "res://resources/old.tres",
                               "expected_count": 1}]
        expect_error(root, same, "различаться")
        bad["operations"] = [{"op": "theme_set_item", "data_type": "color",
                              "theme_type": "Button", "name": "font_color",
                              "value": {"type": "int", "value": 1}}]
        expect_error(root, bad, "не подходит")
        bad["operations"] = [{"op": "tileset_add_atlas_source", "source_id": 0,
                              "texture": {"type": "ResourcePath", "value": "res://textures/frame.png"},
                              "texture_region_size": [16, 16], "tiles": [[0, 0], [0, 0]]}]
        expect_error(root, bad, "повтор")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_parser_alias_and_read_only_prepare():
    root = fixture()
    try:
        path = os.path.join(root, "resources", "data.tres")
        with open(path, "rb") as handle:
            before = handle.read()
        raw = '{"action":"resource-edit","resource":"res://resources/data.tres",' \
              '"operations":[{"op":"set_property","target":[],"property":"value",' \
              '"value":{"type":"int","value":2}}]}'
        parsed, error = parser_base.parse_action_json(raw)
        assert error is None and parsed["action"] == "edit_resource"
        resource_actions.prepare(root, parsed)
        with open(path, "rb") as handle:
            assert handle.read() == before
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_all():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All resource action tests passed: %d" % len(tests))


if __name__ == "__main__":
    run_all()
