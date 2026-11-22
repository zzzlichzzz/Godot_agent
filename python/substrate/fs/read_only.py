"""Physical read-only adapter; per-consumer cap without changing the shared fs."""
from .disk_fs import DiskFileSystem


class ReadOnlyFileSystem:
    def __init__(self, project_root, max_bytes):
        self._disk = DiskFileSystem(project_root, max_bytes=max_bytes)

    def list_files(self):
        return self._disk.list_files()

    def read_raw(self, rel):
        return self._disk.read_raw(rel)

    def is_file(self, rel):
        return self._disk.is_file(rel)

    def exists(self, rel):
        return self._disk.exists(rel)
