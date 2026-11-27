# tools/probe.py - вызвать одну механику нового агента как клиент (R-18).
# Использование: python tools/probe.py <tool> --args '{"query": "..."}' [--project <путь>]
#                python tools/probe.py <tool> --args-file <файл.json> [--project <путь>]
# Печатает ответ агента как JSON: {"ok": true, "result": ...} либо
# {"ok": false, "kind": "...", "message": "...", "hint": "..."}.
# Корень проекта: --project, иначе GODOT_AGENT_PROJECT, иначе текущий каталог.
# `--args-file` нужен там, где оболочка съедает кавычки в JSON (PowerShell 5.1
# разбивает аргумент по пробелу внутри строки) — содержимое файла то же самое.

import base64
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True


def file_refactor_context(project, state_dir=None):
    """Internal client adapter; no registered MCP tool or second executor."""
    from python.kernel.errors import AppError
    from python.kernel.paths import PathPolicy
    from python.runtime.bootstrap import build_agent, default_ports
    from python.runtime.context import ModuleContext
    ports = default_ports(str(project), "test", state_dir)
    agent = build_agent(str(project), "test", ports=ports)

    def call_tool(tool, args):
        answer = agent.call(tool, args)
        if not answer["ok"]:
            raise AppError(answer["kind"], answer["message"], hint=answer.get("hint", ""),
                           details=answer.get("details", {}))
        return answer["result"]

    ctx = ModuleContext("test", ports=ports, path_policy=PathPolicy(str(project), agent_dir=str(ROOT)),
                        call_tool=call_tool)
    return agent, ctx, ports


def file_refactor_client(project, args, operation="prepare", state_dir=None):
    from python.kernel import result
    from python.kernel.errors import AppError
    from python.modules.editing.file_refactor.module import MODULE
    if operation not in ("prepare", "apply", "sync"):
        return result.fail(AppError("invalid_input", "неизвестная внутренняя операция"))
    _agent, ctx, _ports = file_refactor_context(project, state_dir)
    try:
        return result.ok(MODULE.entrypoints[operation](args, ctx))
    except AppError as exc:
        return result.fail(exc)
    except ImportError:
        if operation != "sync":
            raise
        return result.fail(AppError("unavailable", "external-sync недоступен"))


def _tree(project):
    return {p.relative_to(project).as_posix(): p.read_bytes()
            for p in project.rglob("*") if p.is_file()}


def _safety_answer(record, project, state):
    from python.kernel.write_plan import Step, WritePlan
    from python.modules.editing.rollback import recover
    agent, _ctx, ports = file_refactor_context(project, state)
    step = Step("create", record["target"], record["payload"], "", "delete")
    plan = WritePlan("plan_safety", "digest_safety", (step,), {record["target"]: ""})
    ports["journal"].write_prepared(plan.as_dict(), detail={"tool": "file_refactor"})
    append = ports["journal"].append

    class Crash(BaseException):
        pass

    def no_receipt(plan_id, row):
        if row.get("state") == "RECEIPT":
            raise Crash()
        append(plan_id, row)

    ports["journal"].append = no_receipt
    try:
        agent.call("write_apply", {"plan_id": plan.plan_id, "digest": plan.digest})
    except Crash:
        pass
    finally:
        ports["journal"].append = append
    rows = ports["journal"].read(plan.plan_id)
    effect = (project / record["target"][6:]).read_bytes()
    proof = {"intent_before_effect": rows[-1]["state"] == "EFFECT_INTENT",
             "effect_bytes_b64": base64.b64encode(effect).decode("ascii"),
             "receipt_absent": not any(row["state"] == "RECEIPT" for row in rows),
             "recovery": recover(ports)[0]["action"], "tree_unchanged": _tree(project) == {}}
    return {"ok": True, "result": proof}


def _sync_answer(record, project, state):
    """Actual sync and raw inverse proof; an absent service cannot pass its corpus."""
    from python.kernel import result
    from python.kernel.errors import AppError
    from python.modules.editing.file_refactor.module import MODULE
    agent, ctx, ports = file_refactor_context(project, state)
    initial = _tree(project)
    try:
        answer = MODULE.entrypoints["sync"](record["input"], ctx)
    except AppError as exc:
        assert _tree(project) == initial
        return result.fail(exc)
    except ImportError:
        assert _tree(project) == initial
        return result.fail(AppError("unavailable", "external-sync недоступен"))
    expected = {rel: base64.b64decode(data["$bytes_base64"], validate=True)
                for rel, data in record["native_effects"].items()}
    assert _tree(project) == expected, "sync effects differ from native raw bytes"
    completed = record["id"] == "sync-leaf-case"
    assert answer["anchor_already_completed"] is completed
    assert isinstance(answer["patches"], list) and isinstance(answer["moved"], list)
    if answer["plan_id"] is None:
        assert answer["patches"] == answer["moved"] == [] and answer["entry_id"] is None
        assert ports["journal"].plan_ids() == [], "D13 no-op wrote WAL"
    else:
        assert answer["entry_id"].startswith(answer["plan_id"] + "#")
        entries = ports["journal"].read(answer["plan_id"])
        steps = entries[0]["plan"]["steps"]
        assert steps, "D13 zero-step plan created"
        if completed:
            assert all(step["op"] == "replace_raw" for step in steps), "completed alias has anchor receipt"
    if answer["entry_id"]:
        rollback = agent.call("write_rollback", {"entry_id": answer["entry_id"]})
        assert rollback["ok"], rollback
        original = {rel: base64.b64decode(data["bytes_b64"], validate=True)
                    for rel, data in record["original"].items()}
        if completed:
            # D13.2: patches roll back; external case-only file/UID names do not.
            old, new = record["input"]["old_path"][6:], record["input"]["new_path"][6:]
            original = {new + rel[len(old):] if rel == old or rel == old + ".uid" else rel: raw
                        for rel, raw in original.items()}
        assert _tree(project) == original, "sync inverse lost raw bytes or actual names"
    projected = {key: value for key, value in answer.items() if key not in ("patches", "moved", "plan_id")}
    projected["entry_id"] = "<ENTRY>" if answer["entry_id"] else None
    projected["changed_paths"] = sorted(projected["changed_paths"])
    return result.ok(projected)


def file_refactor_corpus_answer(record):
    """Native prepare/raw-byte proof plus the explicitly approved D9 casing effect."""
    from python.kernel import result
    from python.kernel.errors import AppError
    from python.kernel.paths import normalize_rel
    from python.modules.editing.file_refactor.module import MODULE
    with tempfile.TemporaryDirectory(prefix="c22-corpus-") as work:
        project, state = Path(work) / "project", str(Path(work) / "state")
        project.mkdir()
        if record.get("oracle") == "our safety behaviour, not native parity":
            return _safety_answer(record, project, state)
        for rel in record["fixture"]["dirs"]:
            assert normalize_rel(rel) == rel
            (project / rel).mkdir(parents=True, exist_ok=True)
        for rel, data in record["fixture"]["files"].items():
            assert normalize_rel(rel) == rel
            path = project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(data["bytes_b64"], validate=True))
        if record.get("scenario") == "external_sync":
            return _sync_answer(record, project, state)
        initial = _tree(project)
        agent, ctx, _ports = file_refactor_context(project, state)
        try:
            prepared = MODULE.entrypoints["prepare"](record["input"], ctx)
        except AppError as exc:
            assert _tree(project) == initial
            return result.fail(exc)
        assert _tree(project) == initial, "prepare wrote project bytes"
        answer = {key: value for key, value in prepared.items()
                  if key not in ("plan_id", "digest", "state", "steps_count", "confirm_ttl")}
        applied = MODULE.entrypoints["apply"](prepared, ctx)
        oracle = record.get("native_result") or {}
        expected = dict(initial)
        old, new = record["input"]["old_path"][6:], record["input"]["new_path"][6:]
        case_old, case_new = ((old, new) if oracle.get("is_directory") else
                              (old.rpartition("/")[0], new.rpartition("/")[0]))
        if case_old != case_new and case_old.casefold() == case_new.casefold():
            expected = {case_new + rel[len(case_old):] if rel.startswith(case_old + "/") else rel: data
                        for rel, data in expected.items()}
        for row in oracle.get("files", []):
            src, dest = row["path"][6:], row.get("dest", row["path"])[6:]
            current_src = (case_new + src[len(case_old):] if case_old != case_new
                           and case_old.casefold() == case_new.casefold()
                           and src.startswith(case_old + "/") else src)
            if src != dest:
                expected.pop(current_src, None)
                if src + ".uid" in initial:
                    expected.pop(current_src + ".uid", None)
                    expected[dest + ".uid"] = initial[src + ".uid"]
            expected[dest] = base64.b64decode(row["after_bytes"]["$bytes_base64"], validate=True)
        assert _tree(project) == expected, "effects differ from native prepared raw bytes"
        rollback = agent.call("write_rollback", {"entry_id": applied["entry_id"]})
        assert rollback["ok"], rollback
        assert _tree(project) == initial, "inverse did not restore exact paths/raw bytes"
        return {"ok": True, "result": answer}


def resource_client(project, value, operation="prepare", kwargs=None, state_dir=None):
    """Internal client, not Agent.call dispatch; only the module's fixed entrypoints."""
    from python.kernel import result
    from python.kernel.errors import AppError
    from python.kernel.paths import PathPolicy
    from python.modules.editing.resource_ops.module import MODULE
    from python.runtime.bootstrap import default_ports
    from python.runtime.context import ModuleContext
    if operation not in MODULE.entrypoints:
        return result.fail(AppError("invalid_input", "неизвестная внутренняя операция"))
    ctx = ModuleContext("test", ports=default_ports(str(project), "test", state_dir),
                        path_policy=PathPolicy(str(project), agent_dir=str(ROOT)))
    try:
        if operation == "apply":
            from python.protocol.validation import validate_args
            from python.modules.editing.write_apply.tools import TOOLS
            validate_args(TOOLS[0], value)
            _, ctx, _ = file_refactor_context(project, state_dir)
        answer = MODULE.entrypoints[operation](value, ctx, **(kwargs or {}))
        if operation == "normalize_action":
            answer = {"action": answer[0], "target": "res://" + answer[1]}
        return result.ok(answer)
    except AppError as exc:
        return result.fail(exc)


def resource_corpus_answer(record):
    """Full prepare/schema comparison plus exact raw tree non-effect proof."""
    import shutil
    call = record["internal_call"]
    assert call["module_id"] == "editing.resource_ops"
    fixture_name = record["fixture"]
    assert isinstance(fixture_name, str) and Path(fixture_name).name == fixture_name and fixture_name not in (".", "..")
    fixture = ROOT / "fixtures/corpus/editing/resource_ops/projects" / fixture_name
    with tempfile.TemporaryDirectory(prefix="c23-corpus-") as work:
        project = Path(work) / "project"
        shutil.copytree(fixture, project)
        if record.get("resource_write_scenario") is not None:
            return _resource_write_answer(record, project, Path(work) / "state")
        before = _tree(project)
        answer = resource_client(project, record["input"], call["entrypoint"], record.get("kwargs"))
        assert _tree(project) == before, "resource prepare wrote project bytes"
        if answer["ok"] and call["entrypoint"] in ("prepare", "public_prepared"):
            import re
            if call["entrypoint"] == "prepare":
                assert re.fullmatch("[0-9a-f]{32}", answer["result"]["action_id"])
            answer["result"]["action_id"] = "<ACTION_ID>"
        return answer


def _resource_write_answer(record, project, state):
    """C24 internal fixed scenario: real client/WAL and raw-byte effect assertions."""
    import hashlib
    scenario = record["resource_write_scenario"]
    assert record["internal_call"]["entrypoint"] == "prepare_write"
    for name, encoded in scenario.get("seed_bytes", {}).items():
        assert name in ("data.tres", "old.tres", "new.tres")
        (project / name).write_bytes(base64.b64decode(encoded, validate=True))
    before = _tree(project)
    agent, ctx, _ = file_refactor_context(project, state)
    lock = ctx.port("lock")
    if scenario.get("lock_busy"):
        assert lock.acquire()
    try:
        prepared = resource_client(project, record["input"], "prepare_write", record.get("kwargs"), state)
    finally:
        if scenario.get("lock_busy"):
            lock.release()
    assert _tree(project) == before, "resource preparation changed project"
    if not prepared["ok"]:
        assert ctx.port("journal").plan_ids() == [], "refusal created a plan"
        return prepared
    result = prepared["result"]
    plan = ctx.port("journal").read(result["plan_id"])[0]["plan"]
    assert len(plan["steps"]) == 1 and plan["steps"][0]["op"] == "replace_raw"
    target = result["target"][6:]
    assert target in before
    for name, encoded in scenario.get("change_before_apply", {}).items():
        assert name in ("data.tres", "old.tres", "new.tres")
        (project / name).write_bytes(base64.b64decode(encoded, validate=True))
    current = _tree(project)
    request = {key: result[key] for key in ("plan_id", "digest")}
    applied = resource_client(project, request, "apply", state_dir=state)
    if not applied["ok"]:
        assert _tree(project) == current, "refused apply changed project"
        return applied
    after = _tree(project)
    assert (project / target).read_bytes() == base64.b64decode(scenario["after_bytes_b64"], validate=True)
    assert {k: v for k, v in after.items() if k != target} == {k: v for k, v in before.items() if k != target}
    repeat_kind = None
    if scenario.get("repeat"):
        again = resource_client(project, request, "apply", state_dir=state)
        assert not again["ok"] and again["kind"] == "stale_plan" and _tree(project) == after
        repeat_kind = again["kind"]
    rolled = agent.call("write_rollback", {"entry_id": applied["result"]["entry_id"]})
    assert rolled["ok"] and _tree(project) == before, "rollback was not raw-byte exact"
    return {"ok": True, "result": {"target": result["target"], "before_hash": hashlib.sha256(before[target]).hexdigest(),
            "after_hash": hashlib.sha256(after[target]).hexdigest(), "steps": 1, "op": "replace_raw", "rollback_exact": True,
            "repeat_kind": repeat_kind}}


def project_text_client(project, args, feature="tree", policy=None, agent_dir=None, state_dir=None):
    from python.kernel import errors, paths, result
    from python.protocol.registry import Registry
    from python.runtime.bootstrap import _register, default_ports
    from python.runtime.module_loader import load_one
    assert feature in ("read", "tree")
    item = load_one(ROOT / "python/modules/project_text" / feature / "module.py")
    registry = Registry()
    spec = item.spec
    context = _register(registry, item,
                        "test", default_ports(str(project), "test", state_dir),
                        paths.PathPolicy(str(project), agent_dir=str(agent_dir or ROOT), **(policy or {})), {})
    assert context is not None and not registry.disabled()
    try:
        return result.ok(spec.entrypoints["build"](args, context) if feature == "tree" else spec.entrypoints["call"]("read", args, context))
    except errors.AppError as exc:
        return result.fail(exc)

def project_text_corpus_answer(record):
    from python.kernel.paths import normalize_rel
    call = record["internal_call"]
    assert call["module_id"] in ("project_text.read", "project_text.tree")
    with tempfile.TemporaryDirectory(prefix="c25-corpus-") as work:
        project = Path(work) / "project"
        project.mkdir()
        for rel in record["fixture"]["dirs"]:
            assert normalize_rel(rel) == rel
            (project / rel).mkdir(parents=True, exist_ok=True)
        for rel, value in record["fixture"]["files"].items():
            assert normalize_rel(rel) == rel
            path = project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = ((value["text"] * value.get("repeat", 1)).encode("utf-8") if "text" in value else base64.b64decode(value["b64"], validate=True))
            path.write_bytes(raw)
        before = _tree(project)
        dirs = sorted(p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_dir())
        argv = (project, record["args"], call["module_id"].split(".")[1], record["policy"], project / record["agent_rel"], str(Path(work) / "state"))
        answer = project_text_client(*argv)
        assert project_text_client(*argv) == answer, "read/tree repeat differed"
        assert _tree(project) == before, "read/tree changed raw bytes"
        assert dirs == sorted(p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_dir())
        import re
        assert not re.search(r'"path"\s*:\s*"(?!res://)', json.dumps(answer, ensure_ascii=False)), "absolute path in response"
        return answer

def _option(argv, name):
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: probe.py <tool> --args '<json>' | --args-file <файл> "
                         "[--project <путь>]\n")
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tool = argv[1]
    args_file = _option(argv, "--args-file")
    if args_file:
        try:
            raw = Path(args_file).read_text(encoding="utf-8-sig")
        except OSError as exc:
            sys.stderr.write("probe: --args-file не читается: %s\n" % exc)
            return 2
    else:
        raw = _option(argv, "--args") or "{}"
    try:
        args = json.loads(raw)
    except ValueError as exc:
        sys.stderr.write("probe: --args не JSON: %s\n" % exc)
        return 2
    try:
        from python.runtime import bootstrap
    except ImportError:
        sys.stderr.write("probe: каркаса нет (python/runtime/bootstrap.py)\n")
        return 2
    build = getattr(bootstrap, "build_agent", None)
    if build is None:
        sys.stderr.write("probe: bootstrap.build_agent не реализован\n")
        return 2
    agent = build(project_root=_option(argv, "--project")) if tool not in ("resource_ops", "project_text.tree") else None
    answer = (project_text_client(_option(argv, "--project") or Path.cwd(), args)
              if tool == "project_text.tree" else resource_client(_option(argv, "--project") or Path.cwd(), args,
                              _option(argv, "--operation") or "prepare") if tool == "resource_ops" else
              file_refactor_client(_option(argv, "--project") or Path.cwd(), args,
                                  _option(argv, "--operation") or "prepare")
              if tool == "file_refactor" else agent.call(tool, args))
    print(json.dumps(answer, ensure_ascii=False))
    return 0 if answer.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
