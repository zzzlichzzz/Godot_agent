"""Pure subtree removal plus warnings; scripts are never modified."""
from python.formats import gdscript, tscn
from ...shared.node_path import find_node_in_scene, rel_path_between
from ...shared.refactor_plan import attached_scripts, decode, file_plan, prepare_scene


def validate_delete(view, spec):
    target = find_node_in_scene(view[1], spec)
    if target['parent'] is None:
        raise ValueError('Нельзя удалить корневой узел сцены')
    old_path = target['path']
    deleted = [target]
    for node in view[1]:
        parent = node['parent']
        if parent and (parent == old_path or parent.startswith(old_path + '/')):
            deleted.append(node)
    return target, deleted


def script_groups(view, deleted):
    return attached_scripts(view, {node['path'] for node in deleted})


def prepare_delete(raw, scene, spec, scripts, preview, cleanup_code=True, view=None):
    text = decode(raw)
    view = prepare_scene(raw) if view is None else view
    target, deleted = validate_delete(view, spec)
    paths = {node['path'] for node in deleted}
    names = {node['name'] for node in deleted if node['unique_name']}
    edits, count = tscn.node_delete_edits(text, view, deleted, paths, names)
    changed = tscn.patch(text, edits)
    files = [file_plan(raw, text, changed, scene, count, preview)]
    warnings = []
    if cleanup_code:
        for path, nodes in script_groups(view, deleted).items():
            if path not in scripts:
                continue
            rel_paths = {rel_path_between(node['path'], deleted_path)
                         for node in nodes for deleted_path in paths}
            if any(node['path'] == '.' for node in nodes):
                rel_paths.update(paths)
            for line, code in gdscript.deleted_node_references(decode(scripts[path]), rel_paths, names):
                warnings.append({'file': path, 'line': line, 'code': code,
                                 'message': "Ссылка на удаляемый узел '%s' в %s:%d: %s" %
                                            (target['name'], path, line, code)})
    return {'action': 'delete_node', 'scene': scene, 'target_node': target['name'],
            'target_node_path': target['path'], 'deleted_nodes': [node['path'] for node in deleted],
            'files': files, 'reference_count': count, 'affected_paths': [item['path'] for item in files],
            'warnings': warnings}
