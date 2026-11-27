"""Prepare only: metadata → pure schema → unchanged guards → raw hash."""
import uuid

from python.kernel.errors import AppError
from python.modules.editing.shared.funnel import guard_path, guard_transfer

from .domain import core
from . import write_flow


def normalize_action(action, ctx, **kwargs):
    return core.normalize_action(ctx.port("resource_read").snapshot(action), action, **kwargs)


def prepare(action, ctx, allow_addons=False, allow_self_edit=False, addon_dir=None):
    normalized, rel = normalize_action(action, ctx, allow_addons=allow_addons,
                                       allow_self_edit=allow_self_edit, addon_dir=addon_dir)
    guard_path(ctx, rel)
    for dependency in normalized.get("wait_for_import", ()):
        _, dependency_rel = core._path(ctx.port("resource_read").snapshot(dependency), dependency, "wait_for_import")
        guard_transfer(ctx, dependency_rel, dependency_rel)
    before_hash = ctx.port("resource_read").file_sha256("res://" + rel)
    return {"action_id": uuid.uuid4().hex, "action": normalized,
            "resource": normalized["resource"], "target": normalized["resource"],
            "action_digest": core.canonical_digest(normalized), "before_hash": before_hash, "state": "preview"}


def file_sha256(path, ctx):
    core._text(path, "resource")
    if not path.startswith("res://"):
        raise AppError("invalid_input", "resource должен быть res:// путём")
    return ctx.port("resource_read").file_sha256(path)


def canonical_digest(action, ctx):
    return core.canonical_digest(action)


def public_prepared(prepared, ctx):
    return core.public_prepared(prepared)


def operation_summary(action, ctx):
    return core.operation_summary(action)


def prepare_write(action, ctx, expected_hash=None):
    return write_flow.prepare(action, ctx, expected_hash)


def apply(args, ctx):
    return ctx.call_tool("write_apply", {key: args.get(key) for key in ("plan_id", "digest")} if isinstance(args, dict) else args)


def transform_summary(action, ctx, expected_hash=None):
    normalized, rel, raw, resources, expected = write_flow.snapshot(action, ctx, expected_hash)
    output = write_flow.transform.transform(raw, normalized, resources)
    return {"before_hash": expected["res://" + rel], "after_hash": write_flow.hashlib.sha256(output).hexdigest()}
