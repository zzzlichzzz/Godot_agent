"""Consumer-owned structural read/lint/diff ports; composition binds providers."""
from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class RawReader(Protocol):
    def read_raw(self, rel_path: str) -> bytes: ...


@runtime_checkable
class Linter(Protocol):
    def __call__(self, text: str) -> Sequence[str]: ...


@runtime_checkable
class DiffPreview(Protocol):
    def __call__(self, before: str, after: str) -> dict | None: ...
