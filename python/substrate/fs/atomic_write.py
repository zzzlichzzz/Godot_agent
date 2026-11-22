"""substrate/fs/atomic_write.py - единственный адаптер записи в проект (R-12).

Запись атомарна: temp-файл в том же каталоге, `flush` + `fsync`, `os.replace`,
затем `fsync` каталога (POSIX). Читается `read_raw`: сверка `expected` идёт по
сырым байтам, BOM и `\r\n` входят в хеш (ADR-0005).
"""

import errno
import hashlib
import os

from python.kernel.paths import normalize_rel


class AtomicFileWriter(object):
    """Запись файла проекта: temp рядом -> fsync -> os.replace."""

    def __init__(self, project_root):
        self._root = os.path.abspath(str(project_root))
        self._root_real = os.path.realpath(self._root)

    @property
    def project_root(self):
        return self._root

    def read_raw(self, rel):
        path = self._resolve(rel)
        if not os.path.isfile(path):
            raise FileNotFoundError(errno.ENOENT, "файл не найден")
        with open(path, "rb") as handle:
            return handle.read()

    def exists(self, rel):
        return os.path.exists(self._resolve(rel))

    def is_file(self, rel):
        return os.path.isfile(self._resolve(rel))

    def is_dir(self, rel):
        return os.path.isdir(self._resolve(rel))

    def directory_identity(self, rel):
        path=self._resolve(rel);info=os.stat(path,follow_symlinks=False)
        if not os.path.isdir(path) or os.path.islink(path) or getattr(info,'st_file_attributes',0)&0x400:
            raise PermissionError(errno.EACCES,'plain directory required')
        return hashlib.sha256(('%s:%s'%(info.st_dev,info.st_ino)).encode('ascii')).hexdigest()

    def mkdir(self, rel):
        path=self._resolve(rel);os.mkdir(path);self._fsync_dir(os.path.dirname(path))
        return self.directory_identity(rel)

    def remove_empty_directory(self, rel, proof):
        path=self._resolve(rel)
        if self.directory_identity(rel)!=proof:raise PermissionError(errno.EACCES,'directory replaced')
        os.rmdir(path);self._fsync_dir(os.path.dirname(path))

    def same_file(self, src, dest):
        try:
            return os.path.samefile(self._resolve(src), self._resolve(dest))
        except OSError:
            return False

    def same_directory(self, src, dest):
        return self.is_dir(src) and self.is_dir(dest) and self.same_file(src, dest)

    def actual_rel(self, rel):
        return os.path.relpath(os.path.realpath(self._resolve(rel)),
                               self._root_real).replace(os.sep, "/")

    def move(self, src, dest):
        """Raw direct rename; an occupied foreign destination is never replaced."""
        source, target = self._resolve(src), self._resolve(dest)
        if not os.path.isfile(source):
            raise FileNotFoundError(errno.ENOENT, "источник не является файлом")
        case_only = src != dest and src.casefold() == dest.casefold()
        if os.path.exists(target) and not (case_only and self.same_file(src, dest)):
            raise FileExistsError(errno.EEXIST, "цель уже существует")
        directory = os.path.dirname(target)
        os.makedirs(directory, exist_ok=True)
        self._resolve(dest)
        os.replace(source, target)
        self._fsync_dir(os.path.dirname(source))
        self._fsync_dir(directory)
        return target

    def rename_dir_case(self, src, dest):
        """Change only actual segment casing, directly, without a temporary hop."""
        self._resolve(src)
        self._resolve(dest)
        if src == dest or src.casefold() != dest.casefold():
            raise ValueError("dir_case допускает только изменение регистра")
        if not self.same_directory(src, dest):
            raise ValueError("dir_case требует один существующий каталог")
        old, new = src.split("/"), dest.split("/")
        for index in range(len(old), 0, -1):
            if old[index - 1] == new[index - 1]:
                continue
            source = self._resolve("/".join(old[:index]))
            target = self._resolve("/".join(old[:index - 1] + [new[index - 1]]))
            os.rename(source, target)
            self._fsync_dir(os.path.dirname(target))
        return self._resolve(dest)

    def create(self, rel, data):
        """Эксклюзивное durable-create: существующая цель не затирается."""
        path = self._resolve(rel)
        directory = os.path.dirname(path) or self._root
        if not os.path.isdir(directory):
            raise FileNotFoundError(errno.ENOENT, "каталог файла не найден")
        with open(path, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        self._fsync_dir(directory)
        return path

    def delete(self, rel):
        """Удалить durable только обычный файл; каталоги не поддерживаются."""
        path = self._resolve(rel)
        if not os.path.exists(path):
            raise FileNotFoundError(errno.ENOENT, "файл не найден")
        if not os.path.isfile(path):
            raise IsADirectoryError(errno.EISDIR, "удаление каталога запрещено")
        os.remove(path)
        self._fsync_dir(os.path.dirname(path) or self._root)

    def write_raw(self, rel, data):
        path = self._resolve(rel)
        directory = os.path.dirname(path) or self._root
        if not os.path.isdir(directory):
            raise FileNotFoundError(errno.ENOENT, "каталог файла не найден")
        temp = os.path.join(directory, ".%s.agent-tmp" % os.path.basename(path))
        try:
            with open(temp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                try:
                    os.remove(temp)
                except OSError:
                    pass
        self._fsync_dir(directory)
        return path

    @staticmethod
    def _fsync_dir(directory):
        """POSIX: `os.replace` переживает падение только после fsync каталога."""
        handle = None
        try:
            handle = os.open(directory, os.O_RDONLY)
            os.fsync(handle)
        except OSError:
            return
        finally:
            if handle is not None:
                try:
                    os.close(handle)
                except OSError:
                    pass

    def _resolve(self, rel):
        rel_path = normalize_rel(rel)
        if rel_path is None:
            raise PermissionError(errno.EACCES, "путь вне проекта")
        full = os.path.join(self._root, *rel_path.split("/"))
        real = os.path.realpath(full)
        if real != self._root_real and not real.startswith(self._root_real + os.sep):
            raise PermissionError(errno.EACCES, "путь вне проекта")
        return full
