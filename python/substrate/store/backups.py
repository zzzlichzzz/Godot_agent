"""substrate/store/backups.py - бэкапы байтов для отката (ADR-0005, §6.3).

`<state_dir>/backup/<plan_id>/<index>.bin` хранит **сырые** байты файла до
правки: только так откат возвращает CRLF/BOM побайтово. Каталог состояния
лежит вне проекта, поэтому бэкапы не засоряют рабочее дерево.
"""

import errno
import os

_PLAN_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")


def _safe(plan_id):
    value = str(plan_id or "")
    if not value or not set(value) <= _PLAN_CHARS or value in (".", ".."):
        raise ValueError("недопустимый plan_id: %r" % (plan_id,))
    return value


class FileBackups(object):
    """Бэкапы по токену `<plan_id>/<index>.bin`."""

    def __init__(self, state_dir):
        self.state_dir = os.path.abspath(str(state_dir))

    def token(self, plan_id, index):
        return "%s/%d.bin" % (_safe(plan_id), int(index))

    def put(self, plan_id, index, data):
        token = self.token(plan_id, index)
        path = self._path(token)
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return token

    def get(self, token):
        with open(self._path(token), "rb") as handle:
            return handle.read()

    def exists(self, token):
        return os.path.isfile(self._path(token))

    def _path(self, token):
        value = str(token or "").replace("\\", "/")
        parts = [part for part in value.split("/") if part]
        if (not parts or value.startswith("/") or ":" in parts[0]
                or any(part in (".", "..") for part in parts)):
            raise PermissionError(errno.EACCES, "бэкап вне каталога состояния")
        return os.path.join(self.state_dir, *parts)
