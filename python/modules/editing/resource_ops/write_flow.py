"""Read port, unchanged guards, pure compiler, and the existing WAL funnel."""
import base64
import hashlib

from python.kernel.errors import AppError
from python.kernel.write_plan import Step, WritePlan
from ..shared import funnel
from .domain import core, transform


def snapshot(action, ctx, expected_hash=None):
    reader = ctx.port("resource_read")
    normalized, rel = core.normalize_action(reader.snapshot(action), action)
    funnel.guard_path(ctx, rel)
    raw = reader.read_raw("res://" + rel)
    expected = {"res://" + rel: hashlib.sha256(raw).hexdigest()}
    if expected_hash is not None and expected_hash != expected["res://" + rel]:
        raise AppError("stale_plan", "файл изменился после плана: res://" + rel)
    resources = {}
    for path in dict.fromkeys([*normalized.get("wait_for_import", ()), *transform.dependencies(raw)]):
        _, dependency = core._path(reader.snapshot(path), path, "wait_for_import")
        funnel.guard_transfer(ctx, dependency, dependency)
        resources[path] = reader.read_raw(path)
        expected["res://" + dependency] = hashlib.sha256(resources[path]).hexdigest()
    return normalized, rel, raw, resources, expected


def prepare(action, ctx, expected_hash=None):
    lock = ctx.port("lock")
    if not lock.acquire():
        raise AppError("conflict", "проект занят", details={"reason": "lock_busy"})
    try:
        normalized, rel, raw, resources, expected = snapshot(action, ctx, expected_hash)
        target = "res://" + rel
        output = transform.transform(raw, normalized, resources)
        step = Step("replace_raw", target, {"bytes_b64": base64.b64encode(output).decode("ascii")}, expected[target])
        digest = core.canonical_digest(normalized)
        plan = WritePlan(ctx.ids("plan"), digest, (step,), expected).as_dict()
        funnel.preflight(ctx, plan)
        ctx.port("journal").write_prepared(plan, {"tool": "resource_ops"})
        return {"plan_id": plan["plan_id"], "digest": digest, "target": target, "before_hash": expected[target]}
    finally:
        lock.release()
