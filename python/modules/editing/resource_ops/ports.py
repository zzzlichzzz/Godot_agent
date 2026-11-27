"""Consumer-owned read port over the existing filesystem's public interface."""
import hashlib
import os
from typing import Protocol

from python.kernel.errors import AppError

from .domain import core


class ResourceFileSystem(Protocol):
    project_root: str

    def read_raw(self, rel: str) -> bytes: ...
    def is_file(self, rel: str) -> bool: ...
    def exists(self, rel: str) -> bool: ...


class ResourceRead:
    """No write primitives; resolved facts and a second containment-checked read."""

    def __init__(self, fs: ResourceFileSystem):
        self._fs = fs
        self._root = os.path.realpath(fs.project_root)

    def identity(self, path):
        rel = path[6:].replace("\\", "/")
        if "\x00" in rel:
            return {"relative": None, "contained": False, "is_file": False}
        resolved = os.path.realpath(os.path.join(self._root, rel))
        try:
            root_identity, resolved_identity = os.path.normcase(self._root), os.path.normcase(resolved)
            contained = os.path.commonpath([root_identity, resolved_identity]) == root_identity
        except ValueError:
            contained = False
        relative = os.path.relpath(resolved, self._root).replace("\\", "/") if contained else None
        fact = {"relative": relative, "contained": contained, "is_file": False}
        if core.allowed(fact) and relative != ".":
            try:
                fact["is_file"] = self._fs.is_file(relative)
            except PermissionError:
                fact["contained"] = False
        return fact

    def snapshot(self, value):
        facts = {}

        def walk(item):
            if isinstance(item, str) and item.replace("\\", "/").startswith("res://"):
                path = item.replace("\\", "/")
                if path not in facts:
                    facts[path] = self.identity(path)
            elif isinstance(item, dict):
                for nested in item.values():
                    walk(nested)
            elif isinstance(item, list):
                for nested in item:
                    walk(nested)
        walk(value)
        return facts

    def file_sha256(self, path):
        fact = self.identity(path)
        if not core.allowed(fact):
            raise AppError("denied", core.POLICY_MESSAGE)
        if not fact["is_file"]:
            raise AppError("not_found", "Ресурс не найден: %s" % path)
        try:
            raw = self._fs.read_raw(fact["relative"])
            after = self.identity(path)
            if not core.allowed(after) or after["relative"] != fact["relative"]:
                raise AppError("denied", core.POLICY_MESSAGE)
            return hashlib.sha256(raw).hexdigest()
        except PermissionError:
            raise AppError("denied", core.POLICY_MESSAGE) from None
        except OSError:
            raise AppError("not_found", "Ресурс не найден: %s" % path) from None

    def read_raw(self, path):
        expected, before = self.file_sha256(path), self.identity(path)
        if not core.allowed(before):
            raise AppError("denied", core.POLICY_MESSAGE)
        try:
            raw = self._fs.read_raw(before["relative"])
        except (OSError, PermissionError):
            raise AppError("denied", core.POLICY_MESSAGE) from None
        after = self.identity(path)
        if not core.allowed(after) or after["relative"] != before["relative"]:
            raise AppError("denied", core.POLICY_MESSAGE)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise AppError("stale_plan", "файл изменился при чтении ресурса")
        return raw
