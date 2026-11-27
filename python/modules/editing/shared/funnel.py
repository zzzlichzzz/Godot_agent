"""Shared validate/preflight → backup → intent → effect → receipt → inverse.

All project effects and their recovery use this funnel (ADR-0005/0016).
Filesystem IO is supplied by ports; no second journal or executor exists.
"""
from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel

from . import plan_log, script_edits, directory_steps


def guard_path(ctx, rel):
    protected = rel == "plugin.cfg" or rel.endswith("/plugin.cfg")
    reason = ("plugin.cfg защищён" if protected else
              ctx.path_policy.deny_reason(rel) if ctx.path_policy else "")
    if reason:
        raise AppError("denied", "запись в %s закрыта: %s" % (rel, reason),
                       details={"path": rel, "reason": reason})
    return rel


def guard_transfer(ctx, src, dest):
    """Operation-aware policy; generic guard_path deliberately stays unchanged."""
    policy = ctx.path_policy
    agent = (getattr(policy, "_agent_rel", "") or "").casefold()
    for rel in (src, dest):
        path = normalize_rel(rel[6:] if isinstance(rel, str) and rel.startswith("res://") else rel)
        lower = (path or "").casefold()
        protected = (not path or lower == "project.godot" or
                     lower.split("/")[0] in ("addons", ".agent_history") or
                     (agent and (lower == agent or lower.startswith(agent + "/")
                                 or agent.startswith(lower + "/"))))
        reason = "transfer защищён" if protected else policy.deny_reason(path) if policy else ""
        if reason:
            raise AppError("denied", "перенос %s закрыт: %s" % (rel, reason),
                           details={"path": rel, "reason": reason})
    return src, dest


def expected_of(plan, target):
    if target not in (plan.get("expected") or {}):
        raise AppError("stale_plan", "в плане нет хеша файла %s" % target,
                       hint="План повреждён: постройте его заново")
    return plan["expected"][target]


def verify_current(writer, plan, target, missing_kind="stale_plan"):
    try:
        raw = writer.read_raw(script_edits.rel_of(target))
    except OSError:
        raise AppError(missing_kind, "файл %s недоступен" % target,
                       details={"path": target}) from None
    if script_edits.sha256(raw) != expected_of(plan, target):
        raise AppError("stale_plan", "файл изменился после предпросмотра: %s" % target,
                       details={"path": target}, hint="Постройте план заново (`write_preview`)")
    return raw


def verify_absent(writer, plan, target):
    if expected_of(plan, target) != "":
        raise AppError("invalid_input", "create требует absent-sentinel: %s" % target)
    if writer.exists(script_edits.rel_of(target)):
        raise AppError("stale_plan", "целевой файл уже существует: %s" % target,
                       details={"path": target})


def _raw(writer, target):
    rel = script_edits.rel_of(target)
    return writer.read_raw(rel) if writer.exists(rel) and writer.is_file(rel) else None


def _case_identity(writer, src, dest):
    return (src != dest and src.casefold() == dest.casefold()
            and writer.same_file(script_edits.rel_of(src), script_edits.rel_of(dest)))


def _dir_case(writer, step):
    src, dest = step["target"], (step.get("payload") or {}).get("dest")
    a, b = script_edits.rel_of(src), script_edits.rel_of(dest)
    if (a == b or a.casefold() != b.casefold() or step.get("expected_hash") != ""
            or not writer.same_directory(a, b)):
        raise AppError("invalid_input", "dir_case требует один case-only каталог")
    return a, b


def preflight(ctx, plan):
    """Validate initial hashes/absence and simulate every dependent post-state."""
    writer, steps = ctx.port("writer"), plan.get("steps") or ()
    targets, transfers, directories, deletions = set(), {}, set(), set()
    for index, step in enumerate(steps):
        target, op = step.get("target"), step.get("op")
        if target in targets or op not in ("create", "delete", "script_edit", "move", "replace_raw", "dir_case", "mkdir"):
            raise AppError("invalid_input", "некорректная файловая операция")
        targets.add(target)
        rel = script_edits.rel_of(target)
        if op in ("move", "dir_case"):
            dest = (step.get("payload") or {}).get("dest")
            guard_transfer(ctx, rel, script_edits.rel_of(dest))
            transfers[dest] = target
            if op == "dir_case":
                if index != len(steps) - 1:
                    raise AppError("invalid_input", "dir_case должен быть последним")
                _dir_case(writer, step)
                directories.update((target, dest))
        else:
            guard_path(ctx, rel)
            if op == "delete":
                deletions.add(target)
    shadow = {}
    for target, expected in (plan.get("expected") or {}).items():
        rel = script_edits.rel_of(target)
        if target in directories:
            if expected != "":
                raise AppError("invalid_input", "dir_case требует пустой expected")
            continue
        raw = _raw(writer, target)
        if raw is None and target in deletions:
            kind = "invalid_input" if writer.exists(rel) else "not_found"
            raise AppError(kind, "delete требует существующий файл: %s" % target)
        case = target in transfers and _case_identity(writer, transfers[target], target)
        if expected == "":
            if writer.exists(rel) and not case:
                raise AppError("stale_plan", "цель уже существует: %s" % target)
        elif raw is None or script_edits.sha256(raw) != expected:
            raise AppError("stale_plan", "файл изменился после плана: %s" % target)
        shadow[target] = raw
    for step in steps:
        target, op = step["target"], step["op"]
        expected_of(plan, target)
        if op == "mkdir":
            if shadow.get(target) is not None or step.get('expected_hash')!='' or step.get('compensates')!='rmdir':
                raise AppError('invalid_input','mkdir требует absent/rmdir')
            continue
        if op == "dir_case":
            expected_of(plan, step["payload"]["dest"])
            continue
        raw = shadow.get(target)
        if op == "move":
            dest = step["payload"]["dest"]
            expected_of(plan, dest)
            anchor = step["payload"].get("already_moved", False)
            if not isinstance(anchor, bool):
                raise AppError("invalid_input", "already_moved должен быть bool")
            if anchor:
                raw = shadow.get(dest)
                if shadow.get(target) is not None:
                    raise AppError("stale_plan", "external source уже существует")
            elif shadow.get(dest) is not None and not _case_identity(writer, target, dest):
                raise AppError("stale_plan", "цель уже существует: %s" % dest)
            if raw is None or script_edits.sha256(raw) != step.get("expected_hash"):
                raise AppError("stale_plan", "источник переноса изменился: %s" % target)
            shadow[target], shadow[dest] = None, raw
        else:
            if op == "create" and raw is not None:
                raise AppError("stale_plan", "create target занят: %s" % target)
            shadow[target] = script_edits.apply_step(raw, step)


def execute(ctx, plan, build_result):
    """One executor. Caller owns the project lock continuously through COMMITTED."""
    preflight(ctx, plan)
    journal, plan_id = ctx.port("journal"), plan["plan_id"]
    entry_id = plan_log.entry_id_of(plan_id, plan_log.next_index(journal.read(plan_id)))
    started = ctx.clock.now_iso()
    journal.append(plan_id, {"state": "APPLYING", "entry_id": entry_id,
                            "digest": plan["digest"], "started_at": started})
    receipts = []
    try:
        for index, step in enumerate(plan["steps"], start=1):
            receipts.append(apply_file_step(ctx, plan, plan_id, entry_id, index, step))
    except Exception as exc:
        abort_plan(ctx, plan, plan_id, entry_id, receipts,
                   "step_failed:%s" % getattr(exc, "kind", type(exc).__name__))
        if isinstance(exc, AppError):
            raise exc
        raise AppError("internal", "сбой записи: %s" % type(exc).__name__,
                       hint="Проверьте права и место на диске") from None
    finished = ctx.clock.now_iso()
    result = build_result(plan, entry_id, receipts, started, finished)
    journal.append(plan_id, {"state": "COMMITTED", "entry_id": entry_id,
                            "result": result, "finished_at": finished})
    return result


def apply_file_step(ctx, plan, plan_id, entry_id, index, step):
    """Durable backup → durable intent → effect → durable receipt, for every op."""
    writer, journal, backups = ctx.port("writer"), ctx.port("journal"), ctx.port("backups")
    target, op = step["target"], step["op"]
    rel, dest, token, raw, new_raw = script_edits.rel_of(target), "", "", None, None
    directory_steps.prove_parents(ctx,plan,entry_id,target)
    if op == 'mkdir':
        guard_path(ctx,rel)
        return directory_steps.apply(ctx,plan,plan_id,entry_id,step)
    if op in ("move", "dir_case"):
        dest = step["payload"]["dest"]
        directory_steps.prove_parents(ctx,plan,entry_id,dest)
        guard_transfer(ctx, rel, script_edits.rel_of(dest))
        if op == "dir_case":
            _dir_case(writer, step)
        else:
            anchor = step["payload"].get("already_moved", False)
            if anchor:
                if writer.exists(rel):
                    raise AppError("stale_plan", "external source уже существует")
            elif writer.exists(script_edits.rel_of(dest)) and not _case_identity(writer, target, dest):
                raise AppError("stale_plan", "цель переноса уже существует: %s" % dest)
            raw = verify_current(writer, {"expected": {(dest if anchor else target): step["expected_hash"]}},
                                 dest if anchor else target)
    else:
        guard_path(ctx, rel)
        if op == "create":
            verify_absent(writer, plan, target)
        else:
            expected = step["expected_hash"] if op == "replace_raw" else expected_of(plan, target)
            raw = verify_current(writer, {"expected": {target: expected}}, target,
                                 "not_found" if op == "delete" else "stale_plan")
        new_raw = script_edits.apply_step(raw, step)
    expected = script_edits.sha256(raw) if raw is not None else ""
    applied = (expected if op == "move" else
               script_edits.sha256(new_raw) if new_raw is not None else "")
    if raw is not None:
        token = backups.put(plan_id, index, raw)
    intent = {"state": "EFFECT_INTENT", "entry_id": entry_id, "op": op,
              "target": target, "dest": dest, "expected_hash": expected,
              "applied_hash": applied, "undo_token": token}
    journal.append(plan_id, intent)
    if op == "move":
        if not step["payload"].get("already_moved", False):
            writer.move(rel, script_edits.rel_of(dest))
    elif op == "dir_case":
        writer.rename_dir_case(rel, script_edits.rel_of(dest))
    elif op == "create":
        writer.create(rel, new_raw)
    elif op == "delete":
        writer.delete(rel)
    else:
        writer.write_raw(rel, new_raw)
    receipt = {"step_id": target, "applied_hash": applied, "undo_token": token}
    journal.append(plan_id, {"state": "RECEIPT", "entry_id": entry_id, "receipt": receipt})
    return receipt


def effects_of(entries, entry_id):
    """Ordered receipt/proof pairs; pending intents use the same inverse logic."""
    rows = {}
    for record in entries:
        if record.get("entry_id") != entry_id:
            continue
        if record.get("state") == "EFFECT_INTENT":
            rows[record["target"]] = ({"step_id": record["target"],
                "applied_hash": record["applied_hash"], "undo_token": record["undo_token"]}, True)
        elif record.get("state") == "RECEIPT":
            receipt = record["receipt"]
            rows[receipt["step_id"]] = (receipt, False)
    return list(rows.values())


def intent_unstarted(writer, plan, target):
    step = next(item for item in plan["steps"] if item["target"] == target)
    if step['op']=='mkdir':return directory_steps.pending(writer,target)
    if step["op"] in ("move", "dir_case"):
        if step["payload"].get("already_moved", False):
            return False
        dest = step["payload"]["dest"]
        if _case_identity(writer, target, dest):
            return writer.actual_rel(script_edits.rel_of(target)) == script_edits.rel_of(target)
        if writer.exists(script_edits.rel_of(dest)):
            return False
    raw = _raw(writer, target)
    expected = restore_expected(plan, target)
    return (raw is None and expected == "" and not writer.exists(script_edits.rel_of(target))
            or raw is not None and script_edits.sha256(raw) == expected)


def abort_plan(ctx, plan, plan_id, entry_id, receipts, reason):
    journal, writer, backups = ctx.port("journal"), ctx.port("writer"), ctx.port("backups")
    journal.append(plan_id, {"state": "ROLLING_BACK", "entry_id": entry_id, "reason": reason})
    for receipt, pending in reversed(effects_of(journal.read(plan_id), entry_id)):
        target = receipt["step_id"]
        if pending and intent_unstarted(writer, plan, target):
            continue
        restored = restore(writer, backups, plan, target, receipt["undo_token"], receipt["applied_hash"],
                           journal.read(plan_id),entry_id)
        journal.append(plan_id, {"state": "RESTORED", "entry_id": entry_id,
                                 "path": target, "hash": restored})
    journal.append(plan_id, {"state": "ROLLED_BACK", "entry_id": entry_id, "reason": reason})


def restore_expected(plan, target):
    step = next((item for item in plan["steps"] if item["target"] == target), {})
    return step["expected_hash"] if step.get("op") in ("move", "replace_raw") else expected_of(plan, target)


def _conflict(target, reason="post_state_mismatch"):
    raise AppError("conflict", "состояние восстановления изменено: %s" % target,
                   details={"reason": reason, "path": target})


def _backup(backups, token, expected, target):
    try:
        data = backups.get(token)
    except OSError:
        _conflict(target, "backup_missing")
    if script_edits.sha256(data) != expected:
        _conflict(target, "backup_mismatch")
    return data


def restore(writer, backups, plan, target, undo_token, applied_hash="", entries=(), entry_id=""):
    """Prove pre/post state, inverse only our bytes, then prove exact restoration."""
    rel = script_edits.rel_of(target)
    step = next((item for item in plan.get("steps") or () if item["target"] == target), {})
    op, expected = step.get("op"), restore_expected(plan, target)
    directory_steps.prove(writer,plan,entries,entry_id,target)
    if op == "move":directory_steps.prove(writer,plan,entries,entry_id,step["payload"]["dest"])
    if op=='mkdir':return directory_steps.restore(writer,target,undo_token,applied_hash)
    if op == "dir_case":
        dest = script_edits.rel_of(step["payload"]["dest"])
        if not writer.same_directory(rel, dest):
            _conflict(target)
        writer.rename_dir_case(dest, rel)
        if writer.actual_rel(rel) != rel:
            _conflict(target)
        return ""
    if op == "move":
        dest = step["payload"]["dest"]
        case = _case_identity(writer, target, dest)
        if intent_unstarted(writer, plan, target) and not case:
            return expected
        if step.get("compensates") != "move":
            _conflict(target, "no_compensation")
        raw = _raw(writer, dest)
        if raw is None or script_edits.sha256(raw) != applied_hash:
            _conflict(dest)
        if writer.exists(rel) and not case:
            _conflict(target)
        _backup(backups, undo_token, expected, target)
        writer.move(script_edits.rel_of(dest), rel)
        if script_edits.sha256(writer.read_raw(rel)) != expected:
            _conflict(target)
        return expected
    raw = _raw(writer, target)
    if writer.exists(rel) and raw is None:
        _conflict(target)
    current = script_edits.sha256(raw) if raw is not None else ""
    if op == "create" and step.get("compensates") == "delete":
        if raw is None:
            return ""
        if not applied_hash or current != applied_hash:
            _conflict(target)
        writer.delete(rel)
        if writer.exists(rel):
            _conflict(target)
        return ""
    if current == expected:
        return expected
    if current != applied_hash:
        _conflict(target)
    data = _backup(backups, undo_token, expected, target)
    if op == "delete" and raw is None:
        writer.create(rel, data)
    else:
        writer.write_raw(rel, data)
    restored = script_edits.sha256(writer.read_raw(rel))
    if restored != expected:
        raise AppError("internal", "восстановление не совпало с expected: %s" % target)
    return restored
