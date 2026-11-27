"""Read-only directory reference aggregation: no relocation plan or effects."""
import re

from python.kernel.errors import AppError

from . import internal, refs


def references(documents, old, new, existing, unsafe):
    return projections(documents, old, new, existing, unsafe)[0]


def projections(documents, old, new, existing, unsafe, moved_files_map=None):
    """Extract already-computed after-text; the existing references API is unchanged."""
    old_prefix, new_prefix = old.rstrip("/") + "/", new.rstrip("/") + "/"
    moved = (moved_files_map if moved_files_map is not None else
             {path: new_prefix + path[len(old_prefix):] for path in sorted(documents)
              if path.startswith(old_prefix) and not path.lower().endswith(".uid")})
    if not moved and moved_files_map is None:
        raise AppError("invalid_input", "Папка %s не содержит подходящих файлов для перемещения" % old)
    prefix_pat = re.compile(r'(?<=["\'\*])' + re.escape(old_prefix) + r'([^"\'\s,\]]*)(?=["\'\s,\]])')
    dir_pat = refs.exact_pattern(old)

    def directories(text):
        text, first = prefix_pat.subn(lambda m: new_prefix + m.group(1), text)
        text, second = dir_pat.subn(lambda m: new, text)
        return text, first + second

    rows, after = [], {}
    for path, destination in moved.items():
        data = documents[path]
        text, count, rels = data["text"], 0, []
        if path.lower().endswith(".gd"):
            text, count, rels = internal.project_details(text, path, destination, existing, moved, unsafe)
            text, extra = directories(text)
            count += extra
        elif path.lower().endswith((".tscn", ".tres")):
            for target, replacement in moved.items():
                text, extra = refs.exact_pattern(target).subn(lambda m, value=replacement: value, text)
                count += extra
            text, extra = directories(text)
            count += extra
        rows.append({"path": path, "occurrences": count, "exact_matches": count - len(rels),
                     "rel_matches": rels, "bom": data["bom"]})
        after[path] = text

    external = {}
    for target in moved:
        for row in refs.find_file_references(documents, target):
            if row["path"] in moved:
                continue
            external.setdefault(row["path"], []).extend([start, end, raw, moved[target]]
                                                         for start, end, raw in row["rel_matches"])
    for path, data in documents.items():
        if path in moved or path.startswith(old_prefix) or not refs.eligible(path[6:]):
            continue
        rels = external.get(path, [])
        text, count = data["text"], len(rels)
        for start, end, raw, destination in sorted(rels, key=lambda r: r[0], reverse=True):
            text = text[:start] + destination + text[end:]
        for target, replacement in moved.items():
            text, extra = refs.exact_pattern(target).subn(lambda m, value=replacement: value, text)
            count += extra
        text, extra = directories(text)
        count += extra
        if text != data["text"]:
            rows.append({"path": path, "occurrences": count, "exact_matches": count - len(rels),
                         "rel_matches": [r[:3] for r in rels], "bom": data["bom"]})
            after[path] = text
    return rows, after
