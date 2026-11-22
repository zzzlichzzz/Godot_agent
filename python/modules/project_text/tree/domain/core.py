"""Native tree: sorted files before dirs, file-only quota, depth eight."""
EXCLUDED_DIRS = {".godot", ".import", ".git", ".venv", "__pycache__", "node_modules",
                 ".vs", ".vscode", ".agent_history", "minilich_brain"}


def visible_entry(row, base):
    name = row["path"].rsplit("/", 1)[-1]
    if row["type"] == "dir":
        return not name.startswith(".") and name not in EXCLUDED_DIRS
    return name != ".DS_Store" and not name.lower().endswith(".uid")


def build(entries, base, max_depth=8, max_entries=200, only_exts=None):
    root = {"path": "res://" + base, "type": "dir", "children": [], "count": 0}
    groups = {}
    for row in entries:
        parent = row["path"].rpartition("/")[0]
        groups.setdefault(parent, []).append(row)
    used, stopped = 0, False
    def visit(node, rel, depth):
        nonlocal used, stopped
        rows = groups.get(rel, ())
        files = sorted((r for r in rows if r["type"] == "file"), key=lambda r: r["path"])
        dirs = sorted((r for r in rows if r["type"] == "dir"), key=lambda r: r["path"])
        for row in files:
            name = row["path"].rsplit("/", 1)[-1]
            extension = ("." + name.rsplit(".", 1)[-1]).lower() if "." in name else ""
            if not visible_entry(row, base) or (only_exts is not None and extension not in only_exts):
                continue
            if used >= max_entries:
                stopped = True
                break
            node["children"].append({"path": "res://" + row["path"], "type": "file", "children": [], "count": 1})
            used += 1
        if depth < max_depth:
            for row in dirs:
                if stopped:
                    break
                if not visible_entry(row, base):
                    continue
                child = {"path": "res://" + row["path"], "type": "dir", "children": [], "count": 0}
                node["children"].append(child)
                visit(child, row["path"], depth + 1)
        node["count"] = sum(child["count"] for child in node["children"])
    visit(root, base, 0)
    return root
