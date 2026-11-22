"""C.22 frozen lexical request/refusal semantics; no IO."""
import re

from python.kernel.errors import AppError


def normalize(value):
    path = str(value or "").strip().replace("\\", "/")
    if not path.startswith("res://"):
        raise AppError("invalid_input", "Путь должен начинаться с res://: %s" % value)
    rel = path[6:].strip("/")
    if not rel or any(part in ("", ".", "..") for part in rel.split("/")) or "\x00" in rel:
        raise AppError("invalid_input", "Некорректный путь: %s" % value)
    return "res://" + rel


def request(args):
    old, new = normalize(args.get("old_path")), normalize(args.get("new_path"))
    if old == new:
        raise AppError("invalid_input", "Новый путь совпадает со старым: %s" % old)
    return old, new, bool(args.get("update_references", True))


def validate(old, new, source_file, source_exists, target_exists, case_only):
    if not source_exists:
        raise AppError("not_found", "Исходный файл не найден: %s" % old)
    directory = not source_file
    if directory and new.casefold().startswith(old.casefold() + "/") and not case_only:
        raise AppError("invalid_input", "Нельзя переместить папку внутрь самой себя: %s -> %s" % (old, new))
    if target_exists and not case_only:
        message = "Целевая папка уже существует: %s" if directory else "Целевой файл уже существует: %s"
        raise AppError("conflict", message % new)
    return directory


def companion_script(text):
    match = re.search(r'\[ext_resource\s+[^\]]*type="Script"[^\]]*path="([^"]+)"', text)
    return match.group(1) if match else None


def import_projection(text, old, new):
    pattern = re.compile(r'(\bsource_file\s*=\s*["\'])' + re.escape(old) + r'(["\'])')
    return pattern.subn(lambda match: match.group(1) + new + match.group(2), text)
