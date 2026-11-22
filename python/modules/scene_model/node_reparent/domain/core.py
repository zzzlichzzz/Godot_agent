"""Pure prepare_node_reparent semantics; formats own all textual transforms."""
from python.formats import gdscript, tscn
from ...shared.node_path import find_node_in_scene, rel_path_between
from ...shared.refactor_plan import attached_scripts, decode, file_plan, prepare_scene


def validate_reparent(view, spec, parent_spec):
    nodes = view[1]
    target = find_node_in_scene(nodes, spec)
    parent = find_node_in_scene(nodes, parent_spec)
    old_path, parent_path, name = target['path'], parent['path'], target['name']
    if target['parent'] is None:
        raise ValueError('Нельзя перемещать корневой узел сцены')
    if old_path == parent_path:
        raise ValueError('Нельзя переместить узел в самого себя')
    if parent_path.startswith(old_path + '/'):
        raise ValueError('Нельзя переместить узел в его собственного потомка')
    current = '.' if target['parent'] in ('.', None) else target['parent']
    if current == parent_path:
        raise ValueError("Узел '%s' уже находится у этого родителя" % name)
    for node in nodes:
        sibling_parent = '.' if node['parent'] in ('.', None) else node['parent']
        if sibling_parent == parent_path and node['name'] == name and node['path'] != old_path:
            raise ValueError("Узел с именем '%s' уже существует в целевом родителе" % name)
    new_path = name if parent_path == '.' else parent_path + '/' + name
    return target, parent_path, new_path


def _relocated(path, old_path, new_path):
    if path == old_path:
        return new_path
    if path.startswith(old_path + '/'):
        return new_path + path[len(old_path):]
    return path


def prepare_reparent(raw, scene, spec, parent_spec, scripts, linter, preview,
                     update_scripts=True, view=None):
    text = decode(raw)
    view = prepare_scene(raw) if view is None else view
    target, parent_path, new_path = validate_reparent(view, spec, parent_spec)
    old_path = target['path']
    edits, count = tscn.node_reparent_edits(text, view, target, parent_path, new_path)
    changed = tscn.patch(text, edits)
    files = [file_plan(raw, text, changed, scene, count, preview)]
    if update_scripts:
        moved = [target]
        for node in view[1]:
            parent = node['parent']
            if node['path'] != old_path and parent and (parent == old_path or parent.startswith(old_path + '/')):
                moved.append(node)
        for path, nodes in attached_scripts(view).items():
            if path not in scripts:
                continue
            pairs = []
            for moving in moved:
                before_path = moving['path']
                after_path = _relocated(before_path, old_path, new_path)
                for node in nodes:
                    origin = node['path']
                    updated_origin = _relocated(origin, old_path, new_path)
                    old_rel = rel_path_between(origin, before_path)
                    new_rel = rel_path_between(updated_origin, after_path)
                    if old_rel != new_rel:
                        pairs.append((old_rel, new_rel))
                if any(node['path'] == '.' for node in nodes) and before_path != '.':
                    pairs.append((before_path, after_path))
            pairs = list(dict.fromkeys(pairs))
            before = scripts[path]
            source = decode(before)
            changed, occurrences = gdscript.reparent_node_paths(source, pairs)
            if occurrences > 0 and changed != source:
                errors = linter(changed)
                if errors:
                    raise ValueError('После перемещения узла в скрипте %s обнаружена синтаксическая ошибка: %s' % (path, errors[0]))
                files.append(file_plan(before, source, changed, path, occurrences, preview))
                count += occurrences
    return {'action': 'reparent_node', 'scene': scene, 'target_node': target['name'],
            'old_path': old_path, 'new_parent': parent_path, 'new_path': new_path,
            'target_node_path': old_path, 'files': files, 'reference_count': count,
            'affected_paths': [item['path'] for item in files]}
