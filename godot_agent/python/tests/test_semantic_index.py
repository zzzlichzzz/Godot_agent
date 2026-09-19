# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import gd_semantic_parser
from minilich import ml_project_index


def _write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def test_parser_exact_ranges_and_ignored_text():
    text = '''class_name Игрок\r
extends Node\r
# Игрок fake_call()\r
signal died\r
var note = "died Игрок"\r
func take_damage(\r
\tamount: int\r
):\r
\tdied.emit()\r
\tself.take_damage(amount)\r
'''
    parsed = gd_semantic_parser.parse(text, "src/player.gd")
    declarations = {(item["kind"], item["name"]): item for item in parsed["declarations"]}
    assert ("class_name", "Игрок") in declarations
    assert ("signal", "died") in declarations
    assert ("function", "take_damage") in declarations
    for item in declarations.values():
        assert text[item["start"]:item["end"]] == item["name"]
    refs = [(item["name"], item["context"]) for item in parsed["references"]]
    assert ("died", "identifier") in refs or ("died", "member") in refs
    assert ("take_damage", "member") in refs
    assert sum(1 for item in parsed["references"] if item["name"] == "Игрок") == 0
    assert any("died Игрок" in item["value"] for item in parsed["strings"])


def test_index_hash_incremental_and_queries():
    root = tempfile.mkdtemp(prefix="semantic_index_")
    try:
        first = "class_name Alpha\nextends Node\nfunc hit():\n\tpass\n"
        second = "class_name Bravo\nextends Node\nfunc hit():\n\tpass\n"
        assert len(first) == len(second)
        _write(root, "src/unit.gd", first)
        _write(root, "project.godot", "config_version=5\n")
        ml_project_index.build_index(root)
        decls = ml_project_index.find_declarations(root, "class_name", "Alpha")
        assert len(decls) == 1 and decls[0]["path"] == "res://src/unit.gd"
        old_hash = decls[0]["sha256"]
        target = os.path.join(root, "src", "unit.gd")
        stamp = os.stat(target)
        _write(root, "src/unit.gd", second)
        os.utime(target, (stamp.st_atime, stamp.st_mtime))
        ml_project_index.update_entries(root, ["src/unit.gd"])
        decls = ml_project_index.find_declarations(root, "class_name", "Bravo")
        assert len(decls) == 1 and decls[0]["sha256"] != old_hash
        facts = ml_project_index.find_name_facts(root, "hit")
        assert facts["complete"] and len(facts["declarations"]) == 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_duplicate_owners_remain_distinct():
    root = tempfile.mkdtemp(prefix="semantic_owners_")
    try:
        _write(root, "nested.gd", '''extends Node
class A:
\tfunc tick():
\t\tpass
class B:
\tfunc tick():
\t\tpass
''')
        ml_project_index.build_index(root)
        decls = ml_project_index.find_declarations(root, "function", "tick")
        assert len(decls) == 2
        assert len({item["owner"] for item in decls}) == 2
        assert len({item["id"] for item in decls}) == 2
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_all():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All semantic index tests passed: %d" % len(tests))


if __name__ == "__main__":
    run_all()
