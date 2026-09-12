# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile
import time
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
import _bootstrap  # noqa: E402,F401

import main
import runtime_debug
from server_state import STATE


def payload(response):
    if isinstance(response, tuple):
        return response[0].get_json(), response[1]
    return response.get_json(), response.status_code


root = tempfile.mkdtemp(prefix="runtime_flow_project_")
with open(os.path.join(root, "project.godot"), "w", encoding="utf-8") as handle:
    handle.write("config_version=5\n")

originals = {name: getattr(main, name) for name in (
    "_remember", "_sync_chat_after_reply", "_reply_with_self_heal")}
remembered = []
calls = []
main._remember = lambda *args: remembered.append(args)
main._sync_chat_after_reply = lambda: None
main._reply_with_self_heal = lambda prompt, _root: (calls.append(prompt) or ("Runtime проанализирован.", None))

status = {"enabled": True, "protocol": 1, "sessions": [{
    "session_id": 3, "run_id": "run-3", "active": True,
    "breaked": False, "debuggable": True, "bridge_ready": True,
}]}
try:
    STATE.update({"project_root": root, "current_chat_id": "runtime-chat",
                  "runtime_status": status, "runtime_turn_id": 9,
                  "runtime_inspections_this_turn": 0, "pending_action": None,
                  "pending_runtime_request": None})
    action = {"action": "inspect_runtime", "sections": ["tree", "metrics", "errors"]}
    with main.app.test_request_context("/chat", method="POST", json={}):
        prepared, code = payload(main._package_model_reply("Проверяю игру.", action, root))
    assert code == 200 and prepared["pending_action"]["action"] == "inspect_runtime"

    with main.app.test_request_context("/chat/confirm_action", method="POST", json={"approved": True}):
        confirmed, code = payload(main.confirm_action())
    assert code == 200 and confirmed["runtime_request"]["session_id"] == 3, (confirmed, code)
    pending = STATE["pending_runtime_request"]

    bad_token = dict(confirmed["runtime_request"], status="ok", snapshot={"tree": {"nodes": []}})
    bad_token["result_token"] = "0" * 48
    with main.app.test_request_context("/chat/runtime_inspect/result", method="POST", json=bad_token):
        _bad, bad_code = payload(main.runtime_inspect_result())
    assert bad_code == 403 and STATE["pending_runtime_request"] is pending and not calls

    stopped = dict(confirmed["runtime_request"], status="session_stopped", snapshot={})
    with main.app.test_request_context("/chat/runtime_inspect/result", method="POST", json=stopped):
        local, local_code = payload(main.runtime_inspect_result())
    assert local_code == 200 and local["runtime_status"] == "session_stopped" and not calls

    STATE["runtime_inspections_this_turn"] = 0
    with main.app.test_request_context("/chat", method="POST", json={}):
        main._package_model_reply("Повторная диагностика.", action, root)
    with main.app.test_request_context("/chat/confirm_action", method="POST", json={"approved": True}):
        confirmed, code = payload(main.confirm_action())
    ok = dict(confirmed["runtime_request"], status="ok", snapshot={
        "protocol": 1,
        "captured_at_ticks_ms": 10,
        "tree": {"nodes": [{"path": ".", "type": "Node2D"}]},
        "metrics": {"fps": 60.0}, "errors": {"items": []},
    })
    with main.app.test_request_context("/chat/runtime_inspect/result", method="POST", json=ok):
        final, final_code = payload(main.runtime_inspect_result())
    assert final_code == 200 and final["answer"] == "Runtime проанализирован."
    assert len(calls) == 1 and "Godot runtime snapshot" in calls[0]
    assert STATE["pending_runtime_request"] is None

    with main.app.test_request_context("/chat/runtime_inspect/result", method="POST", json=ok):
        _replay, replay_code = payload(main.runtime_inspect_result())
    assert replay_code == 409 and len(calls) == 1

    STATE["runtime_inspections_this_turn"] = 0
    with main.app.test_request_context("/chat", method="POST", json={}):
        main._package_model_reply("Параллельная диагностика.", action, root)
    with main.app.test_request_context("/chat/confirm_action", method="POST", json={"approved": True}):
        concurrent, code = payload(main.confirm_action())
    concurrent_body = dict(concurrent["runtime_request"], status="ok", snapshot={
        "protocol": 1, "tree": {"nodes": []}, "metrics": {"fps": 60},
        "errors": {"items": []}})
    barrier = threading.Barrier(2)
    concurrent_codes = []
    def submit_result():
        with main.app.test_request_context("/chat/runtime_inspect/result", method="POST", json=concurrent_body):
            barrier.wait()
            concurrent_codes.append(payload(main.runtime_inspect_result())[1])
    threads = [threading.Thread(target=submit_result) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sorted(concurrent_codes) == [200, 409] and len(calls) == 2

    STATE["pending_runtime_request"] = dict(runtime_debug.create_request(action, status, "runtime-chat", 9),
                                              deadline=time.time() - 1)
    expired = runtime_debug.public_request(STATE["pending_runtime_request"])
    expired.update({"status": "ok", "snapshot": {}})
    with main.app.test_request_context("/chat/runtime_inspect/result", method="POST", json=expired):
        _expired, expired_code = payload(main.runtime_inspect_result())
    assert expired_code == 410 and len(calls) == 2

    print("PASS runtime debugger prepare/confirm/result security and one follow-up flow")
finally:
    for name, value in originals.items():
        setattr(main, name, value)
    STATE["pending_action"] = None
    STATE["pending_runtime_request"] = None
    shutil.rmtree(root, ignore_errors=True)
