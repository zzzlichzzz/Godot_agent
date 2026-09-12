# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import godot_headless_validation
import history_manager
import parser_base
import transaction_actions as actions


def write(root, rel, text):
    absolute = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def read(root, rel):
    with open(os.path.join(root, *rel.split("/")), "r", encoding="utf-8") as handle:
        return handle.read()


def project():
    root = tempfile.mkdtemp(prefix="transaction_project_")
    write(root, "project.godot", "config_version=5\n")
    write(root, "src/player.gd", "extends Node\nfunc run():\n\tpass\n")
    return root


def receipt(prepared):
    return {"schema_version": 1, "candidate_digest": prepared["batch"]["candidate_digest"],
            "source_hashes": prepared["batch"]["source_hashes"],
            "report": {"status": "unavailable", "blocking": False}}


def test_overlay_sequence_apply_and_full_rollback():
    root = project()
    store = tempfile.mkdtemp(prefix="transaction_store_")
    history_manager.set_storage_dir(store)
    try:
        action = {"action": "transaction", "summary": "feature", "operations": [
            {"action": "create_file", "path": "res://src/health.gd",
             "content": "extends Node\nfunc value():\n\treturn 10\n"},
            {"action": "patch_file", "path": "res://src/health.gd",
             "search": "return 10", "replace": "return 20"},
            {"action": "patch_file", "path": "res://src/player.gd",
             "search": "\tpass", "replace": "\tprint(\"ok\")"}],
            "checks": [{"type": "parse_script", "path": "res://src/health.gd"}]}
        prepared = actions.prepare(root, action)
        assert len(prepared["files"]) == 2
        assert not os.path.exists(os.path.join(root, "src", "health.gd"))
        assert len(actions.prepared_diffs(prepared)) == 2
        actions.attach_validation(prepared, receipt(prepared))
        result = actions.apply_prepared(root, prepared, "chat", "Transaction")
        assert "return 20" in read(root, "src/health.gd")
        assert 'print("ok")' in read(root, "src/player.gd")
        info = history_manager.entry_info(root, result["entry_id"])
        assert info["type"] == "transaction" and len(info["paths"]) == 2
        ok, _message, _force, paths, _diff = history_manager.rollback_entry(root, result["entry_id"])
        assert ok and len(paths) == 2
        assert not os.path.exists(os.path.join(root, "src", "health.gd"))
        assert "\tpass" in read(root, "src/player.gd")
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(store, ignore_errors=True)


def test_move_then_patch_and_stale_receipt():
    root = project()
    try:
        action = {"action": "transaction", "operations": [
            {"action": "move_file", "path": "res://src/player.gd", "dest": "res://src/hero.gd"},
            {"action": "patch_file", "path": "res://src/hero.gd", "search": "run", "replace": "start"}]}
        prepared = actions.prepare(root, action)
        assert set(prepared["paths"]) == {"res://src/player.gd", "res://src/hero.gd"}
        actions.attach_validation(prepared, receipt(prepared))
        write(root, "src/player.gd", "extends Node\n# manual\n")
        try:
            actions.verify_prepared(root, prepared)
            raise AssertionError("stale transaction was accepted")
        except (actions.StaleTransactionError, godot_headless_validation.StaleValidationError):
            pass
        assert not os.path.exists(os.path.join(root, "src", "hero.gd"))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_crlf_source_matches_headless_receipt():
    root = project()
    try:
        absolute = os.path.join(root, "src", "player.gd")
        with open(absolute, "wb") as handle:
            handle.write(b"extends Node\r\nfunc run():\r\n\tpass\r\n")
        prepared = actions.prepare(root, {"action": "transaction", "operations": [
            {"action": "patch_file", "path": "res://src/player.gd",
             "search": "\tpass", "replace": "\tprint(1)"}]})
        actions.attach_validation(prepared, receipt(prepared))
        actions.verify_prepared(root, prepared)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_schema_parser_and_atomic_failure_restore():
    root = project()
    store = tempfile.mkdtemp(prefix="transaction_store_")
    history_manager.set_storage_dir(store)
    old_replace = actions._replace_file
    try:
        parsed, fixes = parser_base.coerce_action_schema({
            "action": "batch-transaction", "operations": [
                {"action": "Create", "path": "res://src/new.gd", "content": "extends Node"}]})
        assert parsed["action"] == "transaction" and parsed["operations"][0]["action"] == "create_file"
        assert fixes
        raw = ("```agent_action\n"
               "{\"action\":\"transaction\",\"operations\":[{\"action\":\"create_file\","
               "\"path\":\"res://src/ref.gd\",\"content_ref\":\"BODY\",\"content_ref_lines\":1}]}\n"
               "===BODY===\nextends Node\n===END_BODY===\n```\n===DONE===")
        resolved, error = parser_base.parse_action_json(raw)
        assert error is None
        assert resolved["operations"][0]["content"] == "extends Node"
        for bad in (
                {"action": "transaction", "operations": []},
                {"action": "transaction", "operations": [{"action": "create_file", "path": "res://project.godot", "content": "x"}]},
                {"action": "transaction", "operations": [{"action": "create_file", "path": "res://scenes/new.tscn", "content": "x"}]},
                {"action": "transaction", "operations": [{"action": "patch_file", "path": "res://scenes/main.tscn", "search": "a", "replace": "b"}]},
                {"action": "transaction", "operations": [{"action": "move_file", "path": "res://src/player.gd", "dest": "res://scenes/new.tscn"}]},
                {"action": "transaction", "operations": [{"action": "edit_scene"}]},
                {"action": "transaction", "operations": [{"action": "patch_file", "path": "res://src/player.gd", "search": "missing", "replace": "x"}]}):
            try:
                actions.prepare(root, bad)
                raise AssertionError("invalid transaction accepted")
            except actions.TransactionError:
                pass
        prepared = actions.prepare(root, {"action": "transaction", "operations": [
            {"action": "patch_file", "path": "res://src/player.gd", "search": "pass", "replace": "print(1)"},
            {"action": "create_file", "path": "res://src/new.gd", "content": "extends Node\n"}]})
        actions.attach_validation(prepared, receipt(prepared))
        calls = {"count": 0}
        def fail_second(source, destination):
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("injected")
            return old_replace(source, destination)
        actions._replace_file = fail_second
        try:
            actions.apply_prepared(root, prepared)
            raise AssertionError("injected failure was ignored")
        except OSError:
            pass
        assert "\tpass" in read(root, "src/player.gd")
        assert not os.path.exists(os.path.join(root, "src", "new.gd"))
    finally:
        actions._replace_file = old_replace
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(store, ignore_errors=True)


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print("All transaction tests passed: %d" % len(tests))
