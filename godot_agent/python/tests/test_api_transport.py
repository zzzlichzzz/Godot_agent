# -*- coding: utf-8 -*-
import os as _os0, sys as _sys0  # v104-restructure: tests/ -> python/
_sys0.path.insert(0, _os0.path.abspath(_os0.path.join(_os0.path.dirname(_os0.path.abspath(__file__)), _os0.pardir)))
import _bootstrap  # noqa: E402,F401
"""Тесты транспорта API (openai_compat): поток SSE, отмена, ошибки, прокси.

Тест ОФЛАЙНОВЫЙ: поднимает настоящий HTTP-сервер на 127.0.0.1 и говорит с ним
по-настоящему. Так проверяется именно то, что ломается в живой работе —
разрезанные события, keep-alive-комментарии, обрыв, отмена посреди потока, —
а не поведение подставного объекта. Сеть и ключи не нужны.
"""
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import api_keys
import openai_compat as oc

results = []


def check(name, cond):
    print("%s -> %s" % (name, "OK" if cond else "FAIL"))
    results.append(bool(cond))


# ---------------------------------------------------------------------------
# Локальный сервер-заглушка
# ---------------------------------------------------------------------------

LAST = {"headers": {}, "body": None, "path": ""}


def sse(obj):
    return b"data: " + json.dumps(obj).encode("utf-8") + b"\n\n"


def delta(content=None, reasoning=None, finish=None, usage=None, model="m/test"):
    d = {}
    if content is not None:
        d["content"] = content
    if reasoning is not None:
        d["reasoning"] = reasoning
    obj = {"model": model, "choices": [{"delta": d, "finish_reason": finish}]}
    if usage is not None:
        obj["usage"] = usage
    return obj


OK_STREAM = (
    b": OPENROUTER PROCESSING\n\n"          # keep-alive, не должен попасть в текст
    + sse(delta(reasoning=u"думаю..."))
    + sse(delta(content=u"Привет"))
    + b"\n"                                  # пустая строка между событиями
    + sse(delta(content=u", мир"))
    + sse(delta(finish="stop", usage={"prompt_tokens": 11, "completion_tokens": 4}))
    + b"data: [DONE]\n\n"
)

ERRORS = {
    "/err401": (401, {"error": {"message": "Invalid API key provided"}}),
    "/err402": (402, {"error": {"message": "Insufficient credits"}}),
    "/err404": (404, {"error": {"message": "No endpoint found for model x/y"}}),
    "/err429": (429, {"error": {"message": "Rate limit exceeded"}}),
    "/err429d": (429, {"error": {"message": "Rate limit exceeded: free-models-per-day"}}),
    "/err400ctx": (400, {"error": {"message": "This model's maximum context length is 8192 tokens"}}),
    "/err500": (502, {"error": {"message": "Bad gateway"}}),
    "/errhtml": (503, None),   # не-JSON тело от балансировщика
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _remember(self):
        LAST["headers"] = {k.lower(): v for k, v in self.headers.items()}
        LAST["path"] = self.path
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            LAST["body"] = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            LAST["body"] = raw

    def _send_stream(self, chunks, delay=0.0, slice_size=0):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        data = b"".join(chunks)
        if slice_size:
            pieces = [data[i:i + slice_size] for i in range(0, len(data), slice_size)]
        else:
            pieces = chunks
        for p in pieces:
            try:
                self.wfile.write(p)
                self.wfile.flush()
            except Exception:
                return
            if delay:
                time.sleep(delay)

    def _send_json(self, status, obj):
        if obj is None:
            body = b"<html>503 Service Unavailable</html>"
        else:
            body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if status == 429:
            self.send_header("Retry-After", "42")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._remember()
        if self.path.endswith("/models"):
            self._send_json(200, {"data": [
                {"id": "a/paid", "pricing": {"prompt": "0.001", "completion": "0.002"}},
                {"id": "b/gift:free", "pricing": {"prompt": "0", "completion": "0"}},
            ]})
            return
        self._send_json(404, {"error": {"message": "no such path"}})

    def do_POST(self):
        self._remember()
        p = self.path
        # Длинные префиксы первыми: "/err429d" начинается с "/err429", и без
        # сортировки суточный лимит обслуживался бы минутным.
        for prefix in sorted(ERRORS, key=len, reverse=True):
            if p.startswith(prefix):
                status, obj = ERRORS[prefix]
                self._send_json(status, obj)
                return
        if p.startswith("/ok"):
            self._send_stream([OK_STREAM])
        elif p.startswith("/split"):
            self._send_stream([OK_STREAM], slice_size=7)
        elif p.startswith("/slow"):
            self._send_stream([sse(delta(content="x%d" % i)) for i in range(200)],
                              delay=0.05)
        elif p.startswith("/miderr"):
            self._send_stream([sse(delta(content=u"начало")),
                               sse({"error": {"message": "upstream died",
                                              "code": 502}})])
        elif p.startswith("/cut"):
            # Заголовки отдали, поток начали и молча оборвали соединение.
            self._send_stream([sse(delta(content=u"часть"))])
        elif p.startswith("/plain"):
            self._send_json(200, {"model": "m/test", "choices": [
                {"message": {"content": u"пинг-ответ"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2}})
        else:
            self._send_json(404, {"error": {"message": "no such path"}})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % PORT

MSG = [{"role": "user", "content": "hi"}]


def call(path, **kw):
    return oc.stream_chat(BASE + path, "sk-test-0123456789abcdef", "m/test", MSG, **kw)


# ---------------------------------------------------------------------------
# 1) Нормальный поток
# ---------------------------------------------------------------------------
seen = []
r = call("/ok", on_delta=lambda t, is_r: seen.append((t, is_r)),
         extra_headers={"X-Title": "Godot Agent"}, max_tokens=1234)
check(u"текст собран из кусков", r["text"] == u"Привет, мир")
check(u"размышления отделены от ответа", r["reasoning"] == u"думаю...")
check(u"keep-alive-комментарий не попал в текст", u"PROCESSING" not in r["text"])
check("finish_reason прочитан", r["finish_reason"] == "stop")
check("usage прочитан", (r["usage"] or {}).get("prompt_tokens") == 11)
check("модель из ответа", r["model"] == "m/test")
check("on_delta получил только куски ответа",
      [t for t, is_r in seen if not is_r] == [u"Привет", u", мир"])
check("on_delta пометил размышление флагом",
      [t for t, is_r in seen if is_r] == [u"думаю..."])
check("elapsed заполнен", r["elapsed"] >= 0)

# ---------------------------------------------------------------------------
# 2) Заголовки и тело запроса
# ---------------------------------------------------------------------------
check("ключ ушёл в Authorization: Bearer",
      LAST["headers"].get("authorization") == "Bearer sk-test-0123456789abcdef")
check("свой User-Agent, а не Python-urllib",
      LAST["headers"].get("user-agent", "").startswith("GodotAgent/"))
check("Accept для потока", LAST["headers"].get("accept") == "text/event-stream")
check("доп. заголовок провайдера дошёл",
      LAST["headers"].get("x-title") == "Godot Agent")
check("stream=true в теле", (LAST["body"] or {}).get("stream") is True)
check("max_tokens дошёл", (LAST["body"] or {}).get("max_tokens") == 1234)
check("пустые необязательные поля НЕ отправлены",
      "temperature" not in (LAST["body"] or {}) and "stop" not in (LAST["body"] or {}))

body = oc.build_body("m", MSG, temperature=0.2, stop=["A"], stream=False)
check("build_body без stream не добавляет stream", "stream" not in body)
check("build_body добавляет заданные поля",
      body["temperature"] == 0.2 and body["stop"] == ["A"])

# ---------------------------------------------------------------------------
# 3) События, разрезанные по границе TCP-пакета
# ---------------------------------------------------------------------------
r2 = call("/split")
check(u"поток, разрезанный по 7 байт, собран верно", r2["text"] == u"Привет, мир")
check("finish_reason при разрезанном потоке", r2["finish_reason"] == "stop")

lines, tail = oc.split_sse_lines(b"data: {}\n\ndata: {\"a\"")
check("хвост без перевода строки сохранён", lines == ["data: {}", ""] and tail == b"data: {\"a\"")
check("комментарий распознан", oc.parse_sse_line(": keep") == ("skip", None))
check("[DONE] распознан", oc.parse_sse_line("data: [DONE]") == ("done", None))
check("event: игнорируется", oc.parse_sse_line("event: message") == ("skip", None))

# ---------------------------------------------------------------------------
# 4) Отмена посреди потока
# ---------------------------------------------------------------------------
state = {"n": 0}


def cancel_after_two():
    return state["n"] >= 2


def count(t, is_r):
    state["n"] += 1


t0 = time.time()
try:
    call("/slow", cancel_cb=cancel_after_two, on_delta=count)
    check(u"отмена посреди потока бросает Cancelled", False)
except oc.Cancelled:
    check(u"отмена посреди потока бросает Cancelled", True)
check(u"отмена срабатывает быстро, а не по таймауту", time.time() - t0 < 5.0)

# ---------------------------------------------------------------------------
# 5) Ошибка внутри потока с кодом 200
# ---------------------------------------------------------------------------
try:
    call("/miderr")
    check(u"ошибка внутри потока не проглатывается", False)
except oc.ServerError as e:
    check(u"ошибка внутри потока -> ServerError", "upstream died" in str(e))
except oc.ApiError:
    check(u"ошибка внутри потока -> ServerError", False)

# ---------------------------------------------------------------------------
# 6) Классификация HTTP-ошибок
# ---------------------------------------------------------------------------
cases = [
    ("/err401", oc.AuthError, u"401 -> AuthError (повтор бессмыслен)"),
    ("/err402", oc.PaymentRequiredError, u"402 -> PaymentRequiredError"),
    ("/err404", oc.ModelNotFoundError, u"404 -> ModelNotFoundError"),
    ("/err400ctx", oc.ContextTooLongError, u"400 про контекст -> ContextTooLongError"),
    ("/err500", oc.ServerError, u"502 -> ServerError (повтор имеет смысл)"),
    ("/errhtml", oc.ServerError, u"503 с HTML-телом -> ServerError"),
]
for path, exc_type, name in cases:
    try:
        call(path)
        check(name, False)
    except exc_type:
        check(name, True)
    except Exception as e:
        print("   получено вместо %s: %r" % (exc_type.__name__, e))
        check(name, False)

try:
    call("/err429")
    check("429 -> RateLimitError", False)
except oc.RateLimitError as e:
    check("429 -> RateLimitError", True)
    check("Retry-After прочитан (42 с)", e.retry_after == 42)
    check("минутный лимит: daily=False", e.daily is False)

try:
    call("/err429d")
    check("суточный лимит помечен daily=True", False)
except oc.RateLimitError as e:
    check("суточный лимит помечен daily=True", e.daily is True)

check("сообщение провайдера извлечено из JSON",
      oc._extract_provider_message('{"error": {"message": "boom"}}') == "boom")
check("не-JSON тело отдаётся как есть",
      "503" in oc._extract_provider_message("<html>503</html>"))
check("Retry-After числом", oc._parse_retry_after("15") == 15)
check("Retry-After мусором -> None", oc._parse_retry_after("позже") is None)

# ---------------------------------------------------------------------------
# 7) Обрыв соединения посреди потока
# ---------------------------------------------------------------------------
r3 = call("/cut")
check(u"оборванный поток отдаёт то, что успело прийти", r3["text"] == u"часть")
check(u"у оборванного потока нет finish_reason", r3["finish_reason"] is None)

# ---------------------------------------------------------------------------
# 8) Непотоковый запрос и список моделей
# ---------------------------------------------------------------------------
r4 = oc.complete_chat(BASE + "/plain", "sk-test", "m/test", MSG, max_tokens=5)
check(u"complete_chat читает обычный ответ", r4["text"] == u"пинг-ответ")
check("complete_chat: stream не отправлен",
      "stream" not in (LAST["body"] or {}))
check("complete_chat: usage прочитан", (r4["usage"] or {}).get("completion_tokens") == 2)

raw_models = oc.fetch_models(BASE + "/models", "sk-test")
import providers as P
check(u"список моделей получен", isinstance(raw_models, dict))
check(u"бесплатные модели отфильтрованы",
      P.parse_models_response(raw_models, free_only=True) == ["b/gift:free"])

# ---------------------------------------------------------------------------
# 9) Прокси: локальные адреса идут напрямую
# ---------------------------------------------------------------------------
check("127.0.0.1 — локальный", oc.is_local_host("127.0.0.1"))
check("localhost — локальный", oc.is_local_host("localhost"))
check("::1 в скобках — локальный", oc.is_local_host("[::1]"))
check("127.5.5.5 — локальный (вся сеть 127/8)", oc.is_local_host("127.5.5.5"))
check("внешний хост — не локальный", not oc.is_local_host("openrouter.ai"))
check("пустой хост — не локальный", not oc.is_local_host(""))

# Заведомо нерабочий прокси: если бы локальный запрос пошёл через него,
# вызов упал бы. Значит проверяем именно обход прокси для localhost.
r5 = call("/ok", proxy="http://127.0.0.1:1/")
check(u"локальный запрос игнорирует прокси", r5["text"] == u"Привет, мир")

# А внешний адрес через тот же битый прокси обязан честно упасть TransportError.
try:
    oc.stream_chat("http://example.invalid/v1", "k", "m", MSG,
                   proxy="http://127.0.0.1:1/", connect_timeout=5)
    check(u"внешний адрес через битый прокси -> TransportError", False)
except oc.TransportError:
    check(u"внешний адрес через битый прокси -> TransportError", True)
except oc.ApiError as e:
    print("   получено: %r" % (e,))
    check(u"внешний адрес через битый прокси -> TransportError", False)

# ---------------------------------------------------------------------------
# 10) Тишина в потоке считается обрывом
# ---------------------------------------------------------------------------
quiet = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
quiet.bind(("127.0.0.1", 0))
quiet.listen(1)
quiet_port = quiet.getsockname()[1]


def _accept_and_hang():
    try:
        conn, _ = quiet.accept()
        conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: text/event-stream\r\n\r\n")
        time.sleep(10)   # молчим — клиент должен сдаться сам
        conn.close()
    except Exception:
        pass


threading.Thread(target=_accept_and_hang, daemon=True).start()
try:
    oc.stream_chat("http://127.0.0.1:%d/v1" % quiet_port, "k", "m", MSG,
                   silence_timeout=1.5)
    check(u"молчащий поток -> TransportError", False)
except oc.TransportError as e:
    check(u"молчащий поток -> TransportError", u"молчит" in str(e))
except oc.ApiError as e:
    print("   получено: %r" % (e,))
    check(u"молчащий поток -> TransportError", False)

# ---------------------------------------------------------------------------
# 11) Ключ не утекает в текст ошибки
# ---------------------------------------------------------------------------
import os
os.environ["GODOT_AGENT_CONFIG_DIR"] = os.path.join(
    os.environ.get("TEMP") or "/tmp", "godot_agent_test_cfg")
api_keys.set_key("openrouter", "sk-or-v1-SECRETSECRETSECRET1234")
leaked = u"Ошибка: ключ sk-or-v1-SECRETSECRETSECRET1234 отклонён"
check(u"redact убирает ключ из текста ошибки",
      "SECRETSECRET" not in api_keys.redact(leaked))
check(u"redact оставляет узнаваемую маску",
      "sk-or-" in api_keys.redact(leaked) and "1234" in api_keys.redact(leaked))
api_keys.delete_key("openrouter")

srv.shutdown()
n_ok = sum(1 for r in results if r)
print("ИТОГО: %d/%d" % (n_ok, len(results)))
sys.exit(0 if n_ok == len(results) else 1)
