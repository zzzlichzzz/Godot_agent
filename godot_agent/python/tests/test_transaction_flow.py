# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import history_manager
import main
from server_state import STATE


def write(root, rel, text):
    absolute = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def read(root, rel):
    with open(os.path.join(root, *rel.split("/")), "r", encoding="utf-8") as handle:
        return handle.read()


def payload(response):
    if isinstance(response, tuple):
        return response[0].get_json(), response[1]
    return response.get_json(), response.status_code


root = tempfile.mkdtemp(prefix="transaction_flow_project_")
store = tempfile.mkdtemp(prefix="transaction_flow_store_")
history_manager.set_storage_dir(store)
write(root, "project.godot", "config_version=5\n")
write(root, "src/player.gd", "extends Node\nfunc run():\n\tpass\n")

originals = {}
for name in ("_remember", "_sync_chat_after_reply", "_refresh_fs_snapshot",
             "_remember_file", "_touch_file_read", "_current_chat_info"):
    originals[name] = getattr(main, name)
main._remember = lambda *_args, **_kwargs: None
main._sync_chat_after_reply = lambda: None
main._refresh_fs_snapshot = lambda *_args: None
main._remember_file = lambda *_args: None
main._touch_file_read = lambda *_args: None
main._current_chat_info = lambda: ("flow-chat", "Transaction flow")

try:
    STATE.update({"project_root": root, "pending_action": None,
                  "pending_transaction": None, "addon_intent": False,
                  "addon_dir": None, "godot_executable": None})
    action = {"action": "transaction", "summary": "add feature", "operations": [
        {"action": "create_file", "path": "res://src/health.gd",
         "content": "extends Node\nfunc hp():\n\treturn 10\n"},
        {"action": "patch_file", "path": "res://src/player.gd",
         "search": "\tpass", "replace": "\tprint(\"ready\")"}]}

    with main.app.test_request_context("/chat", method="POST", json={}):
        prepared_json, prepared_status = payload(
            main._package_model_reply("Готовлю пакет.", action, root))
    assert prepared_status == 200
    assert len(prepared_json["pending_action_diffs"]) == 2
    assert "before_bytes" not in str(prepared_json)
    assert isinstance(STATE.get("pending_transaction"), dict)
    assert not os.path.exists(os.path.join(root, "src", "health.gd"))
    assert "\tpass" in read(root, "src/player.gd")

    with main.app.test_request_context(
            "/chat/confirm_action", method="POST", json={"approved": True}):
        confirm_json, confirm_status = payload(main.confirm_action())
    assert confirm_status == 200 and confirm_json.get("history_entry_id")
    assert set(confirm_json["changed_paths"]) == {"res://src/health.gd", "res://src/player.gd"}
    assert STATE.get("pending_transaction") is None
    assert "return 10" in read(root, "src/health.gd")
    assert 'print("ready")' in read(root, "src/player.gd")

    info = history_manager.entry_info(root, confirm_json["history_entry_id"])
    assert info and info["type"] == "transaction" and len(info["paths"]) == 2
    ok, _message, _force, paths, _diff = history_manager.rollback_entry(
        root, confirm_json["history_entry_id"])
    assert ok and len(paths) == 2
    assert not os.path.exists(os.path.join(root, "src", "health.gd"))
    assert "\tpass" in read(root, "src/player.gd")

    original_validate = main.godot_headless_validation.validate_batch
    main.godot_headless_validation.validate_batch = lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(AssertionError("no-op must not run Godot validation")))
    try:
        no_op = {"action": "transaction", "operations": [
            {"action": "create_file", "path": "res://src/player.gd",
             "content": read(root, "src/player.gd")}], "summary": "already done"}
        with main.app.test_request_context("/chat", method="POST", json={}):
            no_op_json, no_op_status = payload(
                main._package_model_reply("Проверяю пакет.", no_op, root))
        assert no_op_status == 200 and no_op_json["already_satisfied"] is True
        assert no_op_json["pending_action"] is None and no_op_json["changed_paths"] == []
        assert STATE.get("pending_transaction") is None
    finally:
        main.godot_headless_validation.validate_batch = original_validate
    print("PASS transaction Flask prepare/confirm/rollback flow")
finally:
    for name, value in originals.items():
        setattr(main, name, value)
    STATE["pending_action"] = None
    STATE["pending_transaction"] = None
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(store, ignore_errors=True)
