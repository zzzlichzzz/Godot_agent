# tools/snapshot_diff.py - дифференциальный прогон по корпусу (R-09).
# Использование: python tools/snapshot_diff.py [<module_id>] [--json]
# Старый агент здесь не запускается и не импортируется: сравнение идёт с
# зафиксированным эталоном в fixtures/corpus/<область>/<фича>/<id>.json (R-07).
# Контракт проверки: последняя строка - JSON {"status": ..., "detail": ...}.

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.corpus_replay import corpus_routes, records, selected_folders
CORPUS_ROOT = ROOT / "fixtures" / "corpus"
FIXTURES = ROOT / "fixtures" / "projects"


def verdict(status, detail):
    print(json.dumps({"status": status, "detail": detail}, ensure_ascii=False))
    return {"ok": 0, "fail": 1, "needs_live": 2}.get(status, 2)


def corpora(base=None):
    root = Path(base or CORPUS_ROOT)
    return sorted({path.parent for path in root.glob("*/*/manifest.json")})


def cases(folder):
    if Path(folder) == CORPUS_ROOT / "editing" / "file_refactor":
        return sorted((Path(folder) / "cases").glob("*.json"))
    return [path for path in sorted(Path(folder).glob("*.json"))
            if path.name != "manifest.json"]


def file_refactor_answer(record):
    from tools.probe import file_refactor_corpus_answer
    answer = file_refactor_corpus_answer(record)
    return answer if answer.get("ok") else {key: answer[key] for key in ("ok", "kind", "message")}


def file_refactor_expected(record):
    """Only D4's approved absolute/raw omissions and lexicographic item ordering."""
    if record.get("oracle") == "our safety behaviour, not native parity":
        return {"ok": True, "result": record["expect"]}
    if record.get("scenario") == "external_sync":
        projected = dict(record["native_result"])
        projected["entry_id"] = "<ENTRY>" if projected["entry_id"] else None
        projected["changed_paths"] = sorted(projected["changed_paths"])
        projected["anchor_already_completed"] = record["id"] == "sync-leaf-case"
        if record["id"] == "sync-empty-directory":
            projected.update(entry_id=None, file_count=0)
        elif record["id"] == "sync-leaf-case":
            projected["file_count"] -= 1  # D13.2 excludes the completed file anchor.
        return {"ok": True, "result": projected}
    if not record["native_ok"]:
        error = record["native_exception"]
        text = error["text"]
        kind = {"FileNotFoundError": "not_found", "FileExistsError": "conflict"}.get(error["type"], "invalid_input")
        if error["type"] == "FileRefactorError" and any(word in text for word in ("политик", "policy", "истории")):
            kind = "denied"
        return {"ok": False, "kind": kind, "message": text}
    projected = dict(record["native_result"])
    projected["files"] = sorted(({key: value for key, value in row.items()
                                 if key not in ("absolute", "dest_absolute", "before_bytes", "after_bytes")}
                                for row in projected["files"]), key=lambda row: row["path"])
    projected["affected_paths"] = [row.get("dest", row["path"]) for row in projected["files"]]
    return {"ok": True, "result": projected}


def describe(expect, answer, tool=None):
    """Короткое расхождение: что именно не совпало, без дампа всего ответа.

    Сравнение структурное, а не по полям одной механики: у каждой фичи своя форма
    результата (`search` — matches/truncated, `functions` — names или
    functions/missing). Иначе второй инструмент «проходил» бы корпус, потому что
    его полей в ожидании просто нет.

    `tool` нужен для механик, чей живой ответ заведомо содержит случайные части
    (`write_preview`: `plan_id` новый на каждый вызов, `diffs` строятся из наших
    смещений). Их проекция сводит ответ к тому, что вообще сравнимо с эталоном.
    """
    if bool(answer.get("ok")) != bool(expect.get("ok")):
        return "ok: новый=%r эталон=%r" % (answer.get("ok"), expect.get("ok"))
    if not expect.get("ok"):
        if answer.get("kind") != expect.get("kind"):
            return "kind: новый=%r эталон=%r" % (answer.get("kind"), expect.get("kind"))
        return ""
    mine = answer.get("result")
    project = PROJECTIONS.get(tool)
    if project is not None:
        mine = project(mine)
    return _difference(mine, expect.get("result"), "")


def project_write_preview(result):
    """`write_preview` -> сравнимое ядро: без plan_id, digest и диффов."""
    steps = [{"path": step.get("target"),
              "edits": len((step.get("payload") or {}).get("edits") or ())}
             for step in result.get("steps") or ()]
    stats = result.get("stats") or {}
    return {
        "state": result.get("state"), "kind": result.get("kind"),
        "old_name": result.get("old_name"), "new_name": result.get("new_name"),
        "declaration": result.get("declaration"), "mode": result.get("mode"),
        "allow_unverified": result.get("allow_unverified"),
        "steps": steps, "steps_count": result.get("steps_count"),
        "affected_paths": result.get("affected_paths"),
        "stats": {key: stats.get(key)
                  for key in ("files", "edits", "dynamic")},
        "excluded": len([line for line in result.get("skipped_usages") or ()
                         if "снято пользователем" in line]),
    }


def project_context(result):
    """`context` -> тот же пакет, но без машинно-зависимого корня проекта.

    `sections.project.root` — абсолютный путь фикстуры, он разный на каждой машине
    и в эталоне сравнивать его нечем. Корень заменяется на `<PROJECT>`; абсолютность
    и совпадение с корнем фикстуры проверяют тесты контракта, а не корпус.
    """
    sections = dict(result.get("sections") or {})
    project = sections.get("project")
    if isinstance(project, dict) and project.get("root"):
        sections["project"] = dict(project, root="<PROJECT>")
        return dict(result, sections=sections)
    return result


def project_split_apply(result):
    """`split_apply` -> native result without random WAL receipt tokens."""
    return {key: (result or {}).get(key) for key in
            ("donor", "written", "moved", "facade_lines")}


#: Механики, чей живой ответ сравнивается не целиком (см. `describe`).
PROJECTIONS = {"write_preview": project_write_preview,
               "context": project_context,
               "split_apply": project_split_apply}



def _difference(mine, reference, path):
    if isinstance(reference, dict):
        if not isinstance(mine, dict):
            return "%s: ожидался объект" % _field(path)
        for key in sorted(set(reference) | set(mine)):
            if key not in mine:
                return "%s: нет поля (эталон %r)" % (_field(path, key),
                                                   str(reference[key])[:120])
            if key not in reference:
                return "%s: лишнее поле" % _field(path, key)
            found = _difference(mine[key], reference[key], _field(path, key))
            if found:
                return found
        return ""
    if isinstance(reference, list):
        if not isinstance(mine, list):
            return "%s: ожидался список" % _field(path)
        if len(mine) != len(reference):
            return "%s: элементов новый=%d эталон=%d" % (_field(path), len(mine),
                                                       len(reference))
        for index, (item, expected) in enumerate(zip(mine, reference)):
            found = _difference(item, expected, "%s[%d]" % (_field(path), index))
            if found:
                return found
        return ""
    same = mine == reference and isinstance(mine, bool) == isinstance(reference, bool)
    if not same:
        return "%s: новый=%r эталон=%r" % (_field(path), str(mine)[:120],
                                           str(reference)[:120])
    return ""


def _field(path, key=None):
    if key is None:
        return path or "результат"
    return "%s.%s" % (path, key) if path else str(key)


class _FailEffect:
    """Corpus-only fault adapter used to prove reverse compensation."""
    def __init__(self, writer, number):
        self._writer, self._number, self._seen = writer, int(number), 0

    def __getattr__(self, name):
        return getattr(self._writer, name)

    def _call(self, name, *args):
        self._seen += 1
        if self._seen == self._number:
            raise OSError("injected corpus write failure")
        return getattr(self._writer, name)(*args)

    def create(self, *args):
        return self._call("create", *args)

    def write_raw(self, *args):
        return self._call("write_raw", *args)

    def delete(self, *args):
        return self._call("delete", *args)


def _split_apply_answer(record, project, work):
    from python.runtime.bootstrap import build_agent, default_ports

    state = str(Path(work) / "state")
    ports = default_ports(str(project), "test", state)
    failure = (record.get("test_hook") or {}).get("writer_fails_on_effect")
    if failure:
        ports["writer"] = _FailEffect(ports["writer"], failure)
    agent = build_agent(str(project), profile="test", state_dir=state, ports=ports)
    prepared = record.get("prepare") or {}
    answer = agent.call(prepared.get("tool"), prepared.get("args") or {})
    if not answer.get("ok"):
        return answer
    setup = record.get("setup") or {}
    for rel in setup.get("delete") or ():
        (project / rel).unlink()
    for rel, text in (setup.get("write_text") or {}).items():
        (project / rel).write_text(text, encoding="utf-8")
    hook = record.get("test_hook") or {}
    from python.modules.editing.split_py import apply_flow
    native = apply_flow.plan.plan_split

    def poisoned(*args, **kwargs):
        value = native(*args, **kwargs)
        if hook.get("module_text") and value.get("modules"):
            value["modules"][0]["text"] = hook["module_text"]
            value["errors"] = []
        if hook.get("facade_text") and value.get("facade"):
            value["facade"]["text"] = hook["facade_text"]
            value["errors"] = []
        return value

    apply_flow.plan.plan_split = poisoned
    args = {"path": (record.get("args") or {}).get("path"),
            "plan": answer["result"]}
    try:
        applied = agent.call("split_apply", args)
        if record.get("scenario") == "split_plan_apply_twice" and applied.get("ok"):
            applied = agent.call("split_apply", args)
        return applied
    finally:
        apply_flow.plan.plan_split = native


def scenario_answer(record):
    """Живой прогон сценария записи на копии фикстуры.

    Корпус записи нельзя снять вызовом одного инструмента: `write_apply` требует
    `plan_id` от предпросмотра. Поэтому кейс описывает сценарий (`scenario`), а
    сравнение идёт по байтам файлов проекта — той же форме, что у эталона.
    """
    import shutil
    import tempfile

    from python.runtime.bootstrap import build_agent

    fixture = FIXTURES / str(record.get("fixture") or "rename")
    work = tempfile.mkdtemp(prefix="godot_agent_scenario_")
    project = Path(work) / "project"
    try:
        shutil.copytree(str(fixture), str(project))
        if str(record.get("scenario") or "").startswith("split_plan_apply"):
            return _split_apply_answer(record, project, work)
        agent = build_agent(project_root=str(project), profile="test",
                            state_dir=str(Path(work) / "state"))
        plan = agent.call("write_preview", {
            key: value for key, value in (record.get("args") or {}).items()
            if key != "project_root"})
        if not plan.get("ok"):
            return {"ok": False, "kind": plan.get("kind")}
        applied = agent.call("write_apply", {"plan_id": plan["result"]["plan_id"],
                                             "digest": plan["result"]["digest"]})
        if not applied.get("ok"):
            return {"ok": False, "kind": applied.get("kind")}
        if record.get("scenario") in ("preview_apply_rollback", "apply_rollback_apply"):
            done = agent.call("write_rollback",
                              {"entry_id": applied["result"]["entry_id"]})
            if not done.get("ok"):
                return {"ok": False, "kind": done.get("kind")}
            if record.get("scenario") == "apply_rollback_apply":
                again = agent.call("write_apply", {
                    "plan_id": plan["result"]["plan_id"],
                    "digest": plan["result"]["digest"]})
                if not again.get("ok"):
                    return {"ok": False, "kind": again.get("kind"),
                            "details": again.get("details")}
                return {"ok": True, "result": {"entry_id": again["result"]["entry_id"]}}
        files = {}
        for path in sorted((project / "src").rglob("*.gd")):
            rel = path.relative_to(project).as_posix()
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        # Сверяем только те файлы, которые эталон назвал ожидаемыми: у отката это
        # файлы плана (`before_bytes`), у записи — все `src/**/*.gd`.
        expected = (record.get("expect") or {}).get("result", {}).get("files") or {}
        files = {key: value for key, value in files.items() if key in expected}
        return {"ok": True, "result": {"files": files}}
    finally:
        shutil.rmtree(work, ignore_errors=True)


@corpus_routes(_difference)
def run_corpus(agent_cache, folder, only=None):
    touched, passed, failures = 0, 0, []
    for path, record in records(cases(folder)):
        case_id = record.get("id") or path.stem
        internal_refactor = folder == CORPUS_ROOT / "editing" / "file_refactor"
        tool = "file_refactor" if internal_refactor else record.get("tool")
        internal = record.get("internal_call")
        if internal:
            tool = internal["module_id"].split(".", 1)[1]
        if only and tool not in only:
            continue
        touched += 1
        if internal_refactor:
            problem = _difference(file_refactor_answer(record), file_refactor_expected(record), "")
        elif internal:
            from tools.probe import project_text_corpus_answer, resource_corpus_answer
            clients = {"resource": resource_corpus_answer, "project_text": project_text_corpus_answer}
            client = clients[internal.get("client", "resource")]
            answer = client(record)
            projected = ({key: answer[key] for key in record["expect"]}
                         if internal.get("client") == "project_text" else answer)
            problem = _difference(projected, record["expect"], "")
        elif record.get("scenario"):
            answer = scenario_answer(record)
            problem = describe(record.get("expect") or {}, answer, tool)
        else:
            fixture = FIXTURES / str(record.get("fixture") or "minimal")
            if str(fixture) not in agent_cache:
                from python.runtime.bootstrap import build_agent
                agent_cache[str(fixture)] = build_agent(project_root=fixture,
                                                        profile="headless")
            problem = describe(record.get("expect") or {},
                               agent_cache[str(fixture)].call(tool, record.get("args") or {}),
                               tool)
        if problem:
            failures.append("%s: %s" % (case_id, problem))
        else:
            passed += 1
    return touched, passed, failures


def module_tools(module_id):
    """Все инструменты модуля: у одного модуля их может быть два и больше.

    `analyze_rename` живёт в модуле `code_intel.usages` (parity строка 23),
    поэтому фильтр «только tools модуля» берётся из манифеста, а не из имени
    фичи: иначе второй инструмент молча выпадал бы из прогона.
    """
    try:
        from python.runtime.module_loader import discover
        loaded, _failed = discover()
    except Exception:  # noqa: BLE001 - без реестра остаётся имя фичи
        loaded = []
    spec = next((item.spec for item in loaded if item.spec.id == module_id), None)
    if spec is not None and tuple(spec.provides_tools):
        return set(spec.provides_tools)
    return {module_id.split(".", 1)[1]}


def main(argv):
    logging.getLogger("godot_agent").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("module_id", nargs="?")
    parser.add_argument("--json", action="store_true")
    options = parser.parse_args(argv[1:])
    only = module_tools(options.module_id) if options.module_id else None
    folders = selected_folders(corpora(), options.module_id)
    if not folders:
        return verdict("not_implemented", "корпуса нет: fixtures/corpus/<область>/<фича>/")
    agent_cache, total, failures, report = {}, 0, [], []
    for folder in folders:
        touched, passed, module_failures = run_corpus(agent_cache, folder, only)
        if not touched:
            continue
        total += touched
        failures.extend(module_failures)
        report.append({"corpus": str(folder.relative_to(ROOT)).replace("\\", "/"),
                       "cases": touched, "passed": passed, "failures": module_failures[:5]})
        print("%-40s кейсов %3d, совпало %3d, расхождений %d"
              % (report[-1]["corpus"], touched, passed, len(module_failures)))
    if not report:
        return verdict("not_implemented", "нет кейсов для %r" % (options.module_id,))
    if options.json:
        print(json.dumps(report, ensure_ascii=False))
    if failures:
        return verdict("fail", "расхождений %d: %s" % (len(failures), "; ".join(failures[:3])))
    return verdict("ok", "кейсов %d, расхождений нет" % total)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
