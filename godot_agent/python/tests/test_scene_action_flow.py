# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import history_manager
import main
import scene_actions
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


root = tempfile.mkdtemp(prefix="scene_flow_project_")
store = tempfile.mkdtemp(prefix="scene_flow_store_")
history_manager.set_storage_dir(store)
write(root, "project.godot", "config_version=5\n")
scene = write(root, "scenes/main.tscn", '[gd_scene format=3]\n\n[node name="Main" type="Node"]\n')
original_scene = open(scene, "rb").read()

originals = {}
for name in ("_remember", "_sync_chat_after_reply", "_refresh_fs_snapshot",
             "_remember_file", "_touch_file_read", "_current_chat_info"):
    originals[name] = getattr(main, name)
main._remember = lambda *_args, **_kwargs: None
main._sync_chat_after_reply = lambda: None
main._refresh_fs_snapshot = lambda *_args: None
main._remember_file = lambda *_args: None
main._touch_file_read = lambda *_args: None
main._current_chat_info = lambda: ("flow-chat", "Scene flow")

try:
    STATE.update({"project_root": root, "pending_action": None,
                  "pending_scene_action": None, "addon_intent": False,
                  "addon_dir": None})
    action = {"action": "edit_scene", "scene": "res://scenes/main.tscn",
              "operations": [{"op": "add_node", "parent": ".",
                              "name": "HUD", "type": "CanvasLayer"}]}

    with main.app.test_request_context("/chat", method="POST", json={}):
        prepared_json, prepared_status = payload(
            main._package_model_reply("Добавляю HUD.", action, root))
    assert prepared_status == 200 and prepared_json["scene_prepare"]["prepare_in_editor"]
    assert open(scene, "rb").read() == original_scene
    assert isinstance(STATE["pending_scene_action"], dict)
    with main.app.test_request_context(
            "/chat/confirm_action", method="POST", json={
                "approved": True, "editor_semantic_hash": "a" * 64}):
        confirm_json, confirm_status = payload(main.confirm_action())
    assert confirm_status == 200 and confirm_json["execute_in_editor"] is True
    assert open(scene, "rb").read() == original_scene
    assert history_manager.entry_info(root, STATE["pending_scene_action"]["entry_id"]) is None

    # Wrong capability token cannot finalize or mutate state.
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json={
            "action_id": confirm_json["action_id"], "execution_token": "wrong",
            "success": True, "scene_hash": scene_actions.file_sha256(scene)}):
        denied_json, denied_status = payload(main.editor_action_result())
    assert denied_status == 403 and "токен" in denied_json["error"].lower()
    assert STATE["pending_scene_action"]["state"] == "executing"

    # Simulate authoritative Godot ResourceSaver output, then finalize once.
    write(root, "scenes/main.tscn", '[gd_scene format=3]\n\n[node name="Main" type="Node"]\n'
          '[node name="HUD" type="CanvasLayer" parent="."]\n')
    after_hash = scene_actions.file_sha256(scene)
    result_body = {"action_id": confirm_json["action_id"],
                   "execution_token": confirm_json["execution_token"],
                   "success": True, "scene_hash": after_hash}
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=result_body):
        final_json, final_status = payload(main.editor_action_result())
    assert final_status == 200 and final_json["history_entry_id"]
    assert STATE["pending_scene_action"] is None
    info = history_manager.entry_info(root, final_json["history_entry_id"])
    assert info and info["type"] == "edit_scene"
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=result_body):
        duplicate_json, duplicate_status = payload(main.editor_action_result())
    assert duplicate_status == 200 and duplicate_json == final_json
    ok, _message, _force, paths, _diff = history_manager.rollback_entry(
        root, final_json["history_entry_id"])
    assert ok and paths == ["res://scenes/main.tscn"]
    assert open(scene, "rb").read() == original_scene

    # A failed editor execution restores the reserved snapshot.
    STATE.update({"pending_action": None, "pending_scene_action": None})
    with main.app.test_request_context("/chat", method="POST", json={}):
        payload(main._package_model_reply("Повтор.", action, root))
    with main.app.test_request_context(
            "/chat/confirm_action", method="POST", json={
                "approved": True, "editor_semantic_hash": "b" * 64}):
        retry_json, retry_status = payload(main.confirm_action())
    assert retry_status == 200
    write(root, "scenes/main.tscn", "broken editor result\n")
    broken_hash = scene_actions.file_sha256(scene)
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json={
            "action_id": retry_json["action_id"],
            "execution_token": retry_json["execution_token"],
            "success": False, "scene_hash": broken_hash, "error": "save failed"}):
        failed_json, failed_status = payload(main.editor_action_result())
    assert failed_status == 200 and failed_json["restored"] is True
    assert open(scene, "rb").read() == original_scene
    assert STATE["pending_scene_action"] is None

    # A mismatching editor report also restores the reserved snapshot instead
    # of leaving an unfinalized transaction behind.
    STATE.update({"pending_action": None, "pending_scene_action": None})
    with main.app.test_request_context("/chat", method="POST", json={}):
        payload(main._package_model_reply("Несовпадающий отчёт.", action, root))
    with main.app.test_request_context(
            "/chat/confirm_action", method="POST", json={
                "approved": True, "editor_semantic_hash": "c" * 64}):
        mismatch_confirm, mismatch_status = payload(main.confirm_action())
    assert mismatch_status == 200
    write(root, "scenes/main.tscn", "partially saved scene\n")
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json={
            "action_id": mismatch_confirm["action_id"],
            "execution_token": mismatch_confirm["execution_token"],
            "success": True, "scene_hash": "0" * 64}):
        mismatch_json, mismatch_result_status = payload(main.editor_action_result())
    assert mismatch_result_status == 200 and mismatch_json["restored"] is True
    assert open(scene, "rb").read() == original_scene
    assert STATE["pending_scene_action"] is None

    print("PASS edit_scene Flask prepare/confirm/finalize/recovery flow")
finally:
    for name, value in originals.items():
        setattr(main, name, value)
    STATE["pending_action"] = None
    STATE["pending_scene_action"] = None
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(store, ignore_errors=True)
