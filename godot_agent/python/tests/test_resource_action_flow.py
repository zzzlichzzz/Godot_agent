# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import history_manager
import main
import resource_actions
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


root = tempfile.mkdtemp(prefix="resource_flow_project_")
store = tempfile.mkdtemp(prefix="resource_flow_store_")
history_manager.set_storage_dir(store)
write(root, "project.godot", "config_version=5\n")
resource = write(root, "resources/data.tres", '[gd_resource type="Resource" format=3]\n')
with open(resource, "rb") as handle:
    original = handle.read()

originals = {}
for name in ("_remember", "_sync_chat_after_reply", "_refresh_fs_snapshot",
             "_remember_file", "_touch_file_read", "_current_chat_info"):
    originals[name] = getattr(main, name)
main._remember = lambda *_args, **_kwargs: None
main._sync_chat_after_reply = lambda: None
main._refresh_fs_snapshot = lambda *_args: None
main._remember_file = lambda *_args: None
main._touch_file_read = lambda *_args: None
main._current_chat_info = lambda: ("resource-chat", "Resource flow")

try:
    STATE.update({"project_root": root, "pending_action": None,
                  "pending_resource_action": None, "addon_intent": False,
                  "addon_dir": None})
    action = {"action": "edit_resource", "resource": "res://resources/data.tres",
              "operations": [{"op": "set_property", "target": [], "property": "value",
                              "value": {"type": "int", "value": 2}}]}
    with main.app.test_request_context("/chat", method="POST", json={}):
        prepared_json, status = payload(main._package_model_reply("Изменяю ресурс.", action, root))
    assert status == 200 and prepared_json["resource_prepare"]["prepare_in_editor"]
    assert STATE["pending_resource_action"]["state"] == "preview"
    with open(resource, "rb") as handle:
        assert handle.read() == original

    with main.app.test_request_context("/chat/confirm_action", method="POST", json={
            "approved": True, "editor_semantic_hash": "a" * 64,
            "dependency_fingerprint": "b" * 64}):
        confirm_json, status = payload(main.confirm_action())
    assert status == 200 and confirm_json["editor_action_kind"] == "resource"
    assert confirm_json["expected_dependency_fingerprint"] == "b" * 64
    assert history_manager.entry_info(root, STATE["pending_resource_action"]["entry_id"]) is None

    with main.app.test_request_context("/chat/editor_action/result", method="POST", json={
            "editor_action_kind": "unknown", "action_id": confirm_json["action_id"],
            "execution_token": confirm_json["execution_token"]}):
        unknown_json, unknown_status = payload(main.editor_action_result())
    assert unknown_status == 400 and "неизвест" in unknown_json["error"].lower()

    write(root, "resources/data.tres",
          '[gd_resource type="Resource" format=3]\n\n[resource]\nvalue = 2\n')
    after_hash = resource_actions.file_sha256(resource)
    body = {"editor_action_kind": "resource", "action_id": confirm_json["action_id"],
            "execution_token": confirm_json["execution_token"], "success": True,
            "resource_hash": after_hash}
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=body):
        final_json, status = payload(main.editor_action_result())
    assert status == 200 and final_json["history_entry_id"]
    assert STATE["pending_resource_action"] is None
    info = history_manager.entry_info(root, final_json["history_entry_id"])
    assert info and info["type"] == "edit_resource"
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=body):
        duplicate_json, duplicate_status = payload(main.editor_action_result())
    assert duplicate_status == 200 and duplicate_json == final_json

    # Post-commit cache refresh failures must not turn an already committed
    # editor transaction into an unrecoverable 500 on retry.
    original_note = main.librarian.note_files_changed
    main.librarian.note_files_changed = lambda *_args: (_ for _ in ()).throw(RuntimeError("cache"))
    try:
        with main.app.test_request_context("/chat/editor_action/result", method="POST", json=body):
            cached_json, cached_status = payload(main.editor_action_result())
        assert cached_status == 200 and cached_json == final_json
    finally:
        main.librarian.note_files_changed = original_note

    # A post-commit cache exception on the first finalize is also terminal and
    # idempotent: history remains committed and retries return the cached 200.
    second_action = {"action": "edit_resource", "resource": "res://resources/data.tres",
                     "operations": [{"op": "set_property", "target": [], "property": "value",
                                     "value": {"type": "int", "value": 3}}]}
    with main.app.test_request_context("/chat", method="POST", json={}):
        _second_prepared, status = payload(main._package_model_reply("Ещё правка.", second_action, root))
    assert status == 200
    with main.app.test_request_context("/chat/confirm_action", method="POST", json={
            "approved": True, "editor_semantic_hash": "c" * 64,
            "dependency_fingerprint": "d" * 64}):
        second_confirm, status = payload(main.confirm_action())
    assert status == 200
    write(root, "resources/data.tres",
          '[gd_resource type="Resource" format=3]\n\n[resource]\nvalue = 3\n')
    second_body = {"editor_action_kind": "resource", "action_id": second_confirm["action_id"],
                   "execution_token": second_confirm["execution_token"], "success": True,
                   "resource_hash": resource_actions.file_sha256(resource)}
    original_note = main.librarian.note_files_changed
    main.librarian.note_files_changed = lambda *_args: (_ for _ in ()).throw(RuntimeError("cache"))
    try:
        with main.app.test_request_context("/chat/editor_action/result", method="POST", json=second_body):
            second_final, second_status = payload(main.editor_action_result())
    finally:
        main.librarian.note_files_changed = original_note
    assert second_status == 200 and second_final["history_entry_id"]
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=second_body):
        second_retry, second_retry_status = payload(main.editor_action_result())
    assert second_retry_status == 200 and second_retry == second_final
    ok, _message, _force, _paths, _diff = history_manager.rollback_entry(
        root, second_final["history_entry_id"])
    assert ok

    # If replacement lost the target file, an empty actual hash must not block
    # restoring the reserved snapshot.
    with main.app.test_request_context("/chat", method="POST", json={}):
        _third_prepared, status = payload(main._package_model_reply("Recovery.", second_action, root))
    assert status == 200
    with main.app.test_request_context("/chat/confirm_action", method="POST", json={
            "approved": True, "editor_semantic_hash": "e" * 64,
            "dependency_fingerprint": "f" * 64}):
        third_confirm, status = payload(main.confirm_action())
    assert status == 200
    os.remove(resource)
    missing_body = {"editor_action_kind": "resource", "action_id": third_confirm["action_id"],
                    "execution_token": third_confirm["execution_token"], "success": False,
                    "resource_hash": ""}
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=missing_body):
        missing_final, missing_status = payload(main.editor_action_result())
    assert missing_status == 200 and missing_final["restored"]
    with open(resource, "rb") as handle:
        assert b"value = 2" in handle.read()
    ok, _message, _force, paths, _diff = history_manager.rollback_entry(
        root, final_json["history_entry_id"])
    assert ok and paths == ["res://resources/data.tres"]
    with open(resource, "rb") as handle:
        assert handle.read() == original

    print("PASS edit_resource Flask prepare/confirm/finalize/rollback flow")
finally:
    for name, value in originals.items():
        setattr(main, name, value)
    STATE["pending_action"] = None
    STATE["pending_resource_action"] = None
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(store, ignore_errors=True)
