"""Consumer-owned read contracts; structurally bound only in bootstrap."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class SceneReader(Protocol):
    def is_file(self, rel_path: str) -> bool: ...
    def read_raw(self, rel_path: str) -> bytes: ...


@runtime_checkable
class ApiCache(Protocol):
    def classes(self) -> dict: ...
