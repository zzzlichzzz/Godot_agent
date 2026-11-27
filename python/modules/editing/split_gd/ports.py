"""Consumer-owned existing read primitives; no new binding or filesystem mode."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class FileSystem(Protocol):
    def is_file(self, rel_path: str) -> bool:
        """Contained project-file metadata."""

    def exists(self, rel_path: str) -> bool:
        """Contained file-or-directory metadata, only for split target refusal."""

    def read_raw(self, rel_path: str) -> bytes:
        """Bounded original bytes, including BOM/EOL."""

    def list_files(self) -> list[str]:
        """Project-relative files in sorted-directory native walk order."""


@runtime_checkable
class ApiCache(Protocol):
    def snapshot(self) -> tuple[dict, str]:
        """One fresh coherent read of classes and engine version; never refresh/write."""
