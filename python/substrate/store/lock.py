"""substrate/store/lock.py - файловый лок проекта (ADR-0005, §6.5).

`O_CREAT|O_EXCL` — атомарен и на Windows, и на POSIX; «лок на процесс» не
годится: два экземпляра агента — реальный сценарий. Внутри файла PID и время:
это диагностика, а не основание снимать лок автоматически.
"""

import errno
import json
import os
import time


class FileLock(object):
    """Эксклюзивный лок на интервал применения плана."""

    def __init__(self, state_dir, name="project.lock"):
        self.state_dir = os.path.abspath(str(state_dir))
        self.name = str(name)

    @property
    def path(self):
        return os.path.join(self.state_dir, self.name)

    def acquire(self):
        """True — лок наш; False — занят другим экземпляром."""
        if not os.path.isdir(self.state_dir):
            os.makedirs(self.state_dir, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        except OSError as exc:
            if exc.errno in (errno.EEXIST, errno.EACCES):
                return False
            raise
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid(), "at": time.time()}))
            handle.flush()
            os.fsync(handle.fileno())
        return True

    def release(self):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            return
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise

    def held(self):
        return os.path.isfile(self.path)

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("лок занят: %s" % self.path)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
