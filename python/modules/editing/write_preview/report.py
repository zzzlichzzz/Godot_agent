"""modules/editing/write_preview/report.py - план, WAL и диффы (ADR-0005).

`app.py` остаётся тонкой оркестрацией, а сборка конверта живёт здесь: digest по
входу и шагам, запись `PREPARED` в журнал (вне проекта) и диффы из ТЕХ ЖЕ
смещений, которые применит часть 2. В проект не пишется ничего (R-12, SEC-11).
"""

import hashlib

from python.kernel import diff
from python.kernel.errors import AppError
from python.kernel.ids import new_id
from python.kernel.text import normalize_newlines
from python.kernel.write_plan import WritePlan, digest_of

TOOL = "write_preview"
RES = "res://"


def read_texts(ctx, analysis):
    """Тексты, стиль переводов строк и хеши затронутых файлов.

    Читается `read_raw` (байты как есть): только по байтам видно, был файл
    CRLF или LF, — текстовое чтение через universal newlines эту разницу
    скрывает. Смещения шагов считаются в нормализованном тексте, а хеш
    «до правки» — по сырым байтам (контракт `expected`, ADR-0005): иначе
    stale-check части 2 сравнивал бы разные вещи.
    """
    fs = ctx.port("fs")
    texts, newlines, expected = {}, {}, {}
    for path in sorted({usage["path"] for usage in analysis["usages"]}):
        try:
            raw = fs.read_raw(path[len(RES):])
        except OSError as exc:
            raise AppError("not_found", "файл %s исчез во время предпросмотра" % path,
                           hint=str(exc)) from None
        newlines[path] = "crlf" if b"\r\n" in raw else "lf"
        texts[path] = normalize_newlines(raw.decode("utf-8-sig", "replace"))
        expected[path] = hashlib.sha256(raw).hexdigest()
    return texts, newlines, expected


def save(ctx, request, compiled, texts, expected):
    """`DRAFT → PREPARED`: digest по входу, план целиком в журнал, ответ клиенту."""
    steps = tuple(compiled["steps"])
    targets = {step.target for step in steps}
    expected = {path: sha for path, sha in expected.items() if path in targets}
    digest = digest_of(request["kind"], request["declaration"],
                       request["old_name"], request["new_name"],
                       request["mode"], request["allow_unverified"], steps,
                       expected)
    plan = WritePlan(plan_id=new_id("plan"), digest=digest, steps=steps,
                     expected=expected)
    ctx.port("journal").write_prepared(plan.as_dict(), detail={"tool": TOOL})
    return {
        "plan_id": plan.plan_id, "digest": digest, "state": plan.state,
        "kind": request["kind"], "old_name": request["old_name"],
        "new_name": request["new_name"], "declaration": request["declaration"],
        "mode": request["mode"], "allow_unverified": request["allow_unverified"],
        "steps_count": len(steps),
        "steps": [step.as_dict() for step in steps],
        "affected_paths": [step.target for step in steps],
        "skipped_usages": compiled["skipped_usages"], "risks": compiled["risks"],
        "diffs": _diffs(steps, texts), "stats": compiled["stats"],
        "confirm_ttl": plan.confirm_ttl,
    }


def _diffs(steps, texts):
    """Диффы из наших смещений: то же, что применит часть 2."""
    patches = []
    for step in steps:
        text = texts[step.target]
        try:
            new_text = diff.apply_edits(text, step.payload["edits"])
        except ValueError as exc:
            raise AppError("internal", "правки не сходятся: %s" % exc) from None
        patches.append({"path": step.target,
                        "patch": diff.unified(step.target[len(RES):], text, new_text)})
    return patches
