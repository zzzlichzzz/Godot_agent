"""C.20 IO orchestration: confirm → PREPARED → shared write_apply funnel."""
import hashlib
import json

from python.kernel.errors import AppError
from python.kernel.ids import new_id
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.schema import validate
from python.kernel.write_plan import WritePlan, canonical_json, digest_of

from .domain import apply, arch, core, inventory, plan, refs, walk
from .tools_split_apply import APPLY_ARGS


def call(args, ctx):
    """Regenerate private texts, preflight every target, then enter the WAL."""
    if validate(args, APPLY_ARGS):
        raise AppError("invalid_input", "укажите path и результат split_plan")
    rel, public = apply.request(args)
    reason = ctx.path_policy.deny_reason(rel)
    if reason:
        raise AppError("denied", reason)
    fs = ctx.port("fs")
    if not fs.is_file(rel):
        raise AppError("not_found", "файл-донор исчез: %s" % public["donor"])
    from .app import _addon_root, _sources
    root = _addon_root(fs, rel)
    prefix = root + "/" if root else ""
    donor = rel[len(prefix):]
    try:
        raw = fs.read_raw(rel)
    except FileNotFoundError:
        raise AppError("not_found", "файл-донор исчез: %s" % donor) from None
    if len(raw) > READ_TEXT_MAX_BYTES:
        raise AppError("invalid_input", "файл больше лимита чтения")
    source = inventory.decode(raw)
    if not apply.donor_matches(source, public):
        raise AppError("stale_plan", "файл-донор изменился после plan_split: %s" % donor)
    paths = fs.list_files()
    info = inventory.file_inventory(source)
    map_data = _map(fs, prefix, ctx.path_policy)
    index = arch.name_index(_sources(fs, paths, prefix, ctx.path_policy,
                                     donor, raw, arch.eligible)) if map_data else {}
    prepared = plan.plan_split(donor, source, apply.groups_of(public),
                               public["target_lines"], inventory=info,
                               map_data=map_data, index=index, occupied=())
    base = donor.rsplit("/", 1)[-1]
    scan = refs.scan(donor, walk.stem(base), base,
                     _sources(fs, paths, prefix, ctx.path_policy, donor, raw))
    core.finish(prepared, donor, walk.stem(base), scan)
    apply.confirm(public, prepared, donor)
    for module in prepared["modules"]:
        if fs.exists(prefix + module["rel"]):
            raise AppError("stale_plan", "целевой файл уже существует: %s"
                           % module["rel"])
    steps = apply.steps(prepared, raw, prefix)
    expected = {step.target: "" for step in steps if step.op == "create"}
    expected["res://" + rel] = hashlib.sha256(raw).hexdigest()
    declaration = canonical_json({"path": args["path"], "plan": public})
    digest = digest_of("split_apply", declaration, "", "", "split", False,
                       steps, expected)
    write_plan = WritePlan(new_id("plan"), digest, steps, expected)
    ctx.port("journal").write_prepared(write_plan.as_dict(),
                                        detail={"tool": "split_apply"})
    report = ctx.call_tool("write_apply", {"plan_id": write_plan.plan_id,
                                            "digest": digest})
    return apply.result(prepared, report["receipts"])


def _map(fs, prefix, policy):
    rel = prefix + "docs/architecture_map.json"
    try:
        raw = None if policy.deny_reason(rel) else json.loads(
            fs.read_raw(rel).decode("utf-8-sig"))
    except (OSError, ValueError):
        raw = None
    return arch.load_map(raw)
