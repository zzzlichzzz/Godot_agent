# -*- coding: utf-8 -*-
"""Passive first-message Arena diagnostic.

Attaches at browser level before a new Arena target is created. It records all
Arena POST/response bodies from every attached page target, so it can diagnose
the /text/direct -> /c/<id> transition. It never types, clicks, navigates, or
sends a request to Arena.
"""
import base64
import json
import sys
import threading
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
for _d in (_HERE, _HERE / "browser", _HERE / "parsers", _HERE / "server"):
    if _d.is_dir() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from browser.browser_manager import setup_browser
from browser.cdp_ws import CDPSession, browser_ws_url

OUT_DIR = _HERE.parent.parent / "временно"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "arena_first_diagnostic.json"

TARGET = "/nextjs-api/stream/"
lock = threading.Lock()
records = []
sessions = {}
done = threading.Event()
cdp = None


def safe_payload(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            low = str(key).lower()
            if any(marker in low for marker in (
                    "token", "cookie", "authorization", "credential", "secret")):
                out[key] = "[REDACTED]"
            else:
                out[key] = safe_payload(item)
        return out
    if isinstance(value, list):
        return [safe_payload(item) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return value
        return safe_payload(decoded)
    return value


def log(message):
    print("[arena_first] %s" % message)


def save_records_locked():
    temp_file = OUT_FILE.with_suffix(".json.tmp")
    temp_file.write_text(json.dumps(records, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    temp_file.replace(OUT_FILE)


def record_event(session_id, kind, params, extra=None):
    item = {"session_id": session_id, "kind": kind,
            "ts": time.time(), "params": safe_payload(params)}
    if extra:
        item.update(extra)
    with lock:
        records.append(item)
        save_records_locked()


def on_attached(params, _parent_session):
    session_id = params.get("sessionId")
    info = params.get("targetInfo") or {}
    if not session_id:
        return
    url = info.get("url") or ""
    target_id = str(info.get("targetId") or "")
    if target_id and any(state.get("target_id") == target_id
                         for state in sessions.values()):
        threading.Thread(
            target=lambda: cdp.send_command(
                "Runtime.runIfWaitingForDebugger", session_id=session_id,
                timeout=3.0), daemon=True).start()
        return
    threading.Thread(target=configure_session,
                     args=(session_id, info), daemon=True).start()


def configure_session(session_id, info):
    url = info.get("url") or ""
    # Every paused target must be resumed, otherwise unrelated new tabs freeze.
    if info.get("type") != "page" or "arena.ai" not in url:
        try:
            cdp.send_command("Runtime.runIfWaitingForDebugger",
                             session_id=session_id, timeout=3.0)
        except Exception:
            pass
        return
    sessions[session_id] = {"url": url, "target_id": info.get("targetId"),
                            "requests": {}}
    log("attached session=%s target=%s %s"
        % (session_id, info.get("targetId"), url))
    try:
        cdp.send_command("Network.enable", session_id=session_id)
        cdp.send_command("Runtime.runIfWaitingForDebugger", session_id=session_id)
    except Exception as e:
        log("enable failed for %s: %s" % (session_id, e))


def on_request(params, session_id):
    state = sessions.get(session_id)
    if not state:
        return
    req = params.get("request") or {}
    url = req.get("url") or ""
    if (req.get("method") or "").upper() != "POST":
        return
    request_id = params.get("requestId")
    state["requests"][request_id] = {
        "url": url, "body": req.get("postData"), "chat_candidate": False,
    }
    record_event(session_id, "request", {
        "requestId": request_id, "url": url,
        "method": req.get("method"), "postData": req.get("postData"),
    })
    if "arena.ai" in url:
        log("POST %s requestId=%s" % (url, request_id))


def on_response(params, session_id):
    state = sessions.get(session_id)
    if not state:
        return
    response = params.get("response") or {}
    url = response.get("url") or ""
    request_id = params.get("requestId")
    if request_id not in state["requests"]:
        return
    record_event(session_id, "response", {
        "requestId": request_id, "url": url,
        "status": response.get("status"),
        "mimeType": response.get("mimeType"),
    })
    state["requests"][request_id]["mimeType"] = response.get("mimeType")
    state["requests"][request_id]["chat_candidate"] = bool(
        "text/event-stream" in (response.get("mimeType") or "")
        or "post-to-evaluation" in url)


def fetch_body(session_id, request_id):
    try:
        result = cdp.send_command("Network.getResponseBody",
                                  {"requestId": request_id}, timeout=8.0,
                                  session_id=session_id)
        body = result.get("body") or ""
        if result.get("base64Encoded"):
            raw = base64.b64decode(body)
            body = {"base64": base64.b64encode(raw).decode("ascii")}
        state = sessions.get(session_id) or {}
        request = (state.get("requests") or {}).get(request_id) or {}
        candidate = bool(request.get("chat_candidate"))
        record_event(session_id, "response_body", {
            "requestId": request_id, "body": body,
            "url": request.get("url"), "chat_candidate": candidate,
        })
        if candidate:
            done.set()
    except Exception as e:
        record_event(session_id, "response_body_error", {
            "requestId": request_id, "error": str(e),
        })


def on_loading_finished(params, session_id):
    state = sessions.get(session_id)
    request_id = params.get("requestId")
    if not state or request_id not in state["requests"]:
        return
    # CDP commands from the CDP reader callback would deadlock its own reader.
    threading.Thread(target=fetch_body, args=(session_id, request_id),
                     daemon=True).start()


def on_detached(params, _parent_session):
    session_id = params.get("sessionId")
    if session_id in sessions:
        log("detached %s" % session_id)
        sessions.pop(session_id, None)


def main():
    global cdp
    setup_browser()
    ws = browser_ws_url()
    cdp = CDPSession(ws)
    cdp.on_session_event("Target.attachedToTarget", on_attached)
    cdp.on_session_event("Network.requestWillBeSent", on_request)
    cdp.on_session_event("Network.responseReceived", on_response)
    cdp.on_session_event("Network.loadingFinished", on_loading_finished)
    cdp.on_session_event("Target.detachedFromTarget", on_detached)
    cdp.send_command("Target.setAutoAttach", {
        "autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True,
    })
    log("Готово. Теперь отправь ОДНО сообщение в Arena вручную.")
    log("Скрипт пассивный: сам ничего сайту не отправляет.")
    deadline = time.time() + 180.0
    while time.time() < deadline and cdp.is_alive() and not done.wait(0.25):
        pass
    # All background body writers set done only after their atomic record is
    # persisted. Lock once more so no writer can truncate after this point.
    with lock:
        save_records_locked()
    cdp.close()
    log("Диагностика сохранена: %s" % OUT_FILE)


if __name__ == "__main__":
    main()
