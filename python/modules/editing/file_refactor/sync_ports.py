"""External snapshot through C.21; raw anchor proofs are consumer-owned IO."""
from python.kernel.errors import AppError
import python.modules.editing.paths_preview as paths_preview

from ..shared import funnel, script_edits


def completed_alias(writer, old, new, expected):
    """No Entry for an alias: prove real paths, both raw SHA and published casing."""
    try:
        a, b = writer.actual_rel(old[6:]), writer.actual_rel(new[6:])
        hashes = [script_edits.sha256(writer.read_raw(path[6:])) for path in (old, new)]
        valid = (a == b == new[6:] and writer.same_file(old[6:], new[6:])
                 and hashes[0] == hashes[1] == expected)
    except OSError:
        valid = False
    if not valid:
        raise AppError("conflict", "external case-only anchor не доказан: %s" % new)


def snapshot(ctx, old, new, directory):
    writer = ctx.port("writer")
    for path in (old, new):
        try:
            funnel.guard_transfer(ctx, path[6:], path[6:])
        except AppError:
            raise AppError("denied", "Путь защищён текущей политикой доступа: %s" % path) from None
    directory = directory or (writer.exists(new[6:]) and writer.is_dir(new[6:]))
    docs, existing, unsafe = paths_preview.snapshot(ctx.port("paths_fs"), ctx.path_policy, new, True)
    prefix = new.rstrip("/") + "/"
    anchors = ({old + "/" + rel[len(prefix[6:]):]: "res://" + rel for rel in sorted(existing)
                if rel.startswith(prefix[6:])} if directory else
               {old: new} if writer.is_file(new[6:]) else {})
    case = (old, new) if directory and old.casefold() == new.casefold() and writer.same_directory(old[6:], new[6:]) else None
    raw, transfers, imports, completed = {}, {}, {}, []
    for source, dest in anchors.items():
        funnel.guard_transfer(ctx, source[6:], dest[6:])
        raw[dest] = writer.read_raw(dest[6:])
        if case:
            continue
        if source.casefold() == dest.casefold() and writer.exists(source[6:]):
            completed_alias(writer, source, dest, script_edits.sha256(raw[dest]))
            completed.append((source, dest, script_edits.sha256(raw[dest])))
        else:
            transfers[source] = (dest, True)
    if not directory:
        for suffix in (".import", ".uid"):
            source, dest = old + suffix, new + suffix
            if writer.is_file(dest[6:]):
                raw[dest] = writer.read_raw(dest[6:])
                if source.casefold() == dest.casefold() and writer.exists(source[6:]):
                    completed_alias(writer, source, dest, script_edits.sha256(raw[dest]))
                    completed.append((source, dest, script_edits.sha256(raw[dest])))
                else:
                    transfers[source] = (dest, True)
            elif writer.is_file(source[6:]):
                raw[source] = writer.read_raw(source[6:])
                transfers[source] = (dest, False)
            if suffix == ".import":
                if source in raw:
                    imports[source] = (old, new)
                elif dest in raw:
                    imports[dest] = (old, new)
    else:
        imports = {dest: (source[:-7], dest[:-7]) for source, dest in anchors.items() if dest.lower().endswith(".import")}
    for path in docs:
        raw.setdefault(path, writer.read_raw(path[6:]))
    if not directory and new in raw:
        text, bom = paths_preview.decode_raw(raw[new])
        docs[new] = {"text": text, "bom": bom}
    virtual = {old + path[len(new):] if directory and path.startswith(prefix) else path: data
               for path, data in docs.items()}
    owners = {source: dest for source, dest in anchors.items() if source in virtual
              and not source.lower().endswith((".uid", ".import"))}
    return {"documents": virtual, "current_documents": docs, "existing": existing, "unsafe": unsafe,
            "raw": raw, "owners": owners, "transfers": transfers, "imports": imports,
            "directory": directory, "dir_case": case, "completed": completed,
            "anchor_present": writer.exists(new[6:])}
