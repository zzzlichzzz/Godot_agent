"""Literal lexical validation and D4 result assembly; no filesystem access."""
from python.kernel.errors import AppError

from . import directory, internal, refs


def normalize(path):
    p = str(path or "").strip().replace("\\", "/")
    if not p.startswith("res://"):
        raise AppError("invalid_input", "Путь должен начинаться с res://: %s" % path)
    rel = p[6:].strip("/")
    if ".." in rel.split("/"):
        raise AppError("invalid_input", "Путь вне проекта отклонен: %s" % path)
    if not rel or any(part in ("", ".") for part in rel.split("/")) or "\x00" in rel:
        raise AppError("invalid_input", "Некорректный путь: %s" % path)
    return "res://" + rel


def request(args):
    old, new = normalize(args.get("old_path")), normalize(args.get("new_path"))
    if old == new:
        raise AppError("invalid_input", "Новый путь совпадает со старым: %s" % old)
    for path in (old, new):
        if path[6:] == ".agent_history" or path[6:].startswith(".agent_history/"):
            raise AppError("denied", "Доступ к служебной папке истории запрещён.")
    return old, new


def validate(old, new, source_file, source_exists, target_exists, policy):
    if not source_exists:
        raise AppError("not_found", "Исходный файл не найден: %s" % old)
    is_directory = not source_file
    if is_directory and new.startswith(old + "/"):
        raise AppError("invalid_input", "Нельзя переместить папку внутрь самой себя: %s -> %s" % (old, new))
    if target_exists:
        message = "Целевая папка уже существует: %s" if is_directory else "Целевой файл уже существует: %s"
        raise AppError("conflict", message % new)
    for path in (old, new):
        if policy.deny_reason(path[6:]) or path == "res://project.godot":
            raise AppError("denied", "Путь защищён текущей политикой доступа: %s" % path)
    return is_directory


def preview(old, new, is_directory, documents, existing, unsafe):
    if is_directory:
        files = directory.references(documents, old, new, existing, unsafe)
        text, count = None, sum(row["occurrences"] for row in files)
    else:
        files = refs.find_file_references(documents, old)
        text = documents[old]["text"]
        changes = 0
        if old.lower().endswith(".gd"):
            text, changes = internal.update_internal_relative_paths(text, old, new, existing, unsafe=unsafe)
        count = changes + sum(row["occurrences"] for row in files)
    return {"old_path": old, "new_path": new, "is_directory": is_directory,
            "file_count": len(files) + (0 if is_directory else 1), "reference_count": count,
            "files": sorted(files, key=lambda row: row["path"]), "source_text": text}
