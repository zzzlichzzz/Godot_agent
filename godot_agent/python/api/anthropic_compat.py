# -*- coding: utf-8 -*-
"""Минимальный Anthropic Messages API поверх общего urllib-транспорта.

Нужен AgentRouter-моделям Claude: тот же ключ и base URL, но маршрут
POST /messages и формат SSE отличаются от OpenAI /chat/completions. Сетевое
соединение, прокси, TLS, отмена и типы ошибок переиспользуются из
openai_compat, поэтому оба протокола ведут себя для панели одинаково.
"""
import json
import queue
import ssl
import threading
import time

import openai_compat as oc


ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 8192

# ApiBackend ловит эти исключения через openai_compat.
ApiError = oc.ApiError
Cancelled = oc.Cancelled


def _request_headers(api_key, extra_headers=None):
    headers = dict(extra_headers or {})
    headers["anthropic-version"] = ANTHROPIC_VERSION
    if api_key:
        # Официальный Anthropic SDK передаёт ключ в x-api-key, а шлюзы вроде
        # AgentRouter — в Authorization: Bearer. Проверено, что AgentRouter
        # принимает любой из двух, поэтому отправляем оба: так один и тот же
        # транспорт годится и для настоящего api.anthropic.com, и для шлюза.
        # Authorization добавит _open, здесь только x-api-key.
        headers["x-api-key"] = api_key
    return headers


def _body(model, messages, max_tokens=None, temperature=None, stream=False):
    system_parts = []
    converted = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        content = item.get("content")
        if isinstance(content, list):
            text = "\n".join(str(p.get("text") or "") for p in content
                             if isinstance(p, dict) and p.get("type") == "text")
        else:
            text = str(content or "")
        if role == "system":
            if text:
                system_parts.append(text)
            continue
        converted.append({"role": "assistant" if role == "assistant" else "user",
                          "content": text})
    payload = {
        "model": model,
        "messages": converted,
        "max_tokens": int(max_tokens or DEFAULT_MAX_TOKENS),
        "stream": bool(stream),
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if temperature is not None:
        payload["temperature"] = float(temperature)
    return payload


def _usage(raw):
    if not isinstance(raw, dict):
        return None
    pin = raw.get("input_tokens")
    pout = raw.get("output_tokens")
    if pin is None and pout is None:
        return None
    return {"prompt_tokens": int(pin or 0),
            "completion_tokens": int(pout or 0)}


def _content_parts(obj):
    """Ответ, разложенный на текст и «мысли».

    ПОЧЕМУ ТЕКСТ НЕ ЕДИНСТВЕННЫЙ ВИД БЛОКА. У AgentRouter Claude отвечает с
    включённым extended thinking, и тогда в content приходят блоки
    type="thinking" — при коротком max_tokens ответ может состоять ТОЛЬКО из
    них (stop_reason="max_tokens"). Если считать текстом лишь type="text",
    такой ответ выглядел бы пустым, и панель сообщила бы о пустом ответе
    вместо честного «модель не договорила».
    """
    text = []
    reasoning = []
    for block in (obj.get("content") or []) if isinstance(obj, dict) else []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            text.append(str(block.get("text") or ""))
        elif kind == "thinking":
            reasoning.append(str(block.get("thinking") or ""))
    return "".join(text), "".join(reasoning)


def complete_chat(base_url, api_key, model, messages,
                  max_tokens=None, temperature=None, extra_headers=None,
                  proxy=None, connect_timeout=oc.DEFAULT_CONNECT_TIMEOUT,
                  extra_body=None):
    payload = _body(model, messages, max_tokens, temperature, stream=False)
    if isinstance(extra_body, dict):
        payload.update(extra_body)
    started = time.time()
    resp = oc._open(base_url.rstrip("/") + "/messages", api_key,
                    _request_headers(api_key, extra_headers), proxy, payload,
                    "application/json", connect_timeout)
    try:
        raw = resp.read().decode("utf-8", "replace")
    finally:
        oc._force_close(resp)
    try:
        obj = json.loads(raw)
    except Exception:
        raise oc.TransportError(u"Ответ Anthropic не является JSON: %s" % raw[:200])
    err = oc.error_in_event(obj)
    if err is not None:
        raise err
    text, reasoning = _content_parts(obj)
    return {"text": text, "reasoning": reasoning,
            "finish_reason": obj.get("stop_reason"),
            "usage": _usage(obj.get("usage")),
            "model": obj.get("model") or model,
            "elapsed": time.time() - started}


def stream_chat(base_url, api_key, model, messages,
                max_tokens=None, temperature=None, extra_headers=None,
                proxy=None, connect_timeout=oc.DEFAULT_CONNECT_TIMEOUT,
                silence_timeout=oc.DEFAULT_SILENCE_TIMEOUT,
                cancel_cb=None, on_delta=None, stop=None, extra_body=None):
    payload = _body(model, messages, max_tokens, temperature, stream=True)
    if stop:
        payload["stop_sequences"] = list(stop) if isinstance(stop, (list, tuple)) else [str(stop)]
    if isinstance(extra_body, dict):
        payload.update(extra_body)
    started = time.time()
    resp = oc._open(base_url.rstrip("/") + "/messages", api_key,
                    _request_headers(api_key, extra_headers), proxy, payload,
                    "text/event-stream", connect_timeout)
    oc._set_socket_timeout(resp, silence_timeout + 30.0)

    text_parts = []
    reasoning_parts = []
    finish_reason = None
    usage = None
    response_model = ""
    events = 0
    buf = b""
    last_data = time.time()
    done = False
    q = queue.Queue()
    stop_event = threading.Event()
    oc._spawn_reader(resp, q, stop_event)
    try:
        while not done:
            if cancel_cb is not None and cancel_cb():
                raise oc.Cancelled()
            try:
                item = q.get(timeout=oc._POLL_INTERVAL)
            except queue.Empty:
                if time.time() - last_data > silence_timeout:
                    raise oc.TransportError(
                        u"Поток Anthropic молчит %.0f с — соединение считаю оборванным."
                        % silence_timeout)
                continue
            if item is None:
                break
            if isinstance(item, ssl.SSLError):
                raise oc.TransportError(u"Обрыв TLS при чтении Anthropic: %s" % item)
            if isinstance(item, Exception):
                raise oc.TransportError(u"Обрыв соединения Anthropic: %s" % item)
            last_data = time.time()
            buf += item
            lines, buf = oc.split_sse_lines(buf)
            for line in lines:
                kind, payload_str = oc.parse_sse_line(line)
                if kind == "skip":
                    continue
                if kind == "done":
                    done = True
                    break
                try:
                    obj = json.loads(payload_str)
                except Exception:
                    continue
                err = oc.error_in_event(obj)
                if err is not None:
                    raise err
                events += 1
                event_type = obj.get("type")
                if event_type == "message_start":
                    msg = obj.get("message") or {}
                    response_model = str(msg.get("model") or "")
                    usage = _usage(msg.get("usage")) or usage
                elif event_type == "content_block_delta":
                    delta = obj.get("delta") or {}
                    dtype = delta.get("type")
                    if dtype == "text_delta":
                        text = str(delta.get("text") or "")
                        if text:
                            text_parts.append(text)
                            if on_delta is not None:
                                on_delta(text, False)
                    elif dtype == "thinking_delta":
                        # Мысли идут отдельным потоком — панель показывает их
                        # серым и не путает с ответом.
                        think = str(delta.get("thinking") or "")
                        if think:
                            reasoning_parts.append(think)
                            if on_delta is not None:
                                on_delta(think, True)
                elif event_type == "message_delta":
                    delta = obj.get("delta") or {}
                    finish_reason = delta.get("stop_reason") or finish_reason
                    later = _usage(obj.get("usage"))
                    if later:
                        if usage:
                            later["prompt_tokens"] = usage.get("prompt_tokens", 0)
                        usage = later
                elif event_type == "message_stop":
                    done = True
                    break
    finally:
        stop_event.set()
        oc._force_close(resp)
    return {"text": "".join(text_parts), "reasoning": "".join(reasoning_parts),
            "finish_reason": finish_reason, "usage": usage,
            "model": response_model or model, "events": events,
            "elapsed": time.time() - started}
