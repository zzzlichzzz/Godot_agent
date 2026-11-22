"""Consumer-owned structural ports; bootstrap supplies existing adapters."""
from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class RawReader(Protocol):
    def read_raw(self, rel_path: str) -> bytes: ...


@runtime_checkable
class Linter(Protocol):
    def __call__(self, text: str) -> Sequence[str]: ...
