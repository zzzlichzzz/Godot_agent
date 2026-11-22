"""Consumer-owned protocol, structurally supplied by existing filesystem."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class RawReader(Protocol):
    def read_raw(self, rel_path: str) -> bytes: ...
