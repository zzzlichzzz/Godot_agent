# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import main
from server_state import STATE


def payload(response):
    if isinstance(response, tuple):
        return response[0].get_json(), response[1]
    return response.get_json(), response.status_code


root = tempfile.mkdtemp(prefix="runtime_check_flow_")
os.makedirs(os.path.join(root, "scenes"))
with open(os.path.join(root, "project.godot"), "w", encoding="utf-8") as handle:
    handle.write("config_version=5\n")
with open(os.path.join(root, "scenes", "main.tscn"), "w", encoding="utf-8") as handle:
    handle.write('[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n')

originals = {name: getattr(main, name) for name in (
    "_remember", "_sync_chat_after_reply", "_reply_with_self_heal")}
calls = []
main._remember = lambda *_args: None
main._sync_chat_after_reply = lambda: None
main._reply_with_self_heal = lambda prompt, _root: (calls.append(prompt) or ("Проверка разобрана.", None))

status = {"enabled": True, "protocol": 1, "sessions": []}
ready_status = {"enabled": True, "protocol": 1, "sessions": [{
    "session_id": 8, "run_id": "run-8", "active": True, "breaked": False,
    "debuggable": True, "bridge_ready": True, "capabilities": ["run_check_v1"]}]}
action = {"action": "run_check", "scene": "res://scenes/main.tscn", "steps": [
    {"op": "assert_node", "node": ".", "exists": True}]}
try:
    STATE.update({"project_root": root, "user_data_dir": root,
                  "current_chat_id": "check-chat", "runtime_status": status,
                  "runtime_turn_id": 5, "runtime_inspections_this_turn": 0,
                  "pending_action": None, "pending_runtime_check": None})
    with main.app.test_request_context("/chat", method="POST", json={}):
        prepared, code = payload(main._package_model_reply("Проверяю сцену.", action, root))
    assert code == 200 and prepared["pending_action"]["action"] == "run_check"
    with main.app.test_request_context("/chat/confirm_action", method="POST", json={"approved": True}):
        confirmed, code = payload(main.confirm_action())
    assert code == 200 and confirmed["runtime_check_request"]["scene"] == action["scene"]
    public = confirmed["runtime_check_request"]

    bind = dict(public, session_id=8, run_id="run-8", runtime_status=ready_status)
    with main.app.test_request_context("/chat/runtime_check/bind", method="POST", json=bind):
        bound, code = payload(main.runtime_check_bind())
    assert code == 200 and "result_token" not in bound["game_request"]
    with main.app.test_request_context("/chat/runtime_check/bind", method="POST", json=bind):
        rebound, rebound_code = payload(main.runtime_check_bind())
    assert rebound_code == 200 and rebound["game_request"] == bound["game_request"]

    good_result = {"protocol": 1, "scene": action["scene"], "duration_ms": 5,
                   "assertions": [{"index": 0, "op": "assert_node", "actual": True}],
                   "bridge_errors": [], "step_errors": []}
    result_body = dict(public, session_id=8, run_id="run-8", status="ok", result=good_result)
    with main.app.test_request_context("/chat/runtime_check/result", method="POST", json=result_body):
        done, code = payload(main.runtime_check_result())
    assert code == 200 and done["passed"] and not calls
    with main.app.test_request_context("/chat/runtime_check/result", method="POST", json=result_body):
        replay, replay_code = payload(main.runtime_check_result())
    assert replay_code == 200 and replay == done

    STATE.update({"runtime_status": status, "runtime_inspections_this_turn": 0,
                  "pending_action": None})
    with main.app.test_request_context("/chat", method="POST", json={}):
        main._package_model_reply("Проверяю ошибку.", action, root)
    with main.app.test_request_context("/chat/confirm_action", method="POST", json={"approved": True}):
        failed_public, _ = payload(main.confirm_action())
    failed_public = failed_public["runtime_check_request"]
    bind = dict(failed_public, session_id=8, run_id="run-8", runtime_status=ready_status)
    with main.app.test_request_context("/chat/runtime_check/bind", method="POST", json=bind):
        payload(main.runtime_check_bind())
    failed_result = dict(good_result, assertions=[
        {"index": 0, "op": "assert_node", "actual": False}])
    result_body = dict(failed_public, session_id=8, run_id="run-8",
                       status="ok", result=failed_result)
    with main.app.test_request_context("/chat/runtime_check/result", method="POST", json=result_body):
        failed, code = payload(main.runtime_check_result())
    assert code == 200 and not failed["passed"] and len(calls) == 1
    assert "Godot local game check" in calls[0]

    STATE.update({"runtime_status": status, "runtime_inspections_this_turn": 0,
                  "pending_action": None})
    with main.app.test_request_context("/chat", method="POST", json={}):
        main._package_model_reply("Проверяю конкурентный результат.", action, root)
    with main.app.test_request_context("/chat/confirm_action", method="POST", json={"approved": True}):
        concurrent_public, _ = payload(main.confirm_action())
    concurrent_public = concurrent_public["runtime_check_request"]
    bind = dict(concurrent_public, session_id=8, run_id="run-8", runtime_status=ready_status)
    with main.app.test_request_context("/chat/runtime_check/bind", method="POST", json=bind):
        payload(main.runtime_check_bind())
    concurrent_body = dict(concurrent_public, session_id=8, run_id="run-8",
                           status="ok", result=good_result)
    barrier = threading.Barrier(2)
    concurrent_results = []

    def submit_result():
        with main.app.test_request_context("/chat/runtime_check/result", method="POST", json=concurrent_body):
            barrier.wait()
            concurrent_results.append(payload(main.runtime_check_result()))

    threads = [threading.Thread(target=submit_result) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(code for _body, code in concurrent_results) == [200, 200]
    assert concurrent_results[0][0] == concurrent_results[1][0]
    print("PASS runtime check prepare, bind, pass/fail, replay and model-call policy")
finally:
    for name, value in originals.items():
        setattr(main, name, value)
    STATE["pending_action"] = None
    STATE["pending_runtime_check"] = None
    shutil.rmtree(root, ignore_errors=True)
