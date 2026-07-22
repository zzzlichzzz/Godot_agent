# -*- coding: utf-8 -*-
"""CDP (Chrome DevTools Protocol) minimal client, stdlib only.

Selenium's driver.execute_cdp_cmd only does request/response CDP commands,
it cannot receive push events (Network.responseReceived,
Network.loadingFinished, etc). kimi.com answers POST .../ChatService/Chat
with one HTTP response using the Connect-RPC wire format
(content-type: application/connect+json) - a stream of JSON events framed
as: 1 flags byte + 4 big-endian length bytes + JSON payload, repeated.
To receive this stream we need a raw WebSocket connection to the browser's
CDP debug port, subscribed to Network.* events - which is what this module
provides.

Schema reverse-engineered from two real www.kimi.com HAR captures taken on
2026-07-22 (see README_CHANGES.txt, v87.1).
"""
import base64
import json
import os
import socket
import struct
import threading
import urllib.request
from urllib.parse import urlsplit


class WSError(Exception):
    pass


def _ws_handshake(sock, host, path):
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    req = (
        "GET " + path + " HTTP/1.1\r\n"
        "Host: " + host + "\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: " + key + "\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode("ascii")
    sock.sendall(req)
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            raise WSError("Connection closed during WebSocket handshake.")
        resp += chunk
    header, _, rest = resp.partition(b"\r\n\r\n")
    status_line = header.split(b"\r\n", 1)[0]
    if b"101" not in status_line:
        raise WSError("Unexpected WebSocket handshake response: %r" % status_line[:200])
    return rest


def _ws_mask(data):
    mask_key = os.urandom(4)
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ mask_key[i % 4]
    return mask_key, bytes(out)


class MiniWebSocket:
    """Minimal client WebSocket with no external dependencies."""

    def __init__(self, url, timeout=10.0):
        parts = urlsplit(url)
        if parts.scheme not in ("ws", "wss"):
            raise WSError("Expected a ws:// address, got: %s" % url)
        host = parts.hostname
        port = parts.port or (443 if parts.scheme == "wss" else 80)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        self._sock = socket.create_connection((host, port), timeout=timeout)
        if parts.scheme == "wss":
            import ssl
            self._sock = ssl.create_default_context().wrap_socket(self._sock, server_hostname=host)
        leftover = _ws_handshake(self._sock, "%s:%s" % (host, port), path)
        self._buf = bytearray(leftover)
        self._closed = False
        self._send_lock = threading.Lock()

    def _recv_some(self):
        chunk = self._sock.recv(65536)
        if not chunk:
            raise WSError("WebSocket connection closed by the remote side.")
        self._buf.extend(chunk)

    def _read_exact(self, n):
        while len(self._buf) < n:
            self._recv_some()
        data = bytes(self._buf[:n])
        del self._buf[:n]
        return data

    def recv_message(self):
        """Returns one assembled message (fin=1, handles continuation
        frames) as bytes, or None on close."""
        fragments = []
        while True:
            hdr = self._read_exact(2)
            b0, b1 = hdr[0], hdr[1]
            fin = bool(b0 & 0x80)
            op = b0 & 0x0F
            masked = bool(b1 & 0x80)
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]
            mask_key = self._read_exact(4) if masked else None
            payload = self._read_exact(length)
            if mask_key:
                payload = bytes(payload[i] ^ mask_key[i % 4] for i in range(len(payload)))
            if op == 0x9:
                self._send_frame(0xA, payload)
                continue
            if op == 0xA:
                continue
            if op == 0x8:
                self._closed = True
                return None
            fragments.append(payload)
            if fin:
                break
        return b"".join(fragments)

    def _send_frame(self, opcode, payload):
        mask_key, masked_payload = _ws_mask(payload)
        length = len(payload)
        b0 = 0x80 | opcode
        if length < 126:
            hdr = bytes([b0, 0x80 | length])
        elif length < 65536:
            hdr = bytes([b0, 0x80 | 126]) + struct.pack(">H", length)
        else:
            hdr = bytes([b0, 0x80 | 127]) + struct.pack(">Q", length)
        with self._send_lock:
            self._sock.sendall(hdr + mask_key + masked_payload)

    def send_text(self, text):
        self._send_frame(0x1, text.encode("utf-8"))

    def close(self):
        if self._closed:
            return
        try:
            self._send_frame(0x8, b"")
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass
        self._closed = True


class CDPSession:
    def __init__(self, ws_url, timeout=10.0):
        self._ws = MiniWebSocket(ws_url, timeout=timeout)
        self._next_id = 1
        self._lock = threading.Lock()
        self._pending = {}
        self._event_handlers = {}
        self._stop = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def on_event(self, method, callback):
        self._event_handlers.setdefault(method, []).append(callback)

    def _read_loop(self):
        while not self._stop:
            try:
                raw = self._ws.recv_message()
            except Exception:
                break
            if raw is None:
                break
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except Exception:
                continue
            if "id" in msg:
                with self._lock:
                    slot = self._pending.pop(msg["id"], None)
                if slot is not None:
                    slot["result"] = msg.get("result")
                    slot["error"] = msg.get("error")
                    slot["event"].set()
            elif "method" in msg:
                handlers = self._event_handlers.get(msg["method"])
                if handlers:
                    params = msg.get("params") or {}
                    for cb in handlers:
                        try:
                            cb(params)
                        except Exception as e:
                            print("[cdp_ws] event handler for %s failed: %s" % (msg["method"], e))

    def send_command(self, method, params=None, timeout=15.0):
        with self._lock:
            cmd_id = self._next_id
            self._next_id += 1
            slot = {"event": threading.Event(), "result": None, "error": None}
            self._pending[cmd_id] = slot
        payload = {"id": cmd_id, "method": method, "params": params or {}}
        self._ws.send_text(json.dumps(payload))
        if not slot["event"].wait(timeout):
            with self._lock:
                self._pending.pop(cmd_id, None)
            raise WSError("Timed out waiting for CDP response to %s" % method)
        if slot["error"]:
            raise WSError("CDP error %s: %s" % (method, slot["error"]))
        return slot["result"] or {}

    def close(self):
        self._stop = True
        self._ws.close()


def list_targets(host="127.0.0.1", port=9222, timeout=5.0):
    url = "http://%s:%s/json" % (host, port)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_page_ws_url(url_substr, host="127.0.0.1", port=9222, timeout=5.0):
    """CDP WebSocket address of the page target (type == 'page') whose url
    contains url_substr, or None if not found."""
    for t in list_targets(host, port, timeout=timeout):
        if t.get("type") == "page" and url_substr in (t.get("url") or ""):
            return t.get("webSocketDebuggerUrl")
    return None


def decode_connect_frames(raw_bytes):
    """Parses a stream of Connect-RPC envelopes (1 flags byte + 4
    big-endian length bytes + JSON) into a list of (flags, obj) tuples.
    This exact byte-precise decode only works on REAL raw bytes (e.g. from
    Network.getResponseBody). HAR 'text' fields saved without
    encoding=base64 mangle binary bytes via UTF-8 re-encoding, so offline
    HAR-based tests use a balanced-brace JSON scan instead (see
    test_v87_1.py). An incomplete trailing frame is silently dropped."""
    out = []
    i = 0
    n = len(raw_bytes)
    while i + 5 <= n:
        flags = raw_bytes[i]
        length = int.from_bytes(raw_bytes[i + 1:i + 5], "big")
        start = i + 5
        end = start + length
        if end > n:
            break
        payload = raw_bytes[start:end]
        i = end
        try:
            obj = json.loads(payload.decode("utf-8"))
        except Exception:
            continue
        out.append((flags, obj))
    return out


def encode_connect_frame(obj, flags=0):
    """Inverse of decode_connect_frames - test-only helper to build
    synthetic envelopes and verify the decoder round-trips correctly."""
    payload = json.dumps(obj).encode("utf-8")
    return bytes([flags]) + struct.pack(">I", len(payload)) + payload
