"""Prepare the one durable WAL and expose safe summaries, not raw payloads."""
from python.kernel.write_plan import WritePlan, digest_of


def save(ctx, request, compiled):
    steps, expected, summary = compiled
    old, new, references = request
    digest = digest_of("file_refactor", old, old, new, "references", references, steps, expected)
    plan = WritePlan(ctx.ids("plan"), digest, tuple(steps), expected)
    ctx.port("journal").write_prepared(plan.as_dict(), detail={"tool": "file_refactor", "summary": summary})
    return dict(summary, plan_id=plan.plan_id, digest=plan.digest, state=plan.state,
                steps_count=len(steps), confirm_ttl=plan.confirm_ttl)
