"""Module-owned structural read port; implementations belong to substrate."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class Librarian(Protocol):
    def answer(self, query: str, budget_chars: int, *, allow_addons: bool = False,
               allow_self_edit: bool = False, target: str | None = None) -> str: ...
