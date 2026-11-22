"""C.7 span operations over the sole tscn.structure view, never a second parser.

Native node_refactor.py:594-648/840-866. Caller applies accepted tscn.patch;
overlapping native spans and following CR/LF consumption are not improved.
"""
import re



def _parent_header(header, parent, insert=False):
    if insert and not re.search(r'\bparent\s*=\s*"[^"]*"', header):
        return header[:-1].rstrip() + ' parent="%s"]' % parent
    return re.sub(r'(\bparent\s*=\s*")[^"]*(")',
                  r'\g<1>' + parent + r'\2', header, count=1)


def node_reparent_edits(text, view, target, new_parent, new_path, rename_attribute):
    _, nodes, connections, tracks = view
    old_path = target['path']
    start, end = target['header_span']
    header = text[start:end]
    updated = _parent_header(header, new_parent, insert=True)
    edits = [((start, end), updated)] if updated != header else []
    for node in nodes:
        parent = node['parent']
        if not parent or parent == '.':
            continue
        if parent == old_path or parent.startswith(old_path + '/'):
            start, end = node['header_span']
            header = text[start:end]
            updated = _parent_header(header, new_path + parent[len(old_path):])
            if updated != header:
                edits.append(((start, end), updated))
    for connection in connections:
        start, end = connection['span']
        original = text[start:end]
        updated = original
        for attr in ('from', 'to'):
            value = connection[attr]
            if value == old_path or value.startswith(old_path + '/'):
                updated = rename_attribute(updated, attr, value, new_path + value[len(old_path):])
        if updated != original:
            edits.append(((start, end), updated))
    for track in tracks:
        parts = track['path'].split(':')
        node_part = parts[0]
        suffix = ':' + ':'.join(parts[1:]) if len(parts) > 1 else ''
        if node_part == old_path or node_part.startswith(old_path + '/'):
            edits.append((track['path_span'], new_path + node_part[len(old_path):] + suffix))
    return edits, len(edits)


def _following_eol(text, end):
    while end < len(text) and text[end] in ('\r', '\n'):
        end += 1
    return end


def node_delete_edits(text, view, deleted, paths, unique_names):
    edits = []
    for node in deleted:
        start = node['header_span'][0]
        end = _following_eol(text, node['body_span'][1])
        edits.append(((start, end), ''))
    for connection in view[2]:
        if connection['from'] in paths or connection['to'] in paths:
            start, end = connection['span']
            edits.append(((start, _following_eol(text, end)), ''))
    for track in view[3]:
        node_part = track['path'].split(':')[0]
        if node_part in paths or (node_part.startswith('%') and node_part[1:] in unique_names):
            start, end = track['full_span']
            edits.append(((start, _following_eol(text, end)), ''))
    return edits, len(edits)
