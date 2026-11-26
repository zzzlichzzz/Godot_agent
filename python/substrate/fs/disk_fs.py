"""substrate/fs/disk_fs.py - адаптер порта fs: диск (R-13, SEC-12).

Физика путей здесь: `realpath` и проверка «не вышли за корень проекта».
Правила («что вообще можно читать») — в `kernel/paths.py`.
"""

import errno
import os

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.paths import normalize_rel


class DiskFileSystem:
    """Файлы проекта с containment-проверкой для чтения и file-операций."""

    def __init__(self, project_root, max_bytes=READ_TEXT_MAX_BYTES):
        self._root = os.path.abspath(str(project_root))
        self._root_real = os.path.realpath(self._root)
        self._max_bytes = int(max_bytes)

    @property
    def project_root(self):
        return self._root

    def list_files(self):
        """Относительные пути файлов проекта в порядке обхода (каталоги — по имени).

        Ссылки-каталоги не раскрываются: обход без `followlinks`, поэтому цикл
        и выход за корень через junction невозможны.
        """
        if not os.path.isdir(self._root):
            raise FileNotFoundError(errno.ENOENT, "корень проекта не найден")
        found = []
        for dirpath, dirnames, filenames in os.walk(self._root):
            dirnames[:] = sorted(name for name in dirnames
                                 if not os.path.islink(os.path.join(dirpath, name)))
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self._root).replace(os.sep, "/")
                found.append(rel)
        return found

    def read_text(self, rel_path):
        path = self._resolve(rel_path)
        if os.path.getsize(path) > self._max_bytes:
            raise OSError(errno.EFBIG, "файл больше лимита чтения")
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            return handle.read()

    def list_entries(self, subdir="", accept=None):
        """Primitive enumeration: lstat reparse pointers before scandir recursion."""
        return self._list_entries(subdir, accept, None)[0]

    def list_entries_bounded(self, subdir, accept, max_scanned):
        """Return (rows, truncated); count raw entries, including rejected ones."""
        return self._list_entries(subdir, accept, max_scanned)

    def _list_entries(self, subdir, accept, remaining):
        import stat
        from itertools import islice
        base = self._resolve(subdir) if subdir else self._root
        relative = os.path.relpath(base, self._root)
        cursor = self._root
        for part in (() if relative == "." else relative.split(os.sep)):
            cursor = os.path.join(cursor, part)
            info = os.lstat(cursor)
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return [], False
        rows = []
        def visit(folder):
            nonlocal remaining
            with os.scandir(folder) as entries:
                if remaining is None:
                    ordered = list(entries)
                else:
                    ordered = list(islice(entries, remaining + 1))
                    if len(ordered) > remaining:
                        # Do not publish an arbitrary OS-order subset of this folder.
                        return False
                    remaining -= len(ordered)
                ordered.sort(key=lambda entry: entry.name)
            for entry in ordered:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    continue
                directory = stat.S_ISDIR(info.st_mode)
                if not directory and not stat.S_ISREG(info.st_mode):
                    continue
                row = {"path": os.path.relpath(entry.path, self._root).replace("\\", "/"),
                       "type": "dir" if directory else "file"}
                if accept is not None and not accept(row):
                    continue
                rows.append(row)
                if directory and not visit(entry.path):
                    return False
            return True
        complete = visit(base)
        return sorted(rows, key=lambda row: row["path"]), not complete

    def read_raw(self, rel_path):
        """Байты файла как есть: BOM и переводы строк не трогаются.

        Нужен тем, кто обязан различить `\\r\\n` и `\\n` (пишущие механики) и
        сверить хеш файла до правки. `read_text` для остальных остаётся
        текстовым: он нормализует переводы строк через universal newlines.
        """
        path = self._resolve(rel_path)
        if os.path.getsize(path) > self._max_bytes:
            raise OSError(errno.EFBIG, "файл больше лимита чтения")
        with open(path, "rb") as handle:
            return handle.read()

    def is_file(self, rel_path):
        """Metadata only; same realpath containment, no content-size/read side effect."""
        return os.path.isfile(self._resolve(rel_path))

    def exists(self, rel_path: str) -> bool:
        """Истинно для файла и каталога; is_file остаётся строго про обычный файл.

        Только метаданные с прежним containment, без чтения и записи.
        """
        return os.path.exists(self._resolve(rel_path))

    def write_text(self, rel_path, text):
        """Записать UTF-8 текст; вызывающий отвечает за transactional funnel."""
        path = self._resolve(rel_path)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(str(text))

    def create(self, rel_path, text):
        """Эксклюзивно создать UTF-8 файл, не перезаписывая цель."""
        path = self._resolve(rel_path)
        with open(path, "x", encoding="utf-8", newline="") as handle:
            handle.write(str(text))

    def delete(self, rel_path):
        """Удалить только обычный файл; отсутствие и каталог различаются."""
        path = self._resolve(rel_path)
        if not os.path.exists(path):
            raise FileNotFoundError(errno.ENOENT, "файл не найден")
        if not os.path.isfile(path):
            raise IsADirectoryError(errno.EISDIR, "удаление каталога запрещено")
        os.remove(path)

    def _resolve(self, rel_path):
        rel = normalize_rel(rel_path)
        if rel is None:
            raise PermissionError(errno.EACCES, "путь вне проекта")
        full = os.path.join(self._root, *rel.split("/"))
        real = os.path.realpath(full)
        if real != self._root_real and not real.startswith(self._root_real + os.sep):
            raise PermissionError(errno.EACCES, "путь вне проекта")
        return full
