"""Consumer-owned read seam and snapshot orchestration (D6); no effect ports."""
from typing import Protocol

from python.kernel.errors import AppError

from .domain import refs


class FileSystem(Protocol):
    def list_files(self) -> list[str]: ...
    def read_raw(self, rel: str) -> bytes: ...
    def is_file(self, rel: str) -> bool: ...
    def exists(self, rel: str) -> bool: ...


def metadata(fs, path):
    try:
        return fs.is_file(path[6:]), fs.exists(path[6:])
    except PermissionError:
        raise AppError("invalid_input", "Путь вне проекта отклонен: %s" % path) from None


def read_project(fs, policy, old, is_directory):
    documents, existing, unsafe = {}, set(), set()
    if not is_directory:
        try:
            text, bom = refs.decode(fs.read_raw(old[6:]))
        except FileNotFoundError:
            raise AppError("not_found", "Исходный файл не найден: %s" % old) from None
        except PermissionError:
            raise AppError("invalid_input", "Путь вне проекта отклонен: %s" % old) from None
        except OSError as exc:
            raise AppError("invalid_input", str(exc.strerror or exc)) from None
        documents[old] = {"text": text, "bom": bom}
    for rel in fs.list_files():
        try:
            if fs.is_file(rel):
                existing.add(rel)
        except PermissionError:
            unsafe.add(rel)
            continue
        if not refs.visible(rel, policy):
            continue
        moving = is_directory and rel.startswith(old[6:] + "/")
        if not moving and not refs.eligible(rel):
            continue
        if "res://" + rel == old:
            continue
        try:
            text, bom = refs.decode(fs.read_raw(rel))
        except OSError:
            continue
        documents["res://" + rel] = {"text": text, "bom": bom}
    return documents, existing, unsafe
