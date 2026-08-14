# -*- coding: utf-8 -*-
"""Passive Arena Battle network analyzer.

Run from ``python/`` while the agent browser is open, then send one message
manually in Arena Battle. The analyzer never types, clicks, navigates, or
sends requests. It records every Arena stream POST across page targets and
writes a redacted report to ``временно/arena_battle_report.json``.

Useful fields in the report:
* target transitions (/text -> /c/<id>);
* request/response order and requestId;
* response status, MIME, loading completion and body sizes;
* decoded Arena ``a0``, ``a1`` and ``ad`` frame counts and text lengths.

No cookies, authorization headers, request bodies, or response text are saved.
"""
import base64
import json
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

_HERE = Path(__file__).resolve().parent.parent
for _directory in (_HERE, _HERE / "browser", _HERE / "parsers", _HERE / "server"):
    if _directory.is_dir() and str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))

from browser.browser_manager import setup_browser
from browser.cdp_ws import CDPSession, browser_ws_url


OUT_FILE = _HERE.parent.parent / "временно" / "arena_battle_report.json"
TARGET_MARKER = "/nextjs-api/stream/"
lock = threading.RLock()
records = []
sessions = {}
cdp = None
started = time.time()
capture_done = threading.Event()
capture_state = {"first_body_at": None, "last_activity_at": None}


def clean_url(url):
    parsed = urlsplit(url or "")
    return "%s://%s%s" % (parsed.scheme, parsed.netloc, parsed.path)


def report_event(kind, session_id, data):
    with lock:
        records.append({"ts": round(time.time() - started, 3),
                        "kind": kind, "session_id": session_id, **data})
        save_report_locked()


def save_report_locked():
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"created": started, "events": records}
    temporary = OUT_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUT_FILE)


def stream_summary(raw):
    """Summarize complete Arena newline frames without retaining their text."""
    streams = {}
    done = []
    line_count = 0
    prefixes = {}
    payload_types = {}
    malformed = 0
    for line in (raw or b"").splitlines():
        line_count += 1
        if b":" not in line:
            continue
        prefix, payload = line.split(b":", 1)
        prefix = prefix.decode("ascii", "replace").strip()
        payload = payload.strip()
        prefixes[prefix] = prefixes.get(prefix, 0) + 1
        try:
            decoded = json.loads(payload.decode("utf-8", "replace"))
            type_name = type(decoded).__name__
            payload_types[type_name] = payload_types.get(type_name, 0) + 1
        except (TypeError, ValueError):
            decoded = None
            malformed += 1
        if ((prefix.startswith("a") and prefix[1:].isdigit())
                or prefix == "b0"):
            value = decoded
            if isinstance(value, str):
                stream_name = "a1" if prefix == "b0" else prefix
                item = streams.setdefault(stream_name, {"frames": 0, "chars": 0})
                item["frames"] += 1
                item["chars"] += len(value)
        elif prefix == "ad":
            value = decoded if decoded is not None else {"parse_error": True}
            done.append(value)
    return {"line_count": line_count, "prefixes": prefixes,
            "payload_types": payload_types, "malformed_payloads": malformed,
            "streams": streams, "done": done}


def configure_session(session_id, info):
    url = info.get("url") or ""
    if info.get("type") != "page" or "arena.ai" not in url:
        try:
            cdp.send_command("Runtime.runIfWaitingForDebugger",
                             session_id=session_id, timeout=3.0)
        except Exception:
            pass
        return
    sessions[session_id] = {"url": url, "requests": {}}
    report_event("target", session_id, {"target_id": info.get("targetId"),
                                          "url": clean_url(url)})
    try:
        cdp.send_command("Network.enable", session_id=session_id)
        cdp.send_command("Runtime.runIfWaitingForDebugger", session_id=session_id)
    except Exception as exc:
        report_event("session_error", session_id, {"error": str(exc)[:300]})


def on_attached(params, _parent_session):
    session_id = params.get("sessionId")
    if session_id:
        threading.Thread(target=configure_session,
                         args=(session_id, params.get("targetInfo") or {}),
                         daemon=True).start()


def on_request(params, session_id):
    state = sessions.get(session_id)
    if not state:
        return
    request = params.get("request") or {}
    url = request.get("url") or ""
    if TARGET_MARKER not in url or (request.get("method") or "").upper() != "POST":
        return
    request_id = params.get("requestId")
    state["requests"][request_id] = {"url": clean_url(url), "chunks": 0,
                                     "bytes": 0, "body": bytearray()}
    capture_state["last_activity_at"] = time.time()
    report_event("request", session_id, {"request_id": request_id,
                                          "url": clean_url(url)})


def on_response(params, session_id):
    state = sessions.get(session_id)
    response = params.get("response") or {}
    request_id = params.get("requestId")
    item = (state or {}).get("requests", {}).get(request_id)
    if item is None or TARGET_MARKER not in (response.get("url") or ""):
        return
    item.update({"status": response.get("status"),
                 "mime": response.get("mimeType") or ""})
    capture_state["last_activity_at"] = time.time()
    report_event("response", session_id, {"request_id": request_id,
                                           "status": response.get("status"),
                                           "mime": response.get("mimeType") or ""})
    threading.Thread(target=enable_stream, args=(session_id, request_id), daemon=True).start()


def enable_stream(session_id, request_id):
    try:
        result = cdp.send_command("Network.streamResourceContent",
                                  {"requestId": request_id}, timeout=5.0,
                                  session_id=session_id)
        buffered = result.get("bufferedData") or ""
        if buffered:
            raw = base64.b64decode(buffered)
            item = sessions.get(session_id, {}).get("requests", {}).get(request_id)
            if item is not None:
                item["body"].extend(raw)
    except Exception as exc:
        report_event("stream_error", session_id, {"request_id": request_id,
                                                   "error": str(exc)[:300]})


def on_data(params, session_id):
    item = sessions.get(session_id, {}).get("requests", {}).get(params.get("requestId"))
    data = params.get("data")
    if item is None or not data:
        return
    try:
        raw = base64.b64decode(data)
    except Exception:
        return
    item["chunks"] += 1
    item["bytes"] += len(raw)
    item["body"].extend(raw)
    capture_state["last_activity_at"] = time.time()


def on_loading_finished(params, session_id):
    request_id = params.get("requestId")
    item = sessions.get(session_id, {}).get("requests", {}).get(request_id)
    if item is None:
        return
    # Fast Arena responses often finish before streamResourceContent is
    # enabled. Fetching from this callback would deadlock the CDP reader, so
    # use a worker and prefer the full completed body when available.
    threading.Thread(target=finish_request,
                     args=(session_id, request_id), daemon=True).start()


def finish_request(session_id, request_id):
    item = sessions.get(session_id, {}).get("requests", {}).get(request_id)
    if item is None:
        return
    source = "live_stream"
    raw = bytes(item["body"])
    try:
        result = cdp.send_command("Network.getResponseBody",
                                  {"requestId": request_id}, timeout=8.0,
                                  session_id=session_id)
        body = result.get("body") or ""
        full = (base64.b64decode(body) if result.get("base64Encoded")
                else body.encode("utf-8"))
        if full:
            raw = full
            source = "getResponseBody"
    except Exception as exc:
        report_event("body_error", session_id, {"request_id": request_id,
                                                 "error": str(exc)[:300]})
    report_event("finished", session_id, {"request_id": request_id,
                                          "source": source,
                                          "chunks": item["chunks"],
                                          "bytes": len(raw),
                                          "summary": stream_summary(raw)})
    if raw:
        now = time.time()
        if capture_state["first_body_at"] is None:
            capture_state["first_body_at"] = now
        capture_state["last_activity_at"] = now


def on_detached(params, _parent_session):
    sessions.pop(params.get("sessionId"), None)


def connect():
    global cdp
    cdp = CDPSession(browser_ws_url())
    cdp.on_session_event("Target.attachedToTarget", on_attached)
    cdp.on_session_event("Network.requestWillBeSent", on_request)
    cdp.on_session_event("Network.responseReceived", on_response)
    cdp.on_session_event("Network.dataReceived", on_data)
    cdp.on_session_event("Network.loadingFinished", on_loading_finished)
    cdp.on_session_event("Target.detachedFromTarget", on_detached)
    cdp.send_command("Target.setAutoAttach", {
        "autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True})


def main():
    global started
    setup_browser()
    started = time.time()
    capture_done.clear()
    capture_state["first_body_at"] = None
    capture_state["last_activity_at"] = None
    sessions.clear()
    with lock:
        records.clear()
        if OUT_FILE.exists():
            OUT_FILE.unlink()
    connect()
    print("[arena_battle_analyzer] Готово. Отправь одно сообщение вручную в Arena Battle.")
    print("[arena_battle_analyzer] Жду НОВЫЙ Arena POST до 180 секунд...")
    print("[arena_battle_analyzer] Частичный отчёт обновляется здесь: %s" % OUT_FILE)
    deadline = time.time() + 180.0
    while time.time() < deadline and not capture_done.wait(0.25):
        first_body_at = capture_state["first_body_at"]
        last_activity_at = capture_state["last_activity_at"]
        if (first_body_at is not None and last_activity_at is not None
                and time.time() - last_activity_at >= 10.0):
            capture_done.set()
            break
        if cdp.is_alive():
            continue
        report_event("cdp_reconnect", None, {"reason": "browser CDP session closed"})
        try:
            connect()
            print("[arena_battle_analyzer] CDP переподключён, продолжаю ждать запрос...")
        except Exception as exc:
            print("[arena_battle_analyzer] Переподключение не удалось: %s" % exc)
            time.sleep(1.0)
    with lock:
        save_report_locked()
    try:
        cdp.close()
    except Exception:
        pass
    if capture_done.is_set():
        print("[arena_battle_analyzer] Ответы перехвачены, прошло 10 секунд сетевой тишины. Отчёт готов.")
    else:
        print("[arena_battle_analyzer] Таймаут: новый ответ не был перехвачен.")


if __name__ == "__main__":
    main()
