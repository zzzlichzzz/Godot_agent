"""kernel/errors.py - типизированные ошибки: kind, message, hint, details (R-15).

Домен возвращает только `kind`; канал оборачивает его в свой протокол. В ответ
клиенту не попадают стектрейсы и абсолютные пути (R-15) — это проверяет
contract-тест.
"""

KINDS = ("invalid_input", "not_found", "denied", "stale_plan", "conflict",
         "engine_down", "unavailable", "internal", "unknown_tool")


class AppError(Exception):
    """Ошибка с машинно-читаемым `kind` и подсказкой для клиента."""

    def __init__(self, kind, message, hint="", details=None):
        if kind not in KINDS:
            raise ValueError("неизвестный kind: %r" % (kind,))
        super().__init__(message)
        self.kind = kind
        self.message = str(message)
        self.hint = str(hint or "")
        self.details = dict(details or {})

    def payload(self):
        data = {"kind": self.kind, "message": self.message, "hint": self.hint}
        if self.details:
            data["details"] = self.details
        return data

    def __repr__(self):
        return "AppError(%r, %r)" % (self.kind, self.message)

