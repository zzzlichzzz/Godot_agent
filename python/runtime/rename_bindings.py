"""Compose the shared binding analysis with the panel's prepared, isolated byte delta."""
import codecs
from python.formats import gdscript
from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.modules.code_intel.shared import symbol_index, bound_names
from python.modules.code_intel.usages.domain.core import build_query, locate
from python.substrate.fs.disk_fs import DiskFileSystem


def complete(root, action, prepared, policy):
    kind, old, new = action['kind'], action['old_name'], action['new_name']
    if kind not in ('function','signal'): return
    # root is the private materialized view (an explicit disk double in profile=test).
    fs = DiskFileSystem(root)
    index = symbol_index.build(fs, PathPolicy(root, **{k:v for k,v in policy.items() if k!='addon_dir'},
                                              agent_dir=policy['addon_dir']), scenes=True)
    decl = locate(symbol_index.declarations(index),build_query(kind,old,new,action['declaration']))
    if decl['owner'] != 'script': return
    existing = {f['path']:f for f in prepared['files']}
    # The panel also renames overriding declarations. Each such declaration owns
    # its own Callable/Signal references, including those in inheriting scenes.
    renamed_overrides = set()
    for entry in index['files']:
        row = existing.get(entry['path'])
        if not row or not row['after_bytes'] or entry['path'] == decl['path']: continue
        locations = {(d['line'],d['column']) for d in entry['declarations']
                     if d['kind']==kind and d['name']==old and d['owner']=='script'}
        if locations and any(d['kind']==kind and d['name']==new and d['owner']=='script' and
                             (d['line'],d['column']) in locations for d in
                             gdscript.parse(row['after_bytes'].decode('utf-8-sig'),entry['path'])['declarations']):
            renamed_overrides.add(entry['path'])
    owners = bound_names.script_owners(index,decl,renamed_overrides=renamed_overrides)
    excluded = set(prepared.get('excluded_places',()))
    for path, original in bound_names.sources(index, owners):
        if not any(bound_names.places(path,original,kind,old,owners)): continue
        row = existing.get(path)
        raw = row['before_bytes'] if row else fs.read_raw(path[6:])
        # The old scene planner only knew same-script connections and ignored exclude.
        # Merge with its delta except for excluded original fields (handled below).
        after = row['after_bytes'] if row else raw
        lines = after.decode('utf-8-sig').splitlines(True)
        def patch(line, col, source, replacement):
            at=col-1; text=lines[line-1]
            if text[at:at+len(source)]!=source: raise AppError('conflict','Устарела привязка: '+path)
            lines[line-1]=text[:at]+replacement+text[at+len(source):]
        for line,col,_ in reversed(list(bound_names.places(path,''.join(lines),kind,old,owners))):
            if (path,line) not in excluded: patch(line,col,old,new)
        if path.endswith('.tscn') and excluded:
            for line,col,_ in bound_names.places(path,original,kind,old,owners):
                if (path,line) in excluded: lines[line-1]=raw.decode('utf-8-sig').splitlines(True)[line-1]
        updated = (codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b'')+''.join(lines).encode('utf-8')
        if row: row['after_bytes']=updated
        elif updated!=raw: prepared['files'].append(dict(path=path,before_bytes=raw,after_bytes=updated))
