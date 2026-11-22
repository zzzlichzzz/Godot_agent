"""Pure external-sync projection/compiler; same scanner, diff, lint and steps."""
import base64

from python.kernel.write_plan import Step
import python.modules.editing.paths_preview as paths_preview

from ...shared import script_edits
from . import core


def compile_plan(old, new, snapshot, diff, lint):
    docs, existing, unsafe = snapshot["documents"], snapshot["existing"], snapshot["unsafe"]
    if snapshot["directory"]:
        rows, after = paths_preview.project_directory(docs, old, new, existing, unsafe,
                                                      snapshot["owners"], external_relative=False)
        projected = {snapshot["owners"].get(row["path"], row["path"]):
                     {"text": after[row["path"]], "occurrences": row["occurrences"]} for row in rows}
    else:
        # Use the same file projection: first external refs, then moved-file internal paths.
        virtual = dict(docs)
        virtual[old] = snapshot["current_documents"].get(new, {"text": "", "bom": False})
        projected = paths_preview.project_file(virtual, existing, unsafe, old, new, True)
        projected[new] = projected.pop(old)
    for path, (source, dest) in snapshot["imports"].items():
        text, _bom = paths_preview.decode_raw(snapshot["raw"][path])
        text, count = core.import_projection(text, source, dest)
        projected[path] = {"text": text, "occurrences": int(count > 0)}
    steps, expected, patches, moved, changed, refs = [], {}, [], [], [], 0
    for source, (dest, anchor) in snapshot["transfers"].items():
        sha = script_edits.sha256(snapshot["raw"][dest if anchor else source])
        expected[source], expected[dest] = ("", sha) if anchor else (sha, "")
        steps.append(Step("move", source, {"dest": dest, "already_moved": anchor}, sha, "move"))
        if not anchor:
            moved.append({"path": source, "dest": dest})
            changed.append(dest)
    for path, data in sorted(projected.items()):
        if path not in snapshot["raw"]:
            continue
        raw = snapshot["raw"][path]
        before, bom = paths_preview.decode_raw(raw)
        after, count = data["text"], data["occurrences"]
        if after == before or not count or path.lower().endswith(".gd") and lint(after):
            continue
        dest = snapshot["transfers"].get(path, (path, True))[0]
        if snapshot["dir_case"] and dest.startswith(new + "/"):
            dest = old + dest[len(new):]
        sha = script_edits.sha256(raw)
        expected.setdefault(dest, sha)
        new_raw = (b"\xef\xbb\xbf" if bom else b"") + after.encode("utf-8")
        steps.append(Step("replace_raw", dest, {"bytes_b64": base64.b64encode(new_raw).decode("ascii")}, sha))
        patches.append({"path": path, "occurrences": count, "diff": diff(before, after)})
        changed.append(snapshot["transfers"].get(path, (path, True))[0])
        if not (path in snapshot["imports"] and not snapshot["directory"]):
            refs += count
    case = snapshot["dir_case"]
    if case:
        expected[old] = expected[new] = ""
        steps.append(Step("dir_case", old, {"dest": new}, "", "dir_case"))
    summary = {"ok": True, "old_path": old, "new_path": new, "is_directory": snapshot["directory"],
               "changed_paths": sorted(set(changed)), "reference_count": refs,
               "file_count": len(patches) + sum(row["path"] not in projected or
                    not projected[row["path"]]["occurrences"] for row in moved) + int(snapshot["anchor_present"] and not snapshot["completed"]),
               "patches": patches, "moved": moved, "anchor_already_completed": bool(snapshot["completed"])}
    return steps, expected, summary
