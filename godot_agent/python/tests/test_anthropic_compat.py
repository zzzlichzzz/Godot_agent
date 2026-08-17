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
import openai_compat as OC0
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
                    "type": "thinking_delta", "thinking": "think a bit"}},
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
            "content": [{"type": "thinking", "thinking": "hmm"},
                        {"type": "text", "text": "pong"}],
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
     {"role": "user", "content": "ping"}], max_tokens=8,
    extra_headers=providers.headers_for("agentrouter"))
check("non-stream text parsed", res["text"] == "pong", res)
check("non-stream thinking block kept as reasoning",
      res["reasoning"] == "hmm", res)
check("non-stream usage normalized",
      res["usage"] == {"prompt_tokens": 7, "completion_tokens": 2}, res["usage"])
req = seen[-1]
headers_lower = {k.lower(): v for k, v in req["headers"].items()}
check("Anthropic endpoint used", req["path"] == "/v1/messages", req["path"])
check("x-api-key sent", headers_lower.get("x-api-key") == key)
check("Bearer sent", headers_lower.get("authorization") == "Bearer " + key)
check("Anthropic version sent", headers_lower.get("anthropic-version") == A.ANTHROPIC_VERSION)
# ПЛАГИН НЕ ПРИТВОРЯЕТСЯ ЧУЖОЙ ПРОГРАММОЙ. AgentRouter пускает только клиентов
# из своего списка и узнаёт их по User-Agent, но выдавать себя за opencode или
# claude-cli значит подставлять под блокировку аккаунт пользователя. Поэтому в
# запрос уходит настоящее имя плагина, а сам провайдер выключен (см. ниже).
check("plugin sends its own User-Agent",
      headers_lower.get("user-agent") == OC0.USER_AGENT,
      headers_lower.get("user-agent"))
check("no third-party client name in User-Agent",
      not any(w in str(headers_lower.get("user-agent") or "").lower()
              for w in ("opencode", "claude-cli", "cline", "codex")),
      headers_lower.get("user-agent"))
check("only one User-Agent header",
      sum(1 for k in req["headers"] if k.lower() == "user-agent") == 1,
      list(req["headers"]))
check("system message moved to system field",
      req["body"].get("system") == "system rules"
      and req["body"]["messages"] == [{"role": "user", "content": "ping"}], req["body"])

deltas = []
streamed = A.stream_chat(
    base, key, "claude-opus-5", [{"role": "user", "content": "hello"}],
    max_tokens=16, on_delta=lambda text, reasoning: deltas.append((text, reasoning)))
check("Anthropic SSE text assembled", streamed["text"] == "hello world", streamed)
check("Anthropic SSE thinking collected",
      streamed["reasoning"] == "think a bit", streamed["reasoning"])
check("Anthropic SSE deltas forwarded",
      deltas == [("think a bit", True), ("hello ", False), ("world", False)], deltas)
check("Anthropic SSE finish reason parsed", streamed["finish_reason"] == "end_turn")
check("Anthropic SSE usage merged",
      streamed["usage"] == {"prompt_tokens": 12, "completion_tokens": 3}, streamed["usage"])

check("AgentRouter GPT selects OpenAI transport",
      providers.transport_for("agentrouter", "gpt-5.6-sol") == "openai")
check("AgentRouter Claude selects Anthropic transport",
      providers.transport_for("agentrouter", "claude-opus-5") == "anthropic")
check("other providers remain OpenAI",
      providers.transport_for("openrouter", "anything") == "openai")

check("providers add no User-Agent of their own",
      not any("user-agent" in k.lower()
              for pid in providers.provider_ids()
              for k in providers.headers_for(pid)),
      {pid: providers.headers_for(pid) for pid in providers.provider_ids()})

# Посредник ждёт свой апстрим: до первого байта у Claude замеряли до 68 с.
# Транспорт готов заранее — чтобы включение свелось к снятию одного флага.
check("AgentRouter gets a longer connect timeout",
      providers.connect_timeout_for("agentrouter") > OC0.DEFAULT_CONNECT_TIMEOUT,
      providers.connect_timeout_for("agentrouter"))
check("other providers keep the default timeout",
      providers.connect_timeout_for("openrouter") == OC0.DEFAULT_CONNECT_TIMEOUT,
      providers.connect_timeout_for("openrouter"))
check("unknown provider keeps the default timeout",
      providers.connect_timeout_for("nope") == OC0.DEFAULT_CONNECT_TIMEOUT)
# non-stream к Claude шлюз обрывает своим 504 через 120 с.
check("AgentRouter connection test uses streaming",
      providers.test_with_stream("agentrouter") is True)
check("other providers test without streaming",
      providers.test_with_stream("openrouter") is False)

# --- Провайдер объявлен, но обращаться к нему нельзя ---
check("AgentRouter is marked unavailable",
      providers.unavailable_reason("agentrouter") != "")
check("other providers stay available",
      providers.unavailable_reason("openrouter") == ""
      and providers.unavailable_reason("custom") == "")
check("unknown provider is not reported as unavailable",
      providers.unavailable_reason("nope") == "")
# Причина недоступности должна вытеснять «не задан ключ»: ключ здесь не поможет.
_ok, _why = providers.readiness("agentrouter")
check("unavailable provider is never ready", _ok is False, (_ok, _why))
check("readiness explains the real cause, not a missing key",
      _why == providers.unavailable_reason("agentrouter"), _why)
# Запись остаётся видимой в настройках — с объяснением, а не молча исчезает.
_listed = {p["id"]: p for p in providers.list_providers()}
check("AgentRouter stays visible in settings", "agentrouter" in _listed)
check("panel is told the provider is unavailable",
      _listed["agentrouter"]["unavailable"] != "", _listed["agentrouter"])
check("panel is told the reason",
      _listed["agentrouter"]["not_ready_reason"] != ""
      and _listed["agentrouter"]["ready"] is False, _listed["agentrouter"])
check("note mentions the whitelist request",
      u"разрешение" in _listed["agentrouter"]["note_ru"],
      _listed["agentrouter"]["note_ru"])
check("available providers report no reason",
      _listed["openrouter"]["unavailable"] == "", _listed["openrouter"])

# Ошибку «программа не в списке» нельзя выдавать за неверный ключ.
import api_backend as AB  # noqa: E402

_txt, _st, _ra = AB.describe_api_error(
    OC0.AuthError(u"unauthorized client detected, contact support", status=401),
    u"AgentRouter", u"claude-opus-5")
check("client rejection is not blamed on the key",
      u"Клиент не в списке" in _txt and u"отклонил ключ" not in _txt, _txt)
check("client rejection does not suggest faking the client name",
      not any(w in _txt.lower() for w in ("opencode", "claude-cli", "user-agent")),
      _txt)
_txt2, _st2, _ra2 = AB.describe_api_error(
    OC0.AuthError(u"invalid api key", status=401), u"AgentRouter")
check("real key error still reported as key error",
      u"отклонил ключ" in _txt2, _txt2)

srv.shutdown()
print("ИТОГО: %d/%d" % (sum(1 for x in results if x), len(results)))
raise SystemExit(0 if all(results) else 1)
