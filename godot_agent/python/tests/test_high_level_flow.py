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


def payload(response):
    if isinstance(response, tuple):
        return response[0].get_json(), response[1]
    return response.get_json(), response.status_code


root = tempfile.mkdtemp(prefix="high_level_flow_project_")
store = tempfile.mkdtemp(prefix="high_level_flow_store_")
history_manager.set_storage_dir(store)
write(root, "project.godot", "config_version=5\n")
write(root, "src/player.gd", "extends Node\nfunc run():\n\tpass\n")
write(root, "src/health.gd", "extends Node\n")
write(root, "scenes/main.tscn", '[gd_scene format=3]\n\n[node name="Main" type="Node"]\n')

originals = {}
for name in ("_remember", "_sync_chat_after_reply", "_refresh_fs_snapshot",
             "_remember_file", "_touch_file_read", "_current_chat_info"):
    originals[name] = getattr(main, name)
main._remember = lambda *_args, **_kwargs: None
main._sync_chat_after_reply = lambda: None
main._refresh_fs_snapshot = lambda *_args: None
main._remember_file = lambda *_args: None
main._touch_file_read = lambda *_args: None
main._current_chat_info = lambda: ("high-level-chat", "High-level flow")

try:
    STATE.update({"project_root": root, "pending_action": None,
                  "pending_transaction": None, "pending_scene_action": None,
                  "pending_project_settings_action": None, "addon_intent": False,
                  "addon_dir": None, "godot_executable": None})
    command = {"action": "project_command", "summary": "feature", "command": {
        "type": "atomic_files", "operations": [
            {"action": "create_file", "path": "res://src/new.gd", "content": "extends Node\n"},
            {"action": "patch_file", "path": "res://src/player.gd",
             "search": "\tpass", "replace": "\tprint(1)"}]}}
    with main.app.test_request_context("/chat", method="POST", json={}):
        result, status = payload(main._package_model_reply("Готовлю.", command, root))
    assert status == 200 and result["pending_action"]["action"] == "transaction"
    assert len(result["pending_action_diffs"]) == 2
    assert STATE.get("pending_transaction") and "pending_project_command" not in STATE
    with main.app.test_request_context(
            "/chat/confirm_action", method="POST", json={"approved": True}):
        confirmed, status = payload(main.confirm_action())
    assert status == 200 and confirmed.get("history_entry_id")

    scene_command = {"action": "project_command", "command": {
        "type": "create_scene_component", "scene": "res://scenes/main.tscn",
        "parent": ".", "name": "Health", "node_type": "Node",
        "script": "res://src/health.gd"}}
    with main.app.test_request_context("/chat", method="POST", json={}):
        scene_result, status = payload(main._package_model_reply("Сцена.", scene_command, root))
    assert status == 200 and scene_result.get("scene_prepare")
    assert STATE["pending_scene_action"]["action"]["action"] == "edit_scene"
    STATE["pending_action"] = None
    STATE["pending_scene_action"] = None

    settings_command = {"action": "project_command", "command": {
        "type": "create_input_action", "name": "jump",
        "events": [{"type": "key", "key": "SPACE"}]}}
    with main.app.test_request_context("/chat", method="POST", json={}):
        settings_result, status = payload(main._package_model_reply("Input.", settings_command, root))
    assert status == 200 and settings_result.get("project_settings_prepare")
    assert STATE["pending_project_settings_action"]["action"]["action"] == "edit_project_settings"
    print("PASS high-level compiler reuses primitive flows")
finally:
    for name, value in originals.items():
        setattr(main, name, value)
    STATE["pending_action"] = None
    STATE["pending_transaction"] = None
    STATE["pending_scene_action"] = None
    STATE["pending_project_settings_action"] = None
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(store, ignore_errors=True)
