"""Consumer-owned snapshot/transfer ports; all scanning belongs to C.21."""
from typing import Protocol

from python.kernel.errors import AppError
import python.modules.editing.paths_preview as paths_preview

from ..shared import funnel
from .domain import core


class Writer(Protocol):
    def read_raw(self, rel: str) -> bytes: ...
    def exists(self, rel: str) -> bool: ...
    def is_file(self, rel: str) -> bool: ...
    def same_file(self, src: str, dest: str) -> bool: ...
    def same_directory(self, src: str, dest: str) -> bool: ...
    def move(self, src: str, dest: str): ...
    def rename_dir_case(self, src: str, dest: str): ...


def snapshot(ctx, request):
    old, new, _references = request
    writer = ctx.port("writer")
    try:
        source_file, source_exists = writer.is_file(old[6:]), writer.exists(old[6:])
        target_exists = writer.exists(new[6:])
        case = old.casefold() == new.casefold() and writer.same_file(old[6:], new[6:])
    except PermissionError:
        raise AppError("invalid_input", "Путь вне проекта отклонен: %s" % old) from None
    directory = core.validate(old, new, source_file, source_exists, target_exists, case)
    for path in (old, new):
        try:
            funnel.guard_transfer(ctx, path[6:], path[6:])
        except AppError:
            if directory and path.casefold().startswith("res://addons/godot_agent"):
                message = "Directory relocation protected by current access policy (overlaps Godot Agent): %s"
            else:
                message = "Путь защищён текущей политикой доступа: %s"
            raise AppError("denied", message % path) from None
    if not directory:
        for suffix, word in ((".import", "ассет"), (".uid", "файл")):
            if old.lower().endswith(suffix) and writer.is_file(old[6:-len(suffix)]):
                message = ("Не следует переименовывать файл %s напрямую. Переименуйте сам %s (%s), "
                           "и его %s обновится автоматически.")
                raise AppError("invalid_input", message % (suffix, word, old[:-len(suffix)], suffix))
    documents, existing, unsafe = paths_preview.snapshot(ctx.port("paths_fs"), ctx.path_policy, old, directory)
    candidates = sorted(path for path in documents if path.startswith(old + "/")) if directory else [old]
    owners = {path: new + path[len(old):] for path in candidates if not path.lower().endswith((".uid", ".import"))}
    imports = {path: new + path[len(old):] for path in candidates if path.lower().endswith(".import")}
    if not directory:
        owners, imports = {old: new}, {}
        if writer.is_file(old[6:] + ".import"):
            imports[old + ".import"] = new + ".import"
    if not owners and not imports:
        raise AppError("invalid_input", "Папка %s не содержит подходящих файлов для перемещения" % old)
    raw = {}
    for path, dest in list(owners.items()) + list(imports.items()):
        funnel.guard_transfer(ctx, path[6:], dest[6:])
        if writer.exists(dest[6:]) and not (path.casefold() == dest.casefold() and writer.same_file(path[6:], dest[6:])):
            suffix = " .import" if path in imports else ""
            raise AppError("conflict", "Целевой файл%s уже существует: %s" % (suffix, dest))
        raw[path] = writer.read_raw(path[6:])
        if path in owners and writer.is_file(path[6:] + ".uid"):
            uid, uid_dest = path + ".uid", dest + ".uid"
            if writer.exists(uid_dest[6:]) and not (uid.casefold() == uid_dest.casefold() and writer.same_file(uid[6:], uid_dest[6:])):
                raise AppError("conflict", "Целевой файл .uid уже существует: %s" % uid_dest)
            raw[uid] = writer.read_raw(uid[6:])
    parent_old = old if directory else old.rsplit("/", 1)[0]
    parent_new = new if directory else new.rsplit("/", 1)[0]
    dir_case = (parent_old, parent_new) if (parent_old != parent_new and parent_old.casefold() == parent_new.casefold()
               and writer.same_directory(parent_old[6:], parent_new[6:])) else None
    return {"documents": documents, "existing": existing, "unsafe": unsafe, "raw": raw,
            "owners": owners, "imports": imports, "directory": directory, "dir_case": dir_case}


def read_patches(ctx, snapshot, projected):
    for path in projected:
        if path not in snapshot["raw"]:
            snapshot["raw"][path] = ctx.port("writer").read_raw(path[6:])
