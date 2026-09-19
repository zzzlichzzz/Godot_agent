# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import history_manager
import symbol_refactor
from minilich import ml_project_index


def _write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _read(root, rel):
    with open(os.path.join(root, *rel.split("/")), "r", encoding="utf-8") as handle:
        return handle.read()


def _project():
    root = tempfile.mkdtemp(prefix="rename_symbol_")
    _write(root, "project.godot", "config_version=5\n")
    _write(root, "src/player.gd", '''class_name Player
extends Node
signal damaged

func take_damage(amount: int):
\tdamaged.emit()
\tself.take_damage(amount - 1)
''')
    _write(root, "src/controller.gd", '''extends Node
var player: Player

func run():
\tplayer.take_damage(2)
''')
    ml_project_index.build_index(root)
    return root


def _action(kind="function", line=5, old="take_damage", new="apply_damage"):
    return {"action": "rename_symbol", "kind": kind,
            "declaration": "res://src/player.gd:%d" % line,
            "old_name": old, "new_name": new}


def test_prepare_apply_and_compound_rollback():
    root = _project()
    try:
        before_player = _read(root, "src/player.gd")
        before_controller = _read(root, "src/controller.gd")
        prepared = symbol_refactor.prepare_rename(root, _action())
        assert [item["path"] for item in prepared["files"]] == [
            "res://src/controller.gd", "res://src/player.gd"]
        assert prepared["reference_count"] == 2
        assert all(item["diff"]["action"] == "rename_symbol"
                   for item in prepared["files"])
        assert _read(root, "src/player.gd") == before_player

        result = symbol_refactor.apply_prepared_rename(root, prepared, "chat-1", "Rename")
        assert result["file_count"] == 2 and len(result["changed_paths"]) == 2
        assert "apply_damage" in _read(root, "src/player.gd")
        assert "apply_damage" in _read(root, "src/controller.gd")
        info = history_manager.entry_info(root, result["entry_id"])
        assert info["type"] == "rename_symbol" and len(info["paths"]) == 2

        ok, _message, needs_force, paths, _diff = history_manager.rollback_entry(
            root, result["entry_id"])
        assert ok and not needs_force and len(paths) == 2
        assert _read(root, "src/player.gd") == before_player
        assert _read(root, "src/controller.gd") == before_controller
        assert ml_project_index.find_declarations(root, "function", "take_damage", refresh=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_stale_hash_writes_nothing():
    root = _project()
    try:
        prepared = symbol_refactor.prepare_rename(root, _action())
        controller_before = _read(root, "src/controller.gd")
        _write(root, "src/player.gd", _read(root, "src/player.gd") + "# manual\n")
        try:
            symbol_refactor.apply_prepared_rename(root, prepared)
            assert False, "stale transaction must fail"
        except symbol_refactor.StaleRenameError:
            pass
        assert _read(root, "src/controller.gd") == controller_before
        assert "apply_damage" not in _read(root, "src/controller.gd")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_dynamic_and_unknown_references_are_blocking():
    root = _project()
    try:
        _write(root, "src/dynamic.gd", '''extends Node
func run(target):
\ttarget.take_damage(1)
''')
        ml_project_index.build_index(root)
        try:
            symbol_refactor.prepare_rename(root, _action())
            assert False, "unknown receiver must block"
        except symbol_refactor.RenameError as exc:
            assert "неоднознач" in str(exc)

        os.remove(os.path.join(root, "src", "dynamic.gd"))
        _write(root, "src/reflect.gd", '''extends Node
func run(target):
\ttarget.call("take_damage", 1)
''')
        ml_project_index.build_index(root)
        try:
            symbol_refactor.prepare_rename(root, _action())
            assert False, "dynamic string must block"
        except symbol_refactor.RenameError as exc:
            assert "строк" in str(exc) or "неоднознач" in str(exc)

        _write(root, "src/reflect.gd", '''extends Node
func run(target):
\tvar data = {target: Player}
\ttarget.take_damage(1)
''')
        ml_project_index.build_index(root)
        try:
            symbol_refactor.prepare_rename(root, _action())
            assert False, "a dictionary key must not prove the receiver type"
        except symbol_refactor.RenameError as exc:
            assert "неоднознач" in str(exc)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_unqualified_call_in_nested_class_is_blocking():
    root = _project()
    try:
        _write(root, "src/player.gd", _read(root, "src/player.gd") + '''
class Replay:
\tfunc run():
\t\ttake_damage(1)
''')
        ml_project_index.build_index(root)
        try:
            symbol_refactor.prepare_rename(root, _action())
            assert False, "a nested-class call must not be bound to the outer script"
        except symbol_refactor.RenameError as exc:
            assert "неоднознач" in str(exc)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_mid_write_failure_restores_all_files():
    root = _project()
    original_replace = symbol_refactor._replace_file
    try:
        prepared = symbol_refactor.prepare_rename(root, _action())
        before = {item["path"]: item["before_bytes"] for item in prepared["files"]}
        calls = {"count": 0}

        def fail_second(source, destination):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("injected replace failure")
            return original_replace(source, destination)

        symbol_refactor._replace_file = fail_second
        try:
            symbol_refactor.apply_prepared_rename(root, prepared)
            assert False, "injected failure must abort the transaction"
        except OSError as exc:
            assert "injected" in str(exc)
        for path, expected in before.items():
            absolute = os.path.join(root, *path.replace("res://", "").split("/"))
            with open(absolute, "rb") as handle:
                assert handle.read() == expected
    finally:
        symbol_refactor._replace_file = original_replace
        shutil.rmtree(root, ignore_errors=True)


def test_class_name_and_signal_renames():
    root = _project()
    try:
        class_prepared = symbol_refactor.prepare_rename(
            root, _action("class_name", 1, "Player", "Hero"))
        assert len(class_prepared["files"]) == 2
        symbol_refactor.apply_prepared_rename(root, class_prepared)
        assert "class_name Hero" in _read(root, "src/player.gd")
        assert "player: Hero" in _read(root, "src/controller.gd")

        signal_action = {"action": "rename_symbol", "kind": "signal",
                         "declaration": "res://src/player.gd:3",
                         "old_name": "damaged", "new_name": "health_changed"}
        signal_prepared = symbol_refactor.prepare_rename(root, signal_action)
        symbol_refactor.apply_prepared_rename(root, signal_prepared)
        player = _read(root, "src/player.gd")
        assert "signal health_changed" in player and "health_changed.emit()" in player
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_schema_collision_and_comments_are_safe():
    root = _project()
    try:
        _write(root, "src/player.gd", _read(root, "src/player.gd") + '''
# take_damage is documentation only
func apply_damage():
\tpass
''')
        ml_project_index.build_index(root)
        for action in (
                _action(new="for"), _action(new="take_damage"),
                _action(new="apply_damage"),
                dict(_action(), declaration="src/player.gd:5")):
            try:
                symbol_refactor.prepare_rename(root, action)
                assert False, "invalid rename must fail"
            except symbol_refactor.RenameError:
                pass
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_all():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All rename_symbol tests passed: %d" % len(tests))


if __name__ == "__main__":
    run_all()
