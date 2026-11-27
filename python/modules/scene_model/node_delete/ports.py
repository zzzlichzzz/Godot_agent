"""Consumer-owned ports: deletion reads bytes and renders a shared diff only."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class RawReader(Protocol):
    def read_raw(self, rel_path: str) -> bytes: ...


@runtime_checkable
class DiffPreview(Protocol):
    def __call__(self, before: str, after: str) -> dict | None: ...
