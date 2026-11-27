"""Frozen internal preload/load/extends projection, with an immutable existence set."""
import posixpath
import re

from python.kernel.errors import AppError

IMPORT_PATTERN = re.compile(r'(\b(?:preload|load|extends)\s*\(?\s*["\'])([^"\']+)(["\'])')


def project_details(text, old, new, existing, moved_files_map=None, unsafe=()):
    old_dir = posixpath.dirname(old[6:].strip("/"))
    new_dir = posixpath.dirname(new[6:].strip("/"))
    if old_dir == new_dir and not moved_files_map:
        return text, 0, []
    moved = moved_files_map or {}
    changes, rels = 0, []

    def replace(match):
        nonlocal changes
        raw = match.group(2)
        if raw.startswith("uid://"):
            return match.group(0)
        if raw.startswith("res://"):
            if raw in moved:
                changes += 1
                return match.group(1) + moved[raw] + match.group(3)
            return match.group(0)
        target = posixpath.normpath(posixpath.join(old_dir, raw.replace("\\", "/")))
        target_godot = "res://" + target
        if target.startswith(("../", "/")) or target == ".." or (len(target) > 1 and target[1] == ":") or target in unsafe:
            raise AppError("invalid_input", "Путь вне проекта отклонен: %s" % target_godot)
        if target == ".agent_history" or target.startswith(".agent_history/"):
            raise AppError("denied", "Доступ к служебной папке истории запрещён.")
        new_target = moved.get(target_godot, target_godot)
        new_rel = new_target[6:]
        if target not in existing and target_godot not in moved:
            return match.group(0)
        if new_rel.startswith(new_dir + "/") or posixpath.dirname(new_rel) == new_dir:
            value = posixpath.relpath(new_rel, new_dir or ".")
            if not value.startswith(".") and raw.startswith("./"):
                value = "./" + value
        else:
            value = new_target
        if value != raw:
            changes += 1
            rels.append([match.start(2), match.end(2), raw])
            return match.group(1) + value + match.group(3)
        return match.group(0)

    updated = IMPORT_PATTERN.sub(replace, text)
    return updated, changes, rels


def update_internal_relative_paths(text, old, new, existing, moved_files_map=None, unsafe=()):
    updated, changes, _rels = project_details(text, old, new, existing, moved_files_map, unsafe)
    return updated, changes


def partition_directory(documents, old):
    """D13: disjoint inputs to the existing projection, not another regex/scanner."""
    prefix = old.rstrip("/") + "/"
    moved = {path: data for path, data in documents.items() if path.startswith(prefix)}
    external = {path: data for path, data in documents.items() if path not in moved}
    return moved, external
