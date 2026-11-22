"""Consumer-owned byte-reader; existing fs structurally implements this port."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class RawReader(Protocol):
    def read_raw(self, rel_path: str) -> bytes: ...
