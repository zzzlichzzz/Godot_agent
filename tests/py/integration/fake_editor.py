"""fake_editor.py - фейковый мост редактора для сценариев протокола (ADR-0007).

Слушает петлю, говорит тем же кадром (4 байта BE + JSON), пишет `port.json` так
же, как GDScript-сервер, и проверяет токен в каждом кадре - то есть повторяет
правила `editor/bridge/`, но на Python, чтобы сценарии шли без живого Godot.
Режимы отказа - из §5 среза: молчание, обрыв кадра, чужие `verbs_version` и
`project_hash`, двойной ответ, ответ не на тот примитив, кадр больше лимита,
мусор по схеме. Живой сервер проверяется харнессом `editor/harness/validate.gd`
(`needs_live`), приёмкой он не считается.
"""

import hashlib
import json
import os
import socket
import threading
import time

from python.substrate.editor import framing

#: Годные ответы трёх примитивов (совпадают с `result_schema` словаря).
PING = {"godot": "4.6", "verbs_version": 3, "protocol": 1,
        "open_scenes": 1, "uptime_s": 12.5}
SCENE = {"path": "res://main.tscn", "revision": 3, "dirty": False,
         "active": True, "unsaved_changes": 0}
STATE = {"open_scenes": [SCENE], "active_scene": "res://main.tscn",
         "project_hash": "proj-hash"}
SELECTION = {"node_path": "/root/Main/Player", "scene": "res://main.tscn",
             "properties": [{"name": "position", "type": "Vector2",
                             "value": [1, 2]}],
             "script": "res://player.gd"}
ANSWERS = {"editor_ping": PING, "editor_state": STATE,
           "editor_selection": SELECTION}

#: Примитивы батча сцены: ответ строится из запроса, а не из таблиц выше.
SCENE_VERBS = ("editor_scene_plan", "editor_scene_apply")

#: Поле узла по операции - как `steps[].target_node` в словаре примитивов.
TARGETS = {"add_node": "parent", "set_property": "node", "attach_script": "node",
           "connect_signal": "from"}


def own_digest(scene, revision, operations):
    """Отпечаток «чужой реализации»: с доменом он намеренно не совпадает."""
    body = json.dumps([scene, revision, operations], sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def target_of(operation):
    """Узел, которого касается операция (для `target_node` и `node_path`)."""
    return str(operation.get(TARGETS.get(operation.get("op"), "node")) or ".")


#: Режимы фейка: годный снимок плюс отказы из §5.
MODES = ("ok", "slow", "silent", "silent_hello", "close", "truncate", "too_big",
         "verbs_mismatch", "wrong_project", "bad_token", "double",
         "wrong_request", "garbage")


class FakeEditor:
    """Мост в минимуме: handshake первым кадром, токен в каждом кадре, один ответ."""

    def __init__(self, mode="ok", token="fake-token", project_hash="proj-hash",
                 verbs_version=3, answers=None, digest_fn=None, scene=None):
        modes = [mode] if isinstance(mode, str) else list(mode)
        for item in modes:
            if item not in MODES:
                raise ValueError("неизвестный режим фейка: %r" % (item,))
        self._modes = modes
        self.mode = modes[0]
        self.token = token
        self.project_hash = project_hash
        self.verbs_version = verbs_version
        self.answers = dict(ANSWERS if answers is None else answers)
        self.digest_fn = own_digest if digest_fn is None else digest_fn
        self.scene = dict(scene or {})
        self.frames = []
        self.connections = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(4)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def write_port_file(self, path):
        """`port.json` как у сервера: порт, токен, pid, protocol, verbs_version."""
        data = {"port": self.port, "token": self.token, "pid": os.getpid(),
                "protocol": 1, "verbs_version": self.verbs_version,
                "project_hash": self.project_hash}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        return str(path)

    def close(self):
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        self._thread.join(timeout=2)

    # --- сервер -------------------------------------------------------
    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._guard, args=(conn,), daemon=True).start()

    def _guard(self, conn):
        """Одно соединение в своём потоке: молчащий мост не блокирует accept."""
        try:
            self._session(conn)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _session(self, conn):
        conn.settimeout(2)
        if len(self._modes) > 1:
            self.mode = self._modes.pop(0)
        else:
            self.mode = self._modes[0]
        hello = self._frame(conn)
        if hello is None:
            return
        self.frames.append(hello)
        if self.mode == "close":
            return
        if not self._hello_ok(conn, hello):
            return
        if not self._reply_hello(conn):
            return
        while not self._stop.is_set():
            request = self._frame(conn)
            if request is None:
                return
            self.frames.append(request)
            if not self._verb(conn, request):
                return

    def _hello_ok(self, conn, hello):
        """Токен и protocol проверяются до всего: отказ закрывает соединение."""
        payload = hello.get("hello")
        reason = None
        if not isinstance(payload, dict):
            reason = "truncated"
        elif str(payload.get("token") or "") != self.token:
            reason = "bad_token"
        elif payload.get("protocol") != 1:
            reason = "verbs_mismatch"
        if reason is None:
            return True
        self._error(conn, reason, "handshake отвергнут: %s" % reason)
        return False

    def _reply_hello(self, conn):
        if self.mode == "silent_hello":
            return False
        if self.mode == "bad_token":
            self._error(conn, "bad_token", "токен не совпал")
            return False
        version = (self.verbs_version + 1 if self.mode == "verbs_mismatch"
                   else self.verbs_version)
        project = "other-project" if self.mode == "wrong_project" else self.project_hash
        self._send(conn, {"hello": {"protocol": 1, "verbs_version": version,
                                    "godot": "4.6", "project_hash": project,
                                    "token": self.token}})
        return True

    def _verb(self, conn, request):
        verb = str(request.get("verb") or "")
        if str(request.get("token") or "") != self.token:
            self._error(conn, "bad_token", "кадр без токена")
            return False
        if self.mode == "slow":
            time.sleep(0.3)
        if self.mode == "silent":
            time.sleep(1.0)
            return False
        if self.mode == "truncate":
            conn.sendall(b"\x00\x00\x01\x00{\"ok\":")
            return False
        if self.mode == "too_big":
            conn.sendall(b"\x00\x10\x00\x01")
            return False
        if verb in SCENE_VERBS:
            return self._scene(conn, verb, request)
        if verb not in self.answers:
            self._error(conn, "unknown_verb", "мост не знает %r" % (verb,))
            return True
        result = STATE if self.mode == "wrong_request" else self.answers[verb]
        self._send(conn, {"ok": True, "result": result})
        if self.mode == "double":
            self._send(conn, {"ok": True, "result": result})
        return True

    def _scene(self, conn, verb, request):
        """План или применение: ответ собирается из запроса и `self.scene`.

        `self.scene` - сценарий отказа: `error` (кадр с ошибкой), `fail_at`
        (шаг не применился), `drop_receipts` (пусто вместо квитанций),
        `digest`/`revision`/`apply_revision`/`scene` - подмена значений.
        """
        args = request.get("args") or {}
        over = self.scene
        if self.mode == "wrong_request":
            self._send(conn, {"ok": True, "result": STATE})
            return True
        reason = over.get("error")
        if reason:
            self._error(conn, str(reason), "сцена: отказ по требованию сценария")
            return True
        scene = str(over.get("scene") or args.get("scene") or "")
        revision = int(over.get("revision", args.get("expected_revision", 0)))
        operations = [item for item in (args.get("operations") or [])
                      if isinstance(item, dict)]
        digest = str(over.get("digest")
                     or self.digest_fn(scene, revision, operations))
        if verb == "editor_scene_plan":
            result = {"scene": scene, "revision": revision,
                      "plan_digest": digest,
                      "steps": [{"index": index, "op": item.get("op"),
                                 "target_node": target_of(item),
                                 "preview": "%s %s" % (item.get("op"),
                                                       target_of(item))}
                                for index, item in enumerate(operations)],
                      "would_change": [target_of(item) for item in operations],
                      "warnings": []}
        else:
            fail_at = int(over.get("fail_at") or 0)
            receipts = [{"step_id": index, "op": item.get("op"),
                         "node_path": target_of(item),
                         "applied": not fail_at or index + 1 != fail_at}
                        for index, item in enumerate(operations)]
            if over.get("drop_receipts"):
                receipts = []
            result = {"scene": scene,
                      "applied_revision": int(over.get("apply_revision",
                                                       revision + 1)),
                      "undo_label": str(args.get("undo_label")
                                        or "agent: scene_ops"),
                      "receipts": receipts,
                      "changes": [{"node_path": receipt["node_path"],
                                   "field": str(operations[index].get("property")
                                                or operations[index].get("op")),
                                   "before": None,
                                   "after": str(operations[index].get("op"))}
                                  for index, receipt in enumerate(receipts)]}
        self._send(conn, {"ok": True, "result": result})
        return True

    # --- кадры --------------------------------------------------------
    def _frame(self, conn):
        buffer = b""
        while True:
            obj, _ = framing.decode(buffer)
            if obj is not None:
                return obj
            try:
                chunk = conn.recv(65536)
            except (OSError, socket.timeout):
                return None
            if not chunk:
                return None
            buffer += chunk

    @staticmethod
    def _send(conn, obj):
        conn.sendall(framing.encode(obj))

    def _error(self, conn, reason, message):
        kind = {"bad_token": "denied", "unknown_verb": "unknown_tool"}.get(
            reason, "engine_down")
        self._send(conn, {"ok": False,
                          "error": {"kind": kind, "reason": reason,
                                    "message": message}})

