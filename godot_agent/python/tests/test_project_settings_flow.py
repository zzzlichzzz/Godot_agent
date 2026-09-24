# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import history_manager
import main
import project_settings_actions
from server_state import STATE


def write(root, rel, text):
    absolute = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return absolute


def payload(response):
    if isinstance(response, tuple):
        return response[0].get_json(), response[1]
    return response.get_json(), response.status_code


root = tempfile.mkdtemp(prefix="project_settings_flow_project_")
store = tempfile.mkdtemp(prefix="project_settings_flow_store_")
history_manager.set_storage_dir(store)
project_file = write(root, "project.godot", "config_version=5\n")
original = open(project_file, "rb").read()
originals = {}
for name in ("_remember", "_sync_chat_after_reply", "_refresh_fs_snapshot",
             "_remember_file", "_touch_file_read", "_current_chat_info"):
    originals[name] = getattr(main, name)
main._remember = lambda *_args, **_kwargs: None
main._sync_chat_after_reply = lambda: None
main._refresh_fs_snapshot = lambda *_args: None
main._remember_file = lambda *_args: None
main._touch_file_read = lambda *_args: None
main._current_chat_info = lambda: ("settings-flow", "Settings flow")

try:
    STATE.update({"project_root": root, "pending_action": None,
                  "pending_project_settings_action": None, "addon_intent": False,
                  "addon_dir": None})
    action = {"action": "edit_project_settings", "operations": [
        {"op": "add_input_action", "name": "jump", "deadzone": 0.2}]}
    with main.app.test_request_context("/chat", method="POST", json={}):
        prepared, status = payload(main._package_model_reply("Добавляю jump.", action, root))
    assert status == 200 and prepared["project_settings_prepare"]["prepare_in_editor"]
    assert open(project_file, "rb").read() == original

    # A fully satisfied editor-side plan is a successful no-op, not a failed
    # transaction. It must not leave a rollback entry for an unchanged file.
    no_op_entry_id = history_manager.record_batch_change(
        root, "edit_project_settings", ["res://project.godot"], "settings-flow", "Settings flow")
    STATE.update({"pending_action": {"action": "edit_project_settings"},
                  "pending_project_settings_action": {
                      "action": action, "action_id": "already-satisfied",
                      "action_digest": "a" * 64, "before_hash": project_settings_actions.file_sha256(project_file),
                       "policy_snapshot": {"allow_addons": False, "allow_self_edit": False, "addon_dir": None},
                      "editor_semantic_hash": "e" * 64, "entry_id": no_op_entry_id,
                      "execution_token": "token", "state": "executing"}})
    no_op_body = {"action_id": "already-satisfied", "execution_token": "token",
                  "editor_action_kind": "project_settings", "success": True,
                  "already_satisfied": True,
                  "project_hash": project_settings_actions.file_sha256(project_file)}
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=no_op_body):
        no_op, status = payload(main.editor_action_result())
    assert status == 200 and no_op["already_satisfied"] is True
    assert no_op["history_entry_id"] is None and no_op["changed_paths"] == []
    assert history_manager.entry_info(root, no_op_entry_id) is None
    STATE["pending_action"] = None
    with main.app.test_request_context("/chat", method="POST", json={}):
        prepared, status = payload(main._package_model_reply("Добавляю jump.", action, root))
    assert status == 200 and prepared["project_settings_prepare"]["prepare_in_editor"]

    with main.app.test_request_context("/chat/confirm_action", method="POST", json={
            "approved": True, "editor_semantic_hash": "d" * 64}):
        confirmed, status = payload(main.confirm_action())
    assert status == 200 and confirmed["editor_action_kind"] == "project_settings"
    assert open(project_file, "rb").read() == original

    write(root, "project.godot", 'config_version=5\n\n[input]\njump={"deadzone":0.2,"events":[]}\n')
    result_body = {"action_id": confirmed["action_id"],
                   "execution_token": confirmed["execution_token"],
                   "editor_action_kind": "project_settings", "success": True,
                   "project_hash": project_settings_actions.file_sha256(project_file)}
    # A false no-op report must not discard the only recovery reservation.
    invalid_no_op = dict(result_body, already_satisfied=True)
    reservation = STATE["pending_project_settings_action"]["entry_id"]
    with main.app.test_request_context("/chat/editor_action/result", method="POST",
                                       json=dict(result_body, project_hash="")):
        _, status = payload(main.editor_action_result())
    assert status == 409 and STATE["pending_project_settings_action"] is not None
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=invalid_no_op):
        rejected, status = payload(main.editor_action_result())
    assert status == 409 and "already_satisfied" in rejected["error"]
    assert any(e["id"] == reservation for e in history_manager._load_journal(root))
    assert STATE["pending_project_settings_action"] is not None
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=result_body):
        final, status = payload(main.editor_action_result())
    assert status == 200 and final["requires_editor_restart"] is True
    assert STATE["pending_project_settings_action"] is None
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=result_body):
        duplicate, status = payload(main.editor_action_result())
    assert status == 200 and duplicate == final
    info = history_manager.entry_info(root, final["history_entry_id"])
    assert info and info["type"] == "edit_project_settings"
    with main.app.test_request_context("/chat/rollback", method="POST", json={
            "history_entry_id": final["history_entry_id"]}):
        rolled, status = payload(main.rollback())
    assert status == 200 and rolled["paths"] == ["res://project.godot"]
    assert rolled["requires_editor_restart"] is True
    assert open(project_file, "rb").read() == original
    print("PASS edit_project_settings Flask prepare/confirm/finalize/rollback flow")
finally:
    for name, value in originals.items():
        setattr(main, name, value)
    STATE["pending_action"] = None
    STATE["pending_project_settings_action"] = None
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(store, ignore_errors=True)
