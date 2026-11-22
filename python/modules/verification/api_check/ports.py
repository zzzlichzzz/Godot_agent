"""Consumer-owned read-only snapshot seam; implementation is structural."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class ApiCache(Protocol):
    def snapshot(self) -> tuple[dict, str]: ...
