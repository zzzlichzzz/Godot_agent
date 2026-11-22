"""substrate/fs/memory_fs.py - тот же порт в памяти: тесты и предпросмотр (ADR-0003).

Порядок выдачи — лексикографический: тесты не должны зависеть от порядка
вставки, иначе они проверяют `dict`, а не механику.
"""

import errno


class MemoryFileSystem:
    """Файлы проекта как словарь `путь -> текст`."""

    def __init__(self, files=None):
        self._files = dict(files or {})

    def add(self, rel_path, text):
        self._files[str(rel_path)] = str(text)

    def list_files(self):
        return sorted(self._files)

    def list_entries(self, subdir="", accept=None, directories=()):
        """Same primitive; explicit empty dirs belong to this new API only."""
        dirs = set(directories)
        for path in tuple(self._files) + tuple(dirs):
            parts = path.split("/")
            dirs.update("/".join(parts[:i]) for i in range(1, len(parts)))
        rows = [{"path": path, "type": "dir"} for path in dirs]
        rows += [{"path": path, "type": "file"} for path in self._files]
        blocked = []
        result = []
        for row in sorted(rows, key=lambda item: item["path"]):
            path = row["path"]
            if subdir and not path.startswith(subdir + "/"):
                continue
            if any(path.startswith(parent + "/") for parent in blocked):
                continue
            if accept is not None and not accept(row):
                if row["type"] == "dir":
                    blocked.append(path)
                continue
            result.append(row)
        return result

    def read_text(self, rel_path):
        try:
            return self._files[str(rel_path)]
        except KeyError:
            raise FileNotFoundError(errno.ENOENT, "файл не найден") from None

    def read_raw(self, rel_path):
        """Байты того же текста: двойник обязан уметь оба чтения (ADR-0003)."""
        return self.read_text(rel_path).encode("utf-8")

    def is_file(self, rel_path):
        return str(rel_path) in self._files

    def exists(self, rel_path):
        return str(rel_path) in self._files

    def write_text(self, rel_path, text):
        self._files[str(rel_path)] = str(text)

    def create(self, rel_path, text):
        path = str(rel_path)
        if path in self._files:
            raise FileExistsError(errno.EEXIST, "файл уже существует")
        self._files[path] = str(text)

    def delete(self, rel_path):
        path = str(rel_path)
        if path not in self._files:
            raise FileNotFoundError(errno.ENOENT, "файл не найден")
        del self._files[path]
