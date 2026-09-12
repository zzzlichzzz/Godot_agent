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

    # Typed scene creation uses the same editor transaction, but history knows
    # the file did not exist and rollback therefore removes it.
    create_action = {
        "action": "create_scene", "scene": "res://scenes/created.tscn",
        "root": {"name": "Created", "type": "Node2D"}, "operations": [],
    }
    created = os.path.join(root, "scenes", "created.tscn")
    STATE.update({"pending_action": None, "pending_scene_action": None})
    with main.app.test_request_context("/chat", method="POST", json={}):
        create_prepare, create_prepare_status = payload(
            main._package_model_reply("Создаю сцену.", create_action, root))
    assert create_prepare_status == 200 and create_prepare["scene_prepare"]["prepare_in_editor"]
    assert not os.path.exists(created)
    with main.app.test_request_context(
            "/chat/confirm_action", method="POST", json={
                "approved": True, "editor_semantic_hash": "d" * 64}):
        create_confirm, create_confirm_status = payload(main.confirm_action())
    assert create_confirm_status == 200 and not os.path.exists(created)
    staged_created = scene_actions.staged_scene_path(created, create_confirm["action_id"])
    write(root, os.path.relpath(staged_created, root).replace("\\", "/"),
          '[gd_scene format=3]\n\n[node name="Created" type="Node2D"]\n')
    staged_created_hash = scene_actions.file_sha256(staged_created)
    create_result = {"action_id": create_confirm["action_id"],
                     "execution_token": create_confirm["execution_token"],
                     "success": True, "scene_hash": staged_created_hash,
                     "staged_hash": staged_created_hash,
                     "target_written": False}
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json=create_result):
        created_json, created_status = payload(main.editor_action_result())
    assert created_status == 200 and created_json["history_entry_id"]
    assert os.path.isfile(created) and not os.path.exists(staged_created)
    created_info = history_manager.entry_info(root, created_json["history_entry_id"])
    assert created_info and created_info["type"] == "create_scene"
    ok, _message, _force, paths, _diff = history_manager.rollback_entry(
        root, created_json["history_entry_id"])
    assert ok and paths == ["res://scenes/created.tscn"] and not os.path.exists(created)

    # A confirmed partial write is owned by the agent and can be removed.
    partial_action = dict(create_action, scene="res://scenes/partial.tscn")
    partial = os.path.join(root, "scenes", "partial.tscn")
    STATE.update({"pending_action": None, "pending_scene_action": None})
    with main.app.test_request_context("/chat", method="POST", json={}):
        payload(main._package_model_reply("Частичное создание.", partial_action, root))
    with main.app.test_request_context("/chat/confirm_action", method="POST", json={
            "approved": True, "editor_semantic_hash": "e" * 64}):
        partial_confirm, _status = payload(main.confirm_action())
    write(root, "scenes/partial.tscn", "partial output\n")
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json={
            "action_id": partial_confirm["action_id"],
            "execution_token": partial_confirm["execution_token"],
            "success": False, "scene_hash": scene_actions.file_sha256(partial),
            "target_written": True}):
        partial_json, partial_status = payload(main.editor_action_result())
    assert partial_status == 200 and partial_json["restored"] is True
    assert not os.path.exists(partial)

    # A file created externally during the transaction is never deleted when
    # the executor reports it did not write the target.
    collision_action = dict(create_action, scene="res://scenes/external.tscn")
    external = os.path.join(root, "scenes", "external.tscn")
    STATE.update({"pending_action": None, "pending_scene_action": None})
    with main.app.test_request_context("/chat", method="POST", json={}):
        payload(main._package_model_reply("Проверка коллизии.", collision_action, root))
    with main.app.test_request_context("/chat/confirm_action", method="POST", json={
            "approved": True, "editor_semantic_hash": "f" * 64}):
        collision_confirm, _status = payload(main.confirm_action())
    write(root, "scenes/external.tscn", "external owner\n")
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json={
            "action_id": collision_confirm["action_id"],
            "execution_token": collision_confirm["execution_token"],
            "success": False, "scene_hash": scene_actions.file_sha256(external),
            "target_written": False}):
        collision_json, collision_status = payload(main.editor_action_result())
    assert collision_status == 200 and collision_json["restored"] is True
    assert open(external, "rb").read() == b"external owner\n"

    # A destination created after Godot staged the scene wins atomically. The
    # server never overwrites it and discards the agent-owned staged file.
    race_action = dict(create_action, scene="res://scenes/race.tscn")
    race = os.path.join(root, "scenes", "race.tscn")
    STATE.update({"pending_action": None, "pending_scene_action": None})
    with main.app.test_request_context("/chat", method="POST", json={}):
        payload(main._package_model_reply("Проверка гонки.", race_action, root))
    with main.app.test_request_context("/chat/confirm_action", method="POST", json={
            "approved": True, "editor_semantic_hash": "1" * 64}):
        race_confirm, _status = payload(main.confirm_action())
    staged_race = scene_actions.staged_scene_path(race, race_confirm["action_id"])
    write(root, os.path.relpath(staged_race, root).replace("\\", "/"),
          '[gd_scene format=3]\n\n[node name="Agent" type="Node2D"]\n')
    staged_race_hash = scene_actions.file_sha256(staged_race)
    write(root, "scenes/race.tscn", "external race winner\n")
    with main.app.test_request_context("/chat/editor_action/result", method="POST", json={
            "action_id": race_confirm["action_id"],
            "execution_token": race_confirm["execution_token"],
            "success": True, "scene_hash": staged_race_hash,
            "staged_hash": staged_race_hash, "target_written": False}):
        race_json, race_status = payload(main.editor_action_result())
    assert race_status == 409 and race_json["restored"] is True
    assert open(race, "rb").read() == b"external race winner\n"
    assert not os.path.exists(staged_race)

    print("PASS edit/create scene Flask prepare/confirm/finalize/recovery flow")
finally:
    for name, value in originals.items():
        setattr(main, name, value)
    STATE["pending_action"] = None
    STATE["pending_scene_action"] = None
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(store, ignore_errors=True)
