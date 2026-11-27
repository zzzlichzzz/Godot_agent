"""substrate/editor/session.py - одно соединение моста: hello, токен, in-flight.

Состояние соединения живёт здесь, таймауты и повторы - в `retry.py`, сокет и
кадры - в `client.py`. Правила: R-14 (только транспорт), R-15 (отказы
типизированы), ADR-0007 (расхождение версии - `verbs_mismatch`, чужой проект -
`wrong_project`).
"""

from python.kernel.errors import AppError

#: Версия протокола моста (`frame.handshake.protocol`).
PROTOCOL = 1


def _as_int(value):
    """Целое из кадра; bool и строки целыми не считаются."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


class Session:
    """Что сервер сказал в hello и чем мы его дальше зовём."""

    __slots__ = ("protocol", "verbs_version", "godot", "project_hash", "token",
                 "in_flight")

    def __init__(self):
        self.protocol = PROTOCOL
        self.verbs_version = None
        self.godot = ""
        self.project_hash = ""
        self.token = ""
        self.in_flight = False

    def hello(self, token, version, project_hash=""):
        """Первый кадр: кто мы, какую версию словаря ждём и в каком проекте."""
        self.token = str(token or "")
        self.verbs_version = _as_int(version)
        self.project_hash = str(project_hash or "")
        return {"hello": {"protocol": PROTOCOL, "verbs_version": self.verbs_version,
                          "godot": "python", "project_hash": self.project_hash,
                          "token": self.token}}

    def frame(self, verb, args=None):
        """Кадр примитива: токен едет в каждом кадре (SEC-03), а не только в hello."""
        return {"verb": str(verb), "args": dict(args or ()), "token": self.token}

    def accept(self, message):
        """Проверить hello сервера; расхождение - отказ с точной причиной."""
        hello = message.get("hello") if isinstance(message, dict) else None
        if not isinstance(hello, dict):
            raise AppError("engine_down", "мост не поздоровался",
                           hint="Первый кадр сервера - hello (ADR-0007)",
                           details={"reason": "truncated"})
        protocol = _as_int(hello.get("protocol"))
        version = _as_int(hello.get("verbs_version"))
        if protocol != PROTOCOL or version != self.verbs_version:
            raise AppError("engine_down", "другая версия моста",
                           hint="Словарь: contract/editor_verbs.json, ADR-0007",
                           details={"reason": "verbs_mismatch",
                                    "server_protocol": hello.get("protocol"),
                                    "server_verbs_version": hello.get("verbs_version")})
        server_project = str(hello.get("project_hash") or "")
        if self.project_hash and server_project != self.project_hash:
            raise AppError("engine_down", "мост слушает другой проект",
                           hint="Редактор открыл не тот проект (ADR-0007)",
                           details={"reason": "wrong_project",
                                    "server_project": server_project})
        self.godot = str(hello.get("godot") or "")
        self.project_hash = server_project or self.project_hash
