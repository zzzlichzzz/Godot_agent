"""Declared C.21 read/projection seam for C.22; no effects or import-time IO."""
from . import ports
from .domain import directory, internal, refs


def snapshot(fs, policy, old, is_directory):
    return ports.read_project(fs, policy, old, is_directory)


def decode_raw(raw):
    return refs.decode(raw)


def project_file(documents, existing, unsafe, old, new, update_references):
    text, count = documents[old]["text"], 0
    if old.lower().endswith(".gd"):
        text, count = internal.update_internal_relative_paths(text, old, new, existing, unsafe=unsafe)
    updates = {old: {"text": text, "occurrences": count}}
    if update_references:
        for row in refs.find_file_references(documents, old):
            text = documents[row["path"]]["text"]
            for start, end, _raw in sorted(row["rel_matches"], reverse=True):
                text = text[:start] + new + text[end:]
            text = refs.exact_pattern(old).sub(lambda _match: new, text)
            updates[row["path"]] = {"text": text, "occurrences": row["occurrences"]}
    return updates


def project_directory(documents, old, new, existing, unsafe, moved_files_map=None,
                      *, external_relative: bool = True):
    if external_relative:
        return directory.projections(documents, old, new, existing, unsafe, moved_files_map)
    moved, external = internal.partition_directory(documents, old)
    rows, after = directory.projections(moved, old, new, existing, unsafe, moved_files_map)
    extra, external_after = directory.projections(external, old, new, existing, unsafe, {})
    return rows + extra, dict(after, **external_after)
