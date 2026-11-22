"""protocol/error_map.py - единственная классификация исключений в `kind` (R-15).

Сюда приходят только неожиданные исключения: домен обязан бросать `AppError`
сам. Текст ошибки ОС (`strerror`, путь) клиенту не отдаётся — только редакция.
"""

import errno

from python.kernel.errors import AppError
from python.kernel.text import redact_paths


def from_exception(exc, roots=()):
    if isinstance(exc, FileNotFoundError):
        return _typed("not_found", "файл или каталог не найден", exc, roots)
    if isinstance(exc, PermissionError):
        return _typed("denied", "доступ отклонён политикой путей", exc, roots)
    if isinstance(exc, OSError) and exc.errno == errno.EFBIG:
        return _typed("unavailable", "объект больше лимита чтения", exc, roots)
    return AppError("internal", "внутренняя ошибка: %s" % type(exc).__name__,
                    hint="Подробности в логе агента",
                    details={"error": type(exc).__name__})


def _typed(kind, message, exc, roots):
    reason = redact_paths(str(exc), roots)
    details = {"reason": reason} if reason else {}
    return AppError(kind, message, hint="", details=details)

