"""Consumer-owned source-file port; contributions retain their own contracts."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class FileSystem(Protocol):
    def is_file(self, rel_path: str) -> bool: ...
    def read_raw(self, rel_path: str) -> bytes: ...
