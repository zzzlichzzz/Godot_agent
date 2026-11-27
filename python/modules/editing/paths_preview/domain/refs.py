"""Frozen discovery regexes and decoding, operating only on supplied documents."""
import posixpath
import re

EXTENSIONS = (".gd", ".tscn", ".tres", ".gdshader", ".gdshaderinc")
SKIP_DIRS = {".git", ".godot", ".import", "__pycache__", ".agent_history", "addons"}


def decode(raw):
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return text, bom


def visible(rel, policy):
    for part in rel.split("/")[:-1]:
        if part in SKIP_DIRS and not (part.casefold() == "addons" and
                                     (policy.allow_addons or policy.allow_self_edit)):
            return False
    return not policy.deny_reason(rel)


def eligible(rel):
    return posixpath.splitext(rel)[1].lower() in EXTENSIONS or posixpath.basename(rel) == "project.godot"


def exact_pattern(old):
    return re.compile(r'(?<=["\'\*])' + re.escape(old) + r'(?=["\'\s,\]])')


def find_file_references(documents, old):
    pattern = exact_pattern(old)
    rows = []
    for path, data in documents.items():
        if path == old or not eligible(path[6:]):
            continue
        text = data["text"]
        exact = len(list(pattern.finditer(text)))
        rels = []
        if posixpath.splitext(path)[1].lower() == ".gd":
            relative = posixpath.relpath(old[6:], posixpath.dirname(path[6:]) or ".")
            candidates = [relative] + (["./" + relative] if not relative.startswith(".") else [])
            for candidate in candidates:
                rel_pat = re.compile(r'(\b(?:preload|load|extends)\s*\(?\s*["\'])' + re.escape(candidate) + r'(["\'])')
                for match in rel_pat.finditer(text):
                    start = match.start(0) + len(match.group(1))
                    rels.append([start, start + len(candidate), candidate])
        if exact + len(rels):
            rows.append({"path": path, "occurrences": exact + len(rels), "exact_matches": exact,
                         "rel_matches": rels, "bom": data["bom"]})
    return rows
