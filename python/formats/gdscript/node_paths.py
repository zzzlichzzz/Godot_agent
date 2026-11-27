"""Literal node_refactor.py:457-495 transforms, including comment quirks."""
import re


def rename_node_paths(text, seen_name, new_name, unique, paths):
    changes = 0
    if unique:
        text, count = re.subn(r'(%|\$"%|get_node\(["\']%)' + re.escape(seen_name) + r'(\b|["\'])',
                             r'\g<1>' + new_name + r'\2', text)
        changes += count
    for old, new in paths:
        pattern = re.escape(old)
        text, count = re.subn(r'(\$)' + pattern + r'((?:/[A-Za-z0-9_]+)*)(\b)',
                             r'\g<1>' + new + r'\2\3', text)
        changes += count
        text, count = re.subn(r'(\b(?:get_node|get_node_or_null|has_node)\s*\(\s*["\']|\$["\'])' +
                             pattern + r'((?:/[^"\']*)?)(["\'])', r'\g<1>' + new + r'\2\3', text)
        changes += count
    text, count = re.subn(r'(\bfind_child\s*\(\s*["\'])' + re.escape(seen_name) + r'(["\'])',
                         r'\g<1>' + new_name + r'\2', text)
    return text, changes + count


# C.7 append-only literal operations; accepted C.6 transform stays unchanged.
def reparent_node_paths(text, paths):
    changes = 0
    for old, new in paths:
        pattern = re.escape(old)
        if new.startswith('..') or any(not part.isidentifier() for part in new.split('/') if part):
            text, count = re.subn(r'\$' + pattern + r'((?:/[A-Za-z0-9_]+)*)(\b)',
                                 r'$"' + new + r'\1"', text)
        else:
            text, count = re.subn(r'(\$)' + pattern + r'((?:/[A-Za-z0-9_]+)*)(\b)',
                                 r'\g<1>' + new + r'\2\3', text)
        changes += count
        text, count = re.subn(r'(\b(?:get_node|get_node_or_null|has_node)\s*\(\s*["\']|\$["\'])' +
                             pattern + r'((?:/[^"\']*)?)(["\'])', r'\g<1>' + new + r'\2\3', text)
        changes += count
    return text, changes


def deleted_node_references(text, paths, unique_names):
    found = []
    for line_idx, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#'):
            continue
        matched = False
        for path in paths:
            pattern = re.escape(path)
            if (re.search(r'\$' + pattern + r'(\b|/)', line) or
                    re.search(r'(\b(?:get_node|get_node_or_null|has_node)\s*\(\s*["\']|\$["\'])' +
                              pattern + r'(\b|/|["\'])', line)):
                matched = True
                break
        if not matched:
            for name in unique_names:
                if re.search(r'(%|\$"%|get_node\(["\']%)' + re.escape(name) + r'(\b|["\'])', line):
                    matched = True
                    break
        if matched:
            found.append((line_idx, stripped))
    return found
