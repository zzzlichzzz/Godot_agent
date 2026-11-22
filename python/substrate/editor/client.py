"""substrate/editor/client.py - клиент моста: примитив в редактор и ответ.

Python только спрашивает, слушает GDScript (ADR-0007, R-14): здесь `port.json`,
кадры, handshake и один in-flight на соединение. Смысл ответа проверяет
модуль-вклад (`context.editor_context/domain`), схемы отдаёт словарь
примитивов, «сколько ждать и повторять» - `retry.py`. Сети наружу нет: адрес
моста только петлевой (SEC-03).
"""

import json
import os
import socket
import threading

from python.kernel.errors import AppError, KINDS

from . import framing, retry, verbs_catalog
from .session import Session

#: Адрес моста: только петля (SEC-03, ADR-0007).
HOST = "127.0.0.1"
#: Переменная окружения с путём к `port.json` (в редакторе - `user://godot_agent/port.json`).
PORT_FILE_ENV = "GODOT_AGENT_PORT_FILE"
#: Сколько читать из сокета за раз.
CHUNK = 65536


def _reason(exc):
    """Причина отказа из `details` - по ней решается, повторять ли вызов."""
    details = exc.details if isinstance(exc.details, dict) else {}
    return str(details.get("reason") or "")


class EditorClient:
    """Ленивый клиент: соединяется при первом `call`, а не при создании."""

    def __init__(self, port_file=None):
        self._port_file = (port_file if port_file is not None
                           else os.environ.get(PORT_FILE_ENV, ""))
        self._sock = None
        self._session = None
        self._buffer = b""
        self._lock = threading.Lock()

    def call(self, verb, args=None):
        """Вызвать примитив: один in-flight, повторы только по политике `retry`."""
        with self._lock:
            tries = 0
            while True:
                try:
                    return self._call_once(verb, args)
                except AppError as exc:
                    if tries >= retry.attempts(_reason(exc)):
                        raise
                    tries += 1
                    self.close()

    def result_schema(self, verb):
        """Схема ответа примитива из словаря: модуль substrate не импортирует (R-11)."""
        return verbs_catalog.result_schema(verb)

    def verbs_version(self):
        """Версия словаря, которую клиент ждёт от сервера."""
        return verbs_catalog.version()

    def close(self):
        """Закрыть соединение; следующий `call` соединится заново."""
        sock, self._sock = self._sock, None
        self._session = None
        self._buffer = b""
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    # --- один вызов -----------------------------------------------------
    def _call_once(self, verb, args):
        sock, session = self._connect()
        sock.settimeout(retry.REPLY_TIMEOUT)
        try:
            sock.sendall(framing.encode(session.frame(verb, args)))
            reply = self._read(sock)
        except framing.FrameError as exc:
            raise AppError("engine_down", str(exc),
                           details={"reason": exc.reason}) from None
        except socket.timeout:
            raise AppError("engine_down", "мост не ответил на %r" % (verb,),
                           hint="Таймаут кадра: повтор один раз (retry.py)",
                           details={"reason": "timeout"}) from None
        except OSError:
            raise AppError("engine_down", "соединение с мостом оборвалось",
                           details={"reason": "truncated"}) from None
        self._drain(sock)
        return self._result(verb, reply)

    @staticmethod
    def _result(verb, reply):
        """`{"ok": true, "result": …}` либо отказ сервера с причиной."""
        result = reply.get("result")
        if reply.get("ok") is True and isinstance(result, dict):
            return result
        error = reply.get("error") if isinstance(reply.get("error"), dict) else {}
        kind = str(error.get("kind") or "engine_down")
        raise AppError(kind if kind in KINDS else "engine_down",
                       str(error.get("message") or "мост отказал в %r" % (verb,)),
                       hint="Коды: editor/bridge/dispatch/error_codes.gd",
                       details={"reason": str(error.get("reason") or "truncated")})

    # --- соединение -----------------------------------------------------
    def _connect(self):
        if self._sock is not None and self._session is not None:
            return self._sock, self._session
        info = self._read_port_file()
        try:
            sock = socket.create_connection((HOST, info["port"]),
                                            retry.CONNECT_TIMEOUT)
        except OSError:
            raise AppError("engine_down", "мост не принимает соединения",
                           hint="Порт устарел или редактор закрыт (ADR-0007)",
                           details={"reason": "connect_failed"}) from None
        session = Session()
        try:
            sock.settimeout(retry.HANDSHAKE_TIMEOUT)
            sock.sendall(framing.encode(session.hello(
                info["token"], verbs_catalog.version(), info["project_hash"])))
            self._buffer = b""
            hello = self._read(sock)
            if hello.get("ok") is False:
                self._result("hello", hello)
            session.accept(hello)
        except framing.FrameError as exc:
            sock.close()
            raise AppError("engine_down", str(exc),
                           details={"reason": exc.reason}) from None
        except socket.timeout:
            sock.close()
            raise AppError("engine_down", "мост молчит на hello",
                           details={"reason": "timeout"}) from None
        except OSError:
            sock.close()
            raise AppError("engine_down", "мост оборвал handshake",
                           details={"reason": "truncated"}) from None
        except AppError:
            sock.close()
            raise
        self._sock, self._session = sock, session
        return sock, session



    def _read_port_file(self):
        """Адрес и токен, которые записал редактор; нет файла - `no_bridge`."""
        if not self._port_file:
            raise AppError("unavailable", "адрес моста неизвестен",
                           hint="Редактор пишет user://godot_agent/port.json, "
                                "путь к нему - в %s" % PORT_FILE_ENV,
                           details={"reason": "no_bridge"})
        try:
            with open(self._port_file, "r", encoding="utf-8") as handle:
                info = json.load(handle)
        except (OSError, ValueError):
            raise AppError("unavailable", "мост не запущен: нет port.json",
                           details={"reason": "no_bridge"}) from None
        port = info.get("port") if isinstance(info, dict) else None
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise AppError("unavailable", "port.json испорчен",
                           details={"reason": "no_bridge"})
        return {"port": port, "token": str(info.get("token") or ""),
                "project_hash": str(info.get("project_hash") or "")}

    def _read(self, sock):
        """Один кадр из сокета; обрыв посреди кадра - `truncated`, не битый JSON."""
        while True:
            obj, rest = framing.decode(self._buffer)
            if obj is not None:
                self._buffer = rest
                return obj
            chunk = sock.recv(CHUNK)
            if not chunk:
                raise AppError("engine_down", "мост закрыл соединение",
                               details={"reason": "truncated"})
            self._buffer += chunk

    def _drain(self, sock):
        """Ответ мог прийти дважды: второй кадр - мусор, его не тащим в следующий вызов."""
        try:
            sock.setblocking(False)
            while sock.recv(CHUNK):
                pass
        except (BlockingIOError, InterruptedError, OSError):
            pass
        finally:
            self._buffer = b""
            try:
                sock.settimeout(retry.REPLY_TIMEOUT)
            except OSError:
                pass
