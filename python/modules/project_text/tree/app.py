"""Private entrypoint; not a public tool or context contribution."""
from python.kernel.errors import AppError
from python.kernel.schema import validate
from .domain import core

ARGS = {"type": "object", "properties": {
    "subdir": {"type": "string"}, "max_depth": {"type": "integer", "minimum": 0, "maximum": 64},
    "max_entries": {"type": "integer", "minimum": 0, "maximum": 200000},
    "only_exts": {"type": ["array", "null"], "items": {"type": "string"}}}, "additionalProperties": False}


def build(args, ctx):
    problems = validate(args, ARGS)
    if problems:
        raise AppError("invalid_input", "; ".join(problems))
    fs = ctx.port("project_text_fs")
    path = args.get("subdir") or "res://"
    try:
        base = fs.resolve(path, ctx.path_policy, tree=True)
    except AppError as exc:
        if exc.kind == "denied" and "политикой доступа" in exc.message:
            return core.build([], path[6:].rstrip("/"))
        raise
    if not fs.is_dir(base):
        raise AppError("not_found", "Папка не найдена: " + path)
    try:
        entries = fs.entries(base, ctx.path_policy, core.visible_entry)
    except OSError:
        raise AppError("denied", "Папка недоступна для чтения: " + path) from None
    return core.build(entries, base, args.get("max_depth", 8), args.get("max_entries", 200), args.get("only_exts"))
