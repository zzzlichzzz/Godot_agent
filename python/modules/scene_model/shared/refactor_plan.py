"""Pure C.7 byte envelope and ordered attached resources, no project IO."""
import base64
import hashlib

from python.formats import tscn


def decode(raw):
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('utf-8', errors='replace')


def prepare_scene(raw):
    return tscn.structure(decode(raw))


def attached_scripts(view, excluded=()):
    ext, nodes, _, _ = view
    groups = {}
    for node in nodes:
        if node['path'] in excluded:
            continue
        path = ext.get(node['script_id'], {}).get('path')
        if path and path.endswith('.gd'):
            groups.setdefault(path, []).append(node)
    return groups


def file_plan(raw, text, changed, path, occurrences, preview):
    diff = preview(text, changed)
    diff.update(path=path, action='patch_file')
    after = (b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'') + changed.encode('utf-8')
    return {'action': 'patch_file', 'path': path, 'before_hash': hashlib.sha256(raw).hexdigest(),
            'before_bytes': base64.b64encode(raw).decode('ascii'),
            'after_bytes': base64.b64encode(after).decode('ascii'), 'diff': diff, 'occurrences': occurrences}
