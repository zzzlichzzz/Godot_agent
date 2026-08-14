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
