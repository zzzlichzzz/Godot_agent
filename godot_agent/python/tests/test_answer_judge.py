# -*- coding: utf-8 -*-
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

from answer_judge import judge_answer, select_best_project_answer
from minilich.ml_project_index import build_index


def _answer(action):
    return ("Проверяю проект.\n```agent_action\n%s\n```\n===DONE==="
            % json.dumps(action, ensure_ascii=False))


def _project():
    root = tempfile.mkdtemp(prefix="godot_judge_")
    os.makedirs(os.path.join(root, "src", "scripts"))
    with open(os.path.join(root, "project.godot"), "w", encoding="utf-8") as handle:
        handle.write('[application]\nconfig/name="Judge Test"\n')
    with open(os.path.join(root, "src", "scripts", "player.gd"), "w",
              encoding="utf-8") as handle:
        handle.write("extends CharacterBody2D\n\nfunc jump():\n\tvelocity.y = -300\n")
    build_index(root)
    return root


def test_exact_read_file_beats_broad_librarian():
    root = _project()
    try:
        read = _answer({"action": "read_file", "paths": ["res://project.godot"]})
        librarian = _answer({"action": "ask_librarian",
                             "query": "project configuration application settings"})
        key, _text, result, judged = select_best_project_answer(
            root, [("read", read), ("lib", librarian)])
        assert key == "read"
        assert result["acceptable"]
        assert dict(judged)["read"]["score"] > dict(judged)["lib"]["score"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_librarian_beats_nonexistent_read_file():
    root = _project()
    try:
        bad_read = _answer({"action": "read_file",
                            "paths": ["res://missing/player.gd"]})
        librarian = _answer({"action": "ask_librarian",
                             "query": "player jump CharacterBody2D velocity"})
        key, _text, result, judged = select_best_project_answer(
            root, [("read", bad_read), ("lib", librarian)])
        assert key == "lib"
        assert result["acceptable"]
        assert dict(judged)["read"]["blocking"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_gather_context_is_high_value_read_action():
    root = _project()
    try:
        result = judge_answer(root, _answer({
            "action": "gather_context", "query": "player jump",
            "symbols": ["Player.jump"], "godot_api": ["CharacterBody2D"],
            "max_chars": 12000,
        }))
        assert result["acceptable"]
        assert result["vote_eligible"]
        assert result["score"] >= 90
        bad = judge_answer(root, _answer({
            "action": "gather_context", "symbols": "Player.jump",
            "max_chars": 50000,
        }))
        assert not bad["acceptable"]
        assert any(item["category"] == "schema" for item in bad["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_runtime_inspection_is_bounded_read_action():
    root = _project()
    try:
        result = judge_answer(root, _answer({
            "action": "inspect_runtime",
            "sections": ["tree", "properties", "metrics", "errors"],
            "properties": [{"node": "Player", "names": ["health", "global_position"]}],
            "max_age_ms": 1000,
        }))
        assert result["acceptable"] and result["score"] >= 90
        assert any("bounded read-only runtime snapshot" in item for item in result["evidence"])
        bad = judge_answer(root, _answer({
            "action": "inspect_runtime", "sections": ["properties"],
            "properties": [{"node": "../Player", "names": ["health"]}],
            "set_property": True,
        }))
        assert not bad["acceptable"]
        assert any(item["category"] == "runtime" for item in bad["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_runtime_check_is_deterministic_bounded_action():
    root = _project()
    try:
        os.makedirs(os.path.join(root, "scenes"))
        with open(os.path.join(root, "scenes", "main.tscn"), "w", encoding="utf-8") as handle:
            handle.write('[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n')
        result = judge_answer(root, _answer({
            "action": "run_check", "scene": "res://scenes/main.tscn",
            "steps": [{"op": "wait_frames", "frames": 2},
                      {"op": "assert_node", "node": ".", "exists": True}],
        }))
        assert result["acceptable"] and result["score"] >= 90
        assert any("deterministic local game check" in item for item in result["evidence"])
        bad = judge_answer(root, _answer({
            "action": "run_check", "scene": "res://scenes/main.tscn",
            "steps": [{"op": "assert_property", "node": "../Main",
                       "property": "position", "operator": "eq", "expected": 0}],
        }))
        assert not bad["acceptable"]
        assert any(item["category"] == "runtime_check" for item in bad["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_impossible_patch_is_blocking():
    root = _project()
    try:
        result = judge_answer(root, _answer({
            "action": "patch_file", "path": "res://src/scripts/player.gd",
            "search": "not present", "replace": "replacement",
        }))
        assert not result["acceptable"]
        assert any(item["category"] == "patch" for item in result["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_rename_symbol_uses_safe_dry_run():
    root = _project()
    try:
        result = judge_answer(root, _answer({
            "action": "rename_symbol", "kind": "function",
            "declaration": "res://src/scripts/player.gd:3",
            "old_name": "jump", "new_name": "perform_jump",
        }))
        assert result["acceptable"] and result["score"] >= 90
        assert any("Safe rename" in item for item in result["evidence"])
        bad = judge_answer(root, _answer({
            "action": "rename_symbol", "kind": "function",
            "declaration": "res://src/scripts/player.gd:99",
            "old_name": "jump", "new_name": "perform_jump",
        }))
        assert not bad["acceptable"]
        assert any(item["category"] == "refactor" for item in bad["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_edit_scene_uses_structural_schema_validation():
    root = _project()
    try:
        scene_dir = os.path.join(root, "scenes")
        os.makedirs(scene_dir)
        with open(os.path.join(scene_dir, "main.tscn"), "w", encoding="utf-8") as handle:
            handle.write('[gd_scene format=3]\n\n[node name="Main" type="Node"]\n')
        result = judge_answer(root, _answer({
            "action": "edit_scene", "scene": "res://scenes/main.tscn",
            "operations": [{"op": "add_node", "parent": ".",
                            "name": "HUD", "type": "CanvasLayer"}],
        }))
        assert result["acceptable"] and result["score"] >= 90
        bad = judge_answer(root, _answer({
            "action": "edit_scene", "scene": "res://scenes/main.tscn",
            "operations": [{"op": "set_node_property", "node": "../Outside",
                            "property": "visible", "value": {"type": "bool", "value": True}}],
        }))
        assert not bad["acceptable"]
        assert any(item["category"] == "scene" for item in bad["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_project_settings_uses_structural_schema_validation():
    root = _project()
    try:
        result = judge_answer(root, _answer({
            "action": "edit_project_settings", "operations": [
                {"op": "add_input_action", "name": "jump", "deadzone": 0.2}],
        }))
        assert result["acceptable"] and result["score"] >= 90
        bad = judge_answer(root, _answer({
            "action": "edit_project_settings", "operations": [
                {"op": "set_display_settings", "renderer": "unknown"}],
        }))
        assert not bad["acceptable"]
        assert any(item["category"] == "project_settings" for item in bad["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_resource_uses_structural_schema_validation():
    root = _project()
    try:
        resources = os.path.join(root, "resources")
        os.makedirs(resources)
        with open(os.path.join(resources, "data.tres"), "w", encoding="utf-8") as handle:
            handle.write('[gd_resource type="Resource" format=3]\n')
        result = judge_answer(root, _answer({
            "action": "edit_resource", "resource": "res://resources/data.tres",
            "operations": [{"op": "set_property", "target": [], "property": "value",
                            "value": {"type": "int", "value": 1}}],
        }))
        assert result["acceptable"] and result["score"] >= 90
        bad = judge_answer(root, _answer({
            "action": "edit_resource", "resource": "res://resources/data.tres",
            "operations": [{"op": "set_property", "target": "root", "property": "value",
                            "value": {"type": "int", "value": 1}}],
        }))
        assert not bad["acceptable"]
        assert any(item["category"] == "resource" for item in bad["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_transaction_uses_atomic_overlay_validation():
    root = _project()
    try:
        result = judge_answer(root, _answer({"action": "transaction", "operations": [
            {"action": "create_file", "path": "res://health.gd", "content": "extends Node\n"},
            {"action": "patch_file", "path": "res://src/scripts/player.gd", "search": "velocity.y = -300", "replace": "velocity.y = -400"}]}))
        assert result["acceptable"] and result["score"] >= 90
        assert any("Atomic transaction" in value for value in result["evidence"])
        bad = judge_answer(root, _answer({"action": "transaction", "operations": [
            {"action": "create_file", "path": "res://project.godot", "content": "x"}]}))
        assert not bad["acceptable"]
        assert any(item["category"] == "transaction" for item in bad["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_project_command_compiles_then_uses_primitive_judge():
    root = _project()
    try:
        result = judge_answer(root, _answer({"action": "project_command", "command": {
            "type": "atomic_files", "operations": [{"action": "patch_file",
                "path": "res://src/scripts/player.gd", "search": "velocity.y = -300",
                "replace": "velocity.y = -450"}]}}))
        assert result["acceptable"] and result["score"] >= 90
        assert any("deterministically compiles to transaction" in item
                   for item in result["evidence"])
        bad = judge_answer(root, _answer({"action": "project_command", "command": {
            "type": "atomic_files", "operations": [{"action": "patch_file",
                "path": "res://src/scripts/player.gd", "search": "missing",
                "replace": "x"}]}}))
        assert not bad["acceptable"]
        assert any(item["category"] == "transaction" for item in bad["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_broken_gdscript_is_blocking():
    root = _project()
    try:
        result = judge_answer(root, _answer({
            "action": "create_file", "path": "res://src/scripts/broken.gd",
            "content": "extends Node\nfunc broken(\n",
        }))
        assert not result["acceptable"]
        assert any(item["category"] == "gdscript" for item in result["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_plain_done_answer_is_acceptable_but_below_exact_action():
    root = _project()
    try:
        plain = "Нужно уточнить механику движения.\n===DONE==="
        exact = _answer({"action": "read_file", "paths": ["res://project.godot"]})
        plain_result = judge_answer(root, plain)
        exact_result = judge_answer(root, exact)
        assert plain_result["acceptable"]
        assert not plain_result["vote_eligible"]
        assert exact_result["vote_eligible"]
        assert exact_result["score"] > plain_result["score"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_librarian_beats_unfinished_prose_even_without_index_hits():
    root = _project()
    try:
        unfinished = ("Сделаем классический 2D-платформер в духе Mario. "
                      "Сначала быстро посмотрю, что уже есть в проекте.")
        librarian = _answer({
            "action": "ask_librarian",
            "query": "definitely absent terms qzxv no index match",
            "reason": "Нужно определить структуру проекта перед реализацией.",
        })
        key, _text, result, judged = select_best_project_answer(
            root, [("A", unfinished), ("B", librarian)])
        results = dict(judged)
        assert key == "B"
        assert result["acceptable"]
        assert result["vote_eligible"]
        assert not results["A"]["acceptable"]
        assert any(item["category"] == "protocol" for item in results["A"]["blocking"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_content_ref_body_outside_action_fence_is_judged():
    root = _project()
    try:
        action = json.dumps({
            "action": "plan",
            "description": "Create script",
            "steps": [{"action": "create_file",
                       "path": "res://src/scripts/generated.gd",
                       "content_ref": "SCRIPT", "content_ref_lines": 1}],
        })
        answer = ("```agent_action\n%s\n```\n"
                  "===SCRIPT===\nextends Node\n===END_SCRIPT===\n===DONE===" % action)
        result = judge_answer(root, answer)
        assert result["acceptable"]
        assert result["vote_eligible"]
        assert result["action"]["steps"][0]["content"] == "extends Node"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_all():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All Answer Judge tests passed: %d" % len(tests))


if __name__ == "__main__":
    run_all()
