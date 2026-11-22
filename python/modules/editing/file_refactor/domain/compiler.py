"""Pure C.22 transaction compilation using only the declared C.21 projection."""
import base64

from python.kernel.errors import AppError
from python.kernel.write_plan import Step
import python.modules.editing.paths_preview as paths_preview

from ...shared import script_edits
from . import core


def project(request, snapshot):
    old, new, references = request
    docs, existing, unsafe = snapshot["documents"], snapshot["existing"], snapshot["unsafe"]
    if snapshot["directory"]:
        rows, after = paths_preview.project_directory(docs, old, new, existing, unsafe, snapshot["owners"])
        projected = {row["path"]: {"text": after[row["path"]], "occurrences": row["occurrences"]}
                     for row in rows if references or row["path"] in snapshot["owners"]}
    else:
        projected = paths_preview.project_file(docs, existing, unsafe, old, new, references)
    for path, dest in snapshot["imports"].items():
        text, _bom = paths_preview.decode_raw(snapshot["raw"][path])
        text, count = core.import_projection(text, path[:-7], dest[:-7])
        projected[path] = {"text": text, "occurrences": int(count > 0)}
    return projected


def compile_plan(request, snapshot, projected, preview_diff, lint):
    old, new, references = request
    raw, owners, imports = snapshot["raw"], snapshot["owners"], snapshot["imports"]
    steps, patches, expected, files, transferred = [], [], {}, [], set()
    case = snapshot["dir_case"]

    def destination(path, dest):
        return case[0] + dest[len(case[1]):] if case else dest

    def transfer(path, dest):
        current_dest = destination(path, dest)
        sha = script_edits.sha256(raw[path])
        expected[path] = sha
        if path != current_dest:
            expected[current_dest] = ""
            steps.append(Step("move", path, {"dest": current_dest}, sha, "move"))
        transferred.add(path)
        return current_dest

    def row(path, dest=None, companion=False):
        before, bom = paths_preview.decode_raw(raw[path])
        data = projected.get(path, {"text": before, "occurrences": 0})
        after, count = data["text"], data["occurrences"]
        new_raw = ((b"\xef\xbb\xbf" if bom else b"") + after.encode("utf-8")) if count else raw[path]
        if count and path.lower().endswith(".gd"):
            errors = lint(after)
            if errors:
                detail = "ссылки" if dest is None else "путей" if snapshot["directory"] else "внутренних путей"
                raise AppError("invalid_input", "После обновления %s в %s обнаружена синтаксическая ошибка: %s" % (detail, path, errors[0]))
        result = {"action": "move_file" if dest else "patch_file", "path": path,
                  "before_hash": script_edits.sha256(raw[path]), "occurrences": count}
        diff = preview_diff(before, after)
        if dest:
            result["dest"] = dest
            if companion:
                if diff is None:
                    raise AppError("internal", "'NoneType' object does not support item assignment")
                result["is_companion"] = True
                info = "Файл импорта (.import) перемещён в %s" % dest
            elif count:
                wording = ("путей" if path.lower().endswith(".gd") else "ссылок") if snapshot["directory"] else "внутренних путей"
                info = "Файл перемещён в %s (обновлено %s: %d)" % (dest, wording, count)
            else:
                info = "Файл перемещён в %s" % dest
            diff = dict(diff) if diff else {"lines": []}
            diff["lines"] = [{"type": "info", "text": info}] + diff["lines"]
            diff["dest"] = dest
        if diff is not None:
            diff.update(action=result["action"], path=path)
        result["diff"] = diff
        files.append(result)
        if new_raw != raw[path]:
            patch_target = destination(path, dest) if dest else path
            expected.setdefault(patch_target, script_edits.sha256(raw[path]))
            patches.append(Step("replace_raw", patch_target,
                           {"bytes_b64": base64.b64encode(new_raw).decode("ascii")},
                           script_edits.sha256(raw[path])))

    for path, dest in owners.items():
        transfer(path, dest)
        row(path, dest)
        companion = path + ".import"
        if companion in imports:
            transfer(companion, imports[companion])
            row(companion, imports[companion], True)
        uid = path + ".uid"
        if uid in raw:
            transfer(uid, dest + ".uid")
    for path, dest in imports.items():
        if path not in transferred:
            transfer(path, dest)
            row(path, dest, True)
    for path in sorted(projected):
        if path not in transferred:
            expected[path] = script_edits.sha256(raw[path])
            row(path)
    steps.extend(patches)
    if case:
        expected[case[0]] = expected[case[1]] = ""
        steps.append(Step("dir_case", case[0], {"dest": case[1]}, "", "dir_case"))
    ordered = sorted(files, key=lambda item: item["path"])
    summary = {"action": "rename_file", "old_path": old, "new_path": new,
               "files": ordered,
               "reference_count": sum(item["occurrences"] for item in files if not item.get("is_companion")),
               "affected_paths": [item.get("dest", item["path"]) for item in ordered]}
    if snapshot["directory"]:
        summary.update(is_directory=True, moved_files=owners)
    else:
        text = snapshot["documents"][old]["text"]
        summary.update(companion_script=core.companion_script(text) if old.lower().endswith(".tscn") else None,
                       update_references=references)
    return steps, expected, summary
