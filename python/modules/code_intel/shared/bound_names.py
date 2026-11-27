"""Identifiers stored as names by Godot, with a statically known endpoint."""
import re

from python.formats import gdscript, tscn


def script_owners(index, declaration, *, renamed_overrides=()):
    """A nearer declaration owns the name unless that override is itself being renamed."""
    owners = {declaration['path']}
    classes = {}
    for entry in index['files']:
        for d in entry['declarations']:
            if d['kind'] == 'class_name': classes.setdefault(d['name'], []).append(entry['path'])
    while True:
        count = len(owners)
        for entry in index['files']:
            parents = [entry['parent_path']] if entry['parent_path'] else classes.get(entry['parent_class'], [])
            if len(parents) == 1 and parents[0] in owners and (entry['path'] in renamed_overrides or not any(
                    d['owner'] == 'script' and d['name'] == declaration['name'] for d in entry['declarations'])):
                owners.add(entry['path'])
        if len(owners) == count: return owners


def _script(text, path, kind, name):
    ctor = 'Callable' if kind == 'function' else 'Signal'
    if ctor not in text: return
    parsed = gdscript.parse(text, path)
    decls = {d['id']: d for d in parsed['declarations']}
    if any(d['name'] == ctor for d in decls.values()): return
    refs = {r['start']: r['owner'] for r in parsed['references'] if r['name'] == 'self'}
    tokens = [t for t in gdscript.tokenize(text) if t['kind'] not in ('newline', 'comment')]
    for i,t in enumerate(tokens):
        if t['value'] != ctor or (i and tokens[i-1]['value'] == '.'): continue
        if [x['value'] for x in tokens[i+1:i+4]] != ['(', 'self', ',']: continue
        j = i+4
        if j < len(tokens) and tokens[j]['value'] == '&': j += 1
        if j+1 >= len(tokens) or tokens[j+1]['value'] != ')': continue
        lit = tokens[j]
        if lit['kind'] != 'string' or lit['value'] not in ('"'+name+'"', "'"+name+"'"): continue
        owner = refs.get(tokens[i+2]['start'])
        while owner in decls and decls[owner]['kind'] != 'class': owner = decls[owner]['owner']
        if owner == 'script': yield lit['line'], lit['column']+1, ctor.lower()


def _scene(text, kind, name, owners):
    ext, nodes, _ = tscn.fields(text)
    endpoints = {n['path'] for n in nodes if ext.get(n['script_id'], {}).get('type') == 'Script'
                 and ext[n['script_id']]['path'] in owners}
    if not endpoints: return
    field, endpoint = ('method','to') if kind == 'function' else ('signal','from')
    for line, row in enumerate(text.splitlines(), 1):
        if not row.lstrip().startswith('[connection ') or not row.rstrip().endswith(']'): continue
        attrs = {m[1]: m for m in re.finditer(r'\s(\w+)="([^"\\]*)"',row)}
        if field in attrs and attrs[field][2] == name and endpoint in attrs and attrs[endpoint][2] in endpoints:
            yield line, attrs[field].start(2)+1, 'scene_connection'


def places(path, text, kind, name, owners):
    if path.endswith('.tscn'): return _scene(text,kind,name,owners)
    return _script(text,path,kind,name) if path in owners else ()


def sources(index, owners):
    yield from ((e['path'], e['text']) for e in index['files'] if e['path'] in owners)
    yield from index.get('scenes', {}).items()
