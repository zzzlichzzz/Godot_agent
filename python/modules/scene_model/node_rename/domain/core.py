"""Pure raw-bytes -> read-only native rename plan; no IO, regex or application."""
import base64
import hashlib

from python.formats import gdscript, tscn
from ...shared.node_path import find_node_in_scene, rel_path_between
from .diff_preview import preview


def decode(raw):
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('utf-8', errors='replace')


def prepare_scene(raw):
    return tscn.structure(decode(raw))


def attached_scripts(view):
    ext, nodes, _, _ = view
    attached = {}
    for node in nodes:
        path = ext.get(node['script_id'], {}).get('path')
        if path and path.endswith('.gd'):
            attached.setdefault(path, []).append(node)
    return attached


def _file(raw, text, changed, path, occurrences):
    diff = preview(text, changed)
    if diff is None:
        return None
    diff.update(path=path, action='patch_file')
    after = (b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'') + changed.encode('utf-8')
    return {'action': 'patch_file', 'path': path, 'before_hash': hashlib.sha256(raw).hexdigest(),
            'before_bytes': base64.b64encode(raw).decode('ascii'),
            'after_bytes': base64.b64encode(after).decode('ascii'), 'diff': diff, 'occurrences': occurrences}


def validate_rename(view, spec, new_name, previous_name=''):
    """Reference validates target/collisions before it reads attached scripts."""
    new_name = tscn.normalize_node_name(new_name)
    target = find_node_in_scene(view[1], spec)
    old_name, old_path, parent = target['name'], target['path'], target['parent']
    seen_name = tscn.normalize_node_name(previous_name) if str(previous_name or '').strip() else old_name
    seen_path = old_path
    if old_name != seen_name:
        seen_path = seen_name if parent in ('.', None) else parent.rstrip('/') + '/' + seen_name
    if seen_name == new_name:
        raise ValueError('Новое имя узла совпадает со старым: %s' % new_name)
    for node in view[1]:
        if node.get('path') == old_path:
            continue
        if node['parent'] == parent and node['name'] == new_name:
            raise ValueError("Узел с именем '%s' уже существует в той же ветке" % new_name)
    new_path = '.' if parent is None else new_name if parent == '.' else parent.rstrip('/') + '/' + new_name
    return target, new_name, seen_name, seen_path, new_path


def prepare_rename(raw, scene, spec, new_name, scripts, linter, update_scripts=True,
                   scripts_only=False, previous_name='', view=None):
    text = decode(raw)
    view = tscn.structure(text) if view is None else view
    target, new_name, seen_name, seen_path, new_path = validate_rename(view, spec, new_name, previous_name)
    old_name, old_path = target['name'], target['path']
    edits, scene_count = tscn.node_rename_edits(text, view, target, new_name, new_path)
    changed = tscn.patch(text, edits)
    files, count = [], scene_count
    scene_file = _file(raw, text, changed, scene, scene_count)
    if not scripts_only and scene_file is not None:
        files.append(scene_file)
    if update_scripts:
        for path, nodes in attached_scripts(view).items():
            if path not in scripts:
                continue
            before = scripts[path]
            source = decode(before)
            pairs = []
            for node in nodes:
                old, new = rel_path_between(node['path'], seen_path), rel_path_between(node['path'], new_path)
                if old != new:
                    pairs.append((old, new))
            if any(node['path'] == '.' for node in nodes) and seen_path != '.':
                pairs.append((seen_path, new_path))
            pairs = list(dict.fromkeys(pairs))
            changed, occurrences = gdscript.rename_node_paths(source, seen_name, new_name, target['unique_name'], pairs)
            if occurrences > 0 and changed != source:
                errors = linter(changed)
                if errors:
                    raise ValueError('После обновления узла в скрипте %s обнаружена синтаксическая ошибка: %s' % (path, errors[0]))
                files.append(_file(before, source, changed, path, occurrences))
                count += occurrences
    return {'action': 'rename_node', 'scene': scene, 'old_name': old_name, 'new_name': new_name,
            'old_path': old_path, 'new_path': new_path, 'target_node_path': old_path, 'files': files,
            'reference_count': count - scene_count if scripts_only else count,
            'affected_paths': [item['path'] for item in files], 'scripts_only': bool(scripts_only),
            'previous_name': seen_name if str(previous_name or '').strip() else ''}
