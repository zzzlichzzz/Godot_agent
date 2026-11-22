"""Consumer-owned structural extension of the existing librarian port."""
from typing import Protocol


class JudgeReader(Protocol):
    def judge(self, full_text: str, *, allow_addons: bool = False,
              allow_self_edit: bool = False) -> dict: ...
