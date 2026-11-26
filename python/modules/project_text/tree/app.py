"""Resolve and enumerate through the existing project-text filesystem port."""
from python.kernel.errors import AppError
from python.kernel.schema import validate
from .domain import core
from .tools import TREE

ARGS = {"type": "object", "properties": {
    "subdir": {"type": "string"}, "max_depth": {"type": "integer", "minimum": 0, "maximum": 64},
    "max_entries": {"type": "integer", "minimum": 0, "maximum": 200000},
    "only_exts": {"type": ["array", "null"], "items": {"type": "string"}}}, "additionalProperties": False}


def build(args, ctx):
    problems = validate(args, ARGS)
    if problems:
        raise AppError("invalid_input", "; ".join(problems))
    return _build(args, ctx)


def call(tool, args, ctx):
    if tool != "tree":
        raise AppError("unknown_tool", "project_text.tree only owns tree")
    problems = validate(args, TREE.args)
    if problems:
        raise AppError("invalid_input", "; ".join(problems))
    return _build(args, ctx, public=True)


def _build(args, ctx, *, public=False):
    fs = ctx.port("project_text_fs")
    path = args.get("subdir") or "res://"
    depth = args.get("max_depth", 3 if public else 8)
    try:
        base = fs.resolve(path, ctx.path_policy, tree=True)
    except AppError as exc:
        if not public and exc.kind == "denied" and "политикой доступа" in exc.message:
            return core.build([], path[6:].rstrip("/"))
        raise
    if not fs.is_dir(base):
        raise AppError("not_found", "Папка не найдена: " + path)
    try:
        visible = (lambda row, rel: core.visible_at_depth(row, rel, depth)) if public else core.visible_entry
        if public:
            entries, scan_truncated = fs.entries(base, ctx.path_policy, visible,
                                                  max_scanned=TREE.limits['max_scanned'])
        else:
            entries = fs.entries(base, ctx.path_policy, visible)
    except OSError:
        raise AppError("denied", "Папка недоступна для чтения: " + path) from None
    extensions = args.get("only_exts")
    if public and extensions is not None:
        extensions = {ext.lower() for ext in extensions}
    result = core.build(entries, base, depth, args.get("max_entries", 200), extensions,
                        max_nodes=TREE.limits["max_nodes"] if public else None)
    if public:
        result['truncated'] |= scan_truncated
    return result
