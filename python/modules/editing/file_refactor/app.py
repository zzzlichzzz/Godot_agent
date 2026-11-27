"""Internal C.22 orchestration; no ToolSpec, MCP capability or second funnel."""
from python.kernel.errors import AppError
from python.kernel.write_plan import WritePlan, digest_of

from ..shared import funnel, plan_log
from . import ports, report, sync_ports
from .domain import compiler, core, sync_compile


def prepare(args, ctx):
    request = core.request(args)
    lock = ctx.port("lock")
    if not lock.acquire():
        raise AppError("conflict", "проект занят", details={"reason": "lock_busy"})
    try:
        snapshot = ports.snapshot(ctx, request)
        projected = compiler.project(request, snapshot)
        ports.read_patches(ctx, snapshot, projected)
        compiled = compiler.compile_plan(request, snapshot, projected,
                                         ctx.port("node_diff"), ctx.port("gd_lint"))
        steps, expected, _summary = compiled
        funnel.preflight(ctx, {"steps": [step.as_dict() for step in steps], "expected": expected})
        return report.save(ctx, request, compiled)
    finally:
        lock.release()


def apply(args, ctx):
    entries = ctx.port("journal").read(args.get("plan_id", ""))
    if plan_log.state_of(entries) == "COMMITTED":
        raise AppError("stale_plan", "план переноса уже применён")
    return ctx.call_tool("write_apply", {"plan_id": args.get("plan_id"), "digest": args.get("digest")})


def sync(args, ctx):
    old, new = core.normalize(args.get("old_path")), core.normalize(args.get("new_path"))
    lock = ctx.port("lock")
    if not lock.acquire():
        raise AppError("conflict", "проект занят", details={"reason": "lock_busy"})
    try:
        if old == new:
            return {"ok": True, "entry_id": None, "plan_id": None, "old_path": old, "new_path": new,
                    "is_directory": bool(args.get("is_directory", False)), "reference_count": 0,
                    "file_count": 0, "changed_paths": [], "patches": [], "moved": [], "anchor_already_completed": False}
        snapshot = sync_ports.snapshot(ctx, old, new, bool(args.get("is_directory", False)))
        steps, expected, summary = sync_compile.compile_plan(old, new, snapshot,
                                      ctx.port("node_diff"), ctx.port("gd_lint"))
        for source, dest, sha in snapshot["completed"]:
            sync_ports.completed_alias(ctx.port("writer"), source, dest, sha)
        if not steps:
            return dict(summary, entry_id=None, plan_id=None, patches=[], moved=[], file_count=0)
        funnel.preflight(ctx, {"steps": [step.as_dict() for step in steps], "expected": expected})
        digest = digest_of("file_refactor_sync", old, old, new, "references", True, steps, expected)
        plan = WritePlan(ctx.ids("plan"), digest, tuple(steps), expected).as_dict()
        ctx.port("journal").write_prepared(plan, {"tool": "file_refactor", "summary": summary})
        return funnel.execute(ctx, plan, lambda plan, entry, receipts, started, finished:
                              dict(summary, entry_id=entry, plan_id=plan["plan_id"]))
    finally:
        lock.release()
