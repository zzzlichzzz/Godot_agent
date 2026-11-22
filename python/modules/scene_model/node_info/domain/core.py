"""Pure node lookup/card, frozen ba0535d4dec43c32750e601a6ca86e377abc6af3.

find_node_in_scene/rel_path_between: ported verbatim from node_refactor.py
185-222/163-182. Actual-old corpus/hashes: fixtures/corpus/scene_model/node_info.
Parsing delegates only to accepted tscn.structure/fields. Depth/path's two
simple rules repeat tree's documented projection, not its private domain API;
integration pins equality without a forbidden inter-module import (R-11).
"""
from python.formats import tscn
from ...shared.node_path import find_node_in_scene, rel_path_between


def _path(node):
    parent = node['parent']
    return '.' if parent is None else node['name'] if parent == '.' else parent + '/' + node['name']


def describe(raw, spec):
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('utf-8', errors='replace')
    ext, nodes, _, _ = tscn.structure(text)
    field_ext, field_nodes, _ = tscn.fields(text)
    target = find_node_in_scene(nodes, spec)
    instances = {}
    for field in field_nodes:
        instances.setdefault((field['name'], field['parent']), []).append(field['instance_id'])
    instance = None
    for n in nodes:
        ids = instances.get((n['name'], n['parent']), [])
        instance_id = ids.pop(0) if ids else None
        if n is target:
            instance = field_ext.get(instance_id, {}).get('path') or None
    parent = target['parent']
    path = _path(target)
    return {'name': target['name'], 'type': target['type'], 'parent': parent, 'path': path,
            'depth': 0 if parent is None else 1 if parent == '.' else parent.count('/') + 2,
            'script': ext.get(target['script_id'], {}).get('path'), 'instance': instance,
            'unique_name': target['unique_name'],
            'parent_path': None if parent is None else rel_path_between(path, parent),
            'children': [_path(child) for child in nodes if rel_path_between(_path(child), path) == '..']}
