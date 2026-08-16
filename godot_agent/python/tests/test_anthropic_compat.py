# -*- coding: utf-8 -*-
import json
import os as _os0
import sys as _sys0
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(
    _os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
import anthropic_compat as A
import providers


results = []
seen = []


def check(name, cond, detail=None):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    if not cond and detail is not None:
        print("     %r" % (detail,))
    results.append(bool(cond))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode("utf-8"))
        seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
        if body.get("stream"):
            events = [
                {"type": "message_start", "message": {
                    "model": "claude-opus-5", "usage": {"input_tokens": 12}}},
                {"type": "content_block_delta", "delta": {
                    "type": "text_delta", "text": "hello "}},
                {"type": "content_block_delta", "delta": {
                    "type": "text_delta", "text": "world"}},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
                 "usage": {"output_tokens": 3}},
                {"type": "message_stop"},
            ]
            raw = "".join("data: %s\n\n" % json.dumps(e) for e in events).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            return
        raw = json.dumps({
            "type": "message", "model": "claude-opus-5",
            "content": [{"type": "text", "text": "pong"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 7, "output_tokens": 2},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d/v1" % srv.server_address[1]
key = "agentrouter-test-key-not-secret"

res = A.complete_chat(
    base, key, "claude-opus-5",
    [{"role": "system", "content": "system rules"},
     {"role": "user", "content": "ping"}], max_tokens=8)
check("non-stream text parsed", res["text"] == "pong", res)
check("non-stream usage normalized",
      res["usage"] == {"prompt_tokens": 7, "completion_tokens": 2}, res["usage"])
req = seen[-1]
headers_lower = {k.lower(): v for k, v in req["headers"].items()}
check("Anthropic endpoint used", req["path"] == "/v1/messages", req["path"])
check("x-api-key sent", headers_lower.get("x-api-key") == key)
check("Bearer sent", headers_lower.get("authorization") == "Bearer " + key)
check("Anthropic version sent", headers_lower.get("anthropic-version") == A.ANTHROPIC_VERSION)
check("system message moved to system field",
      req["body"].get("system") == "system rules"
      and req["body"]["messages"] == [{"role": "user", "content": "ping"}], req["body"])

deltas = []
streamed = A.stream_chat(
    base, key, "claude-opus-5", [{"role": "user", "content": "hello"}],
    max_tokens=16, on_delta=lambda text, reasoning: deltas.append((text, reasoning)))
check("Anthropic SSE text assembled", streamed["text"] == "hello world", streamed)
check("Anthropic SSE deltas forwarded",
      deltas == [("hello ", False), ("world", False)], deltas)
check("Anthropic SSE finish reason parsed", streamed["finish_reason"] == "end_turn")
check("Anthropic SSE usage merged",
      streamed["usage"] == {"prompt_tokens": 12, "completion_tokens": 3}, streamed["usage"])

check("AgentRouter GPT selects OpenAI transport",
      providers.transport_for("agentrouter", "gpt-5.6-sol") == "openai")
check("AgentRouter Claude selects Anthropic transport",
      providers.transport_for("agentrouter", "claude-opus-5") == "anthropic")
check("other providers remain OpenAI",
      providers.transport_for("openrouter", "anything") == "openai")

srv.shutdown()
print("ИТОГО: %d/%d" % (sum(1 for x in results if x), len(results)))
raise SystemExit(0 if all(results) else 1)
