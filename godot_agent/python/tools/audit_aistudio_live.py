"""Opt-in AI Studio audit. Uses account quota, an isolated project, and own server.

No project files are sent. Chrome uses the normal saved browser profile.
Never retries a chat POST. Evidence is stored only under --session-dir.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import _bootstrap  # noqa: E402,F401
from cdp_ws import CDPSession, list_targets
from ai_parser import JS_GET_ANSWER_STREAM

HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--turns", type=int, default=1, choices=range(1, 5))
    parser.add_argument("--navigate", action="store_true",
                        help="Restore the first chat before turn 2; start a fresh chat before turn 3")
    parser.add_argument("--controls", action="store_true",
                        help="Check live draft edits, busy guards, and cancellation of one extra request")
    args = parser.parse_args()
    if args.navigate and args.turns < 3:
        parser.error("--navigate requires --turns 3 or 4")
    owner = args.session_dir.resolve()
    owner.mkdir(parents=False, exist_ok=False)
    project, user = owner / "project", owner / "user"
    project.mkdir()
    user.mkdir()
    (project / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Browser audit sandbox"\n', encoding="utf-8")
    token = secrets.token_hex(32)
    (user / "godot_agent_token.txt").write_text(token, encoding="utf-8")
    context = {"project_root": str(project), "user_data_dir": str(user)}

    def request(path, data=None, timeout=330):
        req = urllib.request.Request("http://127.0.0.1:%d" % args.port + path,
            data=None if data is None else json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Agent-Token": token})
        with HTTP.open(req, timeout=timeout) as response:
            return json.load(response)

    with socket.socket() as check:
        if check.connect_ex(("127.0.0.1", args.port)) == 0:
            raise RuntimeError("Audit port already occupied; refusing to touch another server")
    env = dict(os.environ, GODOT_AGENT_CONFIG_DIR=str(owner / "config"))
    cdp = None
    with (owner / "stdout.log").open("w", encoding="utf-8") as out, \
            (owner / "stderr.log").open("w", encoding="utf-8") as err:
        launch = ("import runpy; from flask import Flask; original = Flask.run; "
                  "Flask.run = lambda self, *a, **kw: original(self, *a, **dict(kw, port=%d)); "
                  "runpy.run_path('main.py', run_name='__main__')") % args.port
        server = subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-u", "-c", launch],
            cwd=ROOT, env=env, stdout=out, stderr=err)
        try:
            deadline = time.monotonic() + 60
            while True:
                if server.poll() is not None:
                    raise RuntimeError("Server exited; inspect sandbox logs")
                try:
                    request("/browser/status", {}, timeout=2)
                    break
                except (urllib.error.URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.5)
            opened = request("/chats/new", {**context, "site_id": "aistudio"})
            context["chat_id"] = opened["current_id"]
            time.sleep(3)
            browser = request("/browser/status", {})
            targets = [t for t in list_targets() if t.get("type") == "page"
                       and urllib.parse.urlsplit(t.get("url", "")).hostname == "aistudio.google.com"
                       and t.get("url") == browser.get("url")]
            if len(targets) != 1:
                raise RuntimeError("Cannot uniquely identify the server's AI Studio tab")
            cdp = CDPSession(targets[0]["webSocketDebuggerUrl"])
            posts = set()

            def observe(params):
                req = params.get("request", {})
                if req.get("method") == "POST" and "MakerSuiteService/GenerateContent" in req.get("url", ""):
                    posts.add(params["requestId"])

            cdp.on_event("Network.requestWillBeSent", observe)
            cdp.send_command("Network.enable")
            draft = "draft [array]\n    indented \u0442\u0435\u0441\u0442"
            if args.controls:
                for seq, text in enumerate((draft, "short", draft), 1):
                    mirrored = request("/chat/live_input", {"seq": seq, "text": text})
                    assert mirrored.get("applied"), mirrored
                    value = cdp.send_command("Runtime.evaluate", {
                        "expression": "document.querySelector('textarea').value", "returnByValue": True,
                    })["result"].get("value")
                    assert value == text, "Live draft differs from the requested text"
                assert not posts, "Live input unexpectedly submitted a request"
            previous_markers = []
            for turn in range(args.turns):
                if args.navigate and turn in (1, 2):
                    first_id = context["chat_id"]
                    opened = request("/chats/new", {**context, "site_id": "aistudio"})
                    assert opened["current_id"] != first_id
                    if turn == 1:
                        restored = request("/chats/open", {**context, "id": first_id})
                        assert restored["current_id"] == first_id
                        assert previous_markers[0] in json.dumps(restored["transcript"])
                    else:
                        context["chat_id"] = opened["current_id"]
                    time.sleep(3)
                marker = "AUDIT_" + secrets.token_hex(6)
                count = 80 if turn == 0 else 8
                expected = "\n".join("%s_%03d [array] \u0442\u0435\u0441\u0442" % (marker, n) for n in range(1, count + 1))
                prompt = ("Browser transport test in an empty disposable project. Do not use tools or file actions. "
                          "Return only the NEW lines between BEGIN and END verbatim in one plain code block, "
                          "without omissions or previous answers, then the normal final completion marker.\nBEGIN\n" + expected + "\nEND")
                (owner / ("send-attempted-%d" % turn)).write_text("One POST only; no automatic retry", encoding="utf-8")
                samples = []
                failure = None
                before_posts = set(posts)
                started = time.monotonic()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(request, "/chat", {**context, "prompt": prompt})
                    while not future.done():
                        samples.append(request("/chat/progress", timeout=5))
                        time.sleep(0.5)
                    try:
                        result = future.result()
                    except Exception as exc:
                        failure = exc
                        result = {"error": str(exc)}
                        if isinstance(exc, urllib.error.HTTPError):
                            result["body"] = exc.read().decode("utf-8", errors="replace")
                dom = cdp.send_command("Runtime.evaluate", {
                    "expression": "(function(){" + JS_GET_ANSWER_STREAM + "})()", "returnByValue": True,
                })["result"].get("value", "")
                answer = result.get("answer", "")
                evidence = {"context": dict(context), "seconds": round(time.monotonic() - started, 2),
                            "posts": sorted(posts - before_posts), "result": result, "dom": dom,
                            "progress": samples, "expected": expected,
                            "browser": request("/browser/status", {})}
                (owner / ("evidence-%d.json" % turn)).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
                if failure is not None:
                    raise failure
                assert len(posts - before_posts) == 1, "Expected exactly one generation POST per turn"
                assert not result.get("pending_action"), "Unexpected file action"
                for line in expected.splitlines():
                    assert line in dom, "DOM omitted " + line
                    # Server presentation escapes BBCode brackets.
                    assert line.translate(str.maketrans({"[": "[lb]", "]": "[rb]"})) in answer or line in answer, "Server omitted " + line
                assert all(old not in answer and old not in dom for old in previous_markers), "Previous answer leaked"
                previous_markers.append(marker)
                print("PASS live AI Studio turn %d: %d Unicode/code lines, one POST, server/DOM agree; %.2fs" % (turn + 1, count, evidence["seconds"]))
                if args.controls and turn == 0:
                    mirrored = request("/chat/live_input", {"seq": 10, "text": draft})
                    assert mirrored.get("applied"), mirrored
                    value = cdp.send_command("Runtime.evaluate", {
                        "expression": "document.querySelector('textarea').value", "returnByValue": True,
                    })["result"].get("value")
                    assert value == draft, "Identical draft was lost after sending"
                    cleared = request("/chat/live_input", {"seq": 11, "text": ""})
                    assert cleared.get("applied"), cleared
            if args.controls:
                before_posts = set(posts)
                prompt = ("No tools or file actions. Produce exactly 160 numbered lines, each containing "
                          "the number and the words CANCEL_AUDIT transport check, then the completion marker.")
                (owner / "cancel-send-attempted").write_text("One POST only", encoding="utf-8")
                started = time.monotonic()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(request, "/chat", {**context, "prompt": prompt})
                    while posts == before_posts and not future.done():
                        if time.monotonic() - started > 60:
                            raise TimeoutError("No accepted POST for cancellation test")
                        time.sleep(0.1)
                    assert not future.done(), "Response completed before cancellation could be tested"
                    busy = request("/chat/live_input", {"seq": 20, "text": "MUST_NOT_BE_TYPED"})
                    assert busy.get("reason") == "busy" and not busy.get("applied"), busy
                    try:
                        request("/chats/new", {**context, "site_id": "aistudio"})
                    except urllib.error.HTTPError as exc:
                        assert exc.code == 409, exc.code
                    else:
                        raise AssertionError("Navigation was allowed during generation")
                    stopped = request("/chat/stop", {})
                    result = future.result(timeout=30)
                progress = request("/chat/progress")
                evidence = {"posts": sorted(posts - before_posts), "stop": stopped,
                            "busy": busy, "result": result, "progress": progress,
                            "seconds": round(time.monotonic() - started, 2)}
                (owner / "controls.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
                assert len(posts - before_posts) == 1, "Cancellation triggered another POST"
                assert "\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e" in result.get("answer", ""), result
                assert not result.get("pending_action") and not progress.get("active"), evidence
                print("PASS live controls: exact draft edits/reinsert, no draft submit, busy guards, one cancelled POST")
            print("Evidence:", owner)
        finally:
            if cdp is not None:
                cdp.close()
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)


if __name__ == "__main__":
    main()
