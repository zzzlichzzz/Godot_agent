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


root = tempfile.mkdtemp(prefix="rename_flow_project_")
store = tempfile.mkdtemp(prefix="rename_flow_store_")
history_manager.set_storage_dir(store)
write(root, "project.godot", "config_version=5\n")
write(root, "src/player.gd", """class_name Player
extends Node
func take_damage():
\tself.take_damage()
""")
write(root, "src/controller.gd", """extends Node
var player: Player
func run():
\tplayer.take_damage()
""")

originals = {}
for name in ("_remember", "_sync_chat_after_reply", "_refresh_fs_snapshot",
             "_remember_file", "_touch_file_read", "_current_chat_info"):
    originals[name] = getattr(main, name)
main._remember = lambda *_args, **_kwargs: None
main._sync_chat_after_reply = lambda: None
main._refresh_fs_snapshot = lambda *_args: None
main._remember_file = lambda *_args: None
main._touch_file_read = lambda *_args: None
main._current_chat_info = lambda: ("flow-chat", "Rename flow")

try:
    STATE.update({"project_root": root, "pending_action": None,
                  "pending_refactor": None, "addon_intent": False,
                  "addon_dir": None})
    action = {"action": "rename_symbol", "kind": "function",
              "declaration": "res://src/player.gd:3",
              "old_name": "take_damage", "new_name": "apply_damage"}

    with main.app.test_request_context("/chat", method="POST", json={}):
        prepared_response = main._package_model_reply("Переименовываю.", action, root)
        prepared_json, prepared_status = payload(prepared_response)

    assert prepared_status == 200
    assert len(prepared_json["pending_action_diffs"]) == 2
    assert prepared_json["pending_action_diff"] is None
    assert "before_bytes" not in str(prepared_json)
    assert "take_damage" in read(root, "src/player.gd")
    assert isinstance(STATE.get("pending_refactor"), dict)

    with main.app.test_request_context(
            "/chat/confirm_action", method="POST", json={"approved": True}):
        confirm_response = main.confirm_action()
        confirm_json, confirm_status = payload(confirm_response)

    assert confirm_status == 200
    assert confirm_json["changed_paths"] == [
        "res://src/controller.gd", "res://src/player.gd"]
    assert confirm_json.get("history_entry_id")
    assert STATE.get("pending_action") is None
    assert STATE.get("pending_refactor") is None
    assert "apply_damage" in read(root, "src/player.gd")
    assert "apply_damage" in read(root, "src/controller.gd")

    info = history_manager.entry_info(root, confirm_json["history_entry_id"])
    assert info and info["type"] == "rename_symbol" and len(info["paths"]) == 2
    ok, _message, _needs_force, paths, _diff = history_manager.rollback_entry(
        root, confirm_json["history_entry_id"])
    assert ok and len(paths) == 2
    assert "take_damage" in read(root, "src/player.gd")
    assert "take_damage" in read(root, "src/controller.gd")

    print("PASS rename_symbol Flask prepare/confirm/rollback flow")
finally:
    for name, value in originals.items():
        setattr(main, name, value)
    STATE["pending_action"] = None
    STATE["pending_refactor"] = None
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(store, ignore_errors=True)
