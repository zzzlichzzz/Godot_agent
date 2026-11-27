"""Consumer-owned read port; existing bootstrap fs structurally implements it."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class RawReader(Protocol):
    def read_raw(self, rel_path: str) -> bytes:
        """Original bytes, including BOM/EOL, within the shared reading limit."""
