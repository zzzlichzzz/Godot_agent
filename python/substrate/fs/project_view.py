"""Short-lived Godot-read input for preparers which require a physical tree."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock

from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy, normalize_rel
from .godot_io import GodotFiles, MAX_BYTES

_index_base = None
_index_lock = RLock()


def view_addon(root, original, addon):
    """Preserve project-relative policy identity in a materialized view."""
    try: return str(Path(root) / Path(addon).resolve().relative_to(Path(original).resolve()))
    except ValueError: return str(addon)


def exact_inputs(action):
    """Inputs required by path-based native normalizers (engine dependencies are captured separately)."""
    if not isinstance(action,dict): return None
    kind = action.get('action')
    if kind in ('create_scene', 'edit_scene', 'edit_resource', 'edit_project_settings'):
        def paths(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key != 'summary': yield from paths(item)
            elif isinstance(value, list):
                for item in value: yield from paths(item)
            elif isinstance(value, str) and value.startswith('res://'):
                yield value[6:]
        return {'project.godot', *paths(action)}
    if kind in ('transaction', 'plan'):
        ops=action.get('operations', action.get('steps', [])); checks=action.get('checks', [])
        if not isinstance(ops,list) or not isinstance(checks,list): return set()
        groups = [exact_inputs(op) for op in ops]
        checked={c['path'][6:] for c in checks if isinstance(c,dict) and isinstance(c.get('path'),str) and c['path'].startswith('res://')}
        return None if None in groups else checked.union(*groups)
    if kind not in ('create_file', 'patch_file', 'move_file', 'delete_file'): return None
    paths = {p[6:] for p in (action.get('path'), action.get('dest')) if isinstance(p,str) and p.startswith('res://')}
    if kind == 'move_file': paths |= {p+'.uid' for p in paths}
    return paths


@contextmanager
def project_view(root, addon, *, action=None, allow_addons=False, allow_self_edit=False, indexed=False, suffixes=None):
    fs = GodotFiles(root, MAX_BYTES)
    policy = PathPolicy(root, allow_addons, allow_self_edit, addon)
    inputs = exact_inputs(action)
    if action and action.get('action') == 'rename_symbol': suffixes={'.gd','.uid','.tscn','.tres','.godot'} if action.get('kind')!='class_name' else None
    with TemporaryDirectory(prefix='godot-agent-view-') as folder:
        base = Path(folder)
        if base.is_relative_to(Path(root).resolve()):
            raise AppError('denied', 'Снимок должен находиться вне рабочего проекта')
        if inputs is None:
            def accept(row):
                rel = row['path']
                return (not any(s.casefold() in {'.godot','.git','.agent_history','__pycache__','node_modules'} for s in rel.split('/'))
                        and (policy.can_read(rel) or (rel=='addons' and allow_self_edit))
                        and (row['type']=='dir' or suffixes is None or Path(rel).suffix.lower() in suffixes))
            rows,cut=fs.list_entries_bounded('',accept,60000)
            if cut: raise AppError('unavailable','Снимок проекта превышает лимит обхода')
        else:
            rows=[]
            for rel in sorted(inputs):
                if not rel or normalize_rel(rel)!=rel: raise AppError('invalid_input','Некорректный путь: res://'+rel)
                if not policy.can_read(rel):
                    if policy.is_addon(rel): raise AppError('invalid_input','Изменение res://addons требует явного запроса пользователя и разрешённой политики доступа: res://'+rel)
                    raise AppError('denied','Путь действия закрыт')
                if fs.is_file(rel): rows.append(dict(path=rel,type='file'))
                elif fs.is_dir(rel): rows.append(dict(path=rel,type='dir'))
                else:
                    for parent in Path(rel).parents:
                        if parent!=Path('.') and fs.is_dir(parent.as_posix()):
                            rows.append(dict(path=parent.as_posix(),type='dir')); break
        total=0; fingerprint=hashlib.sha256(str(Path(root).resolve()).encode()) if indexed else None
        for row in rows:
            rel=row['path']; dest=base/rel
            if indexed: fingerprint.update(rel.encode()+b'\0'+row['type'].encode()+b'\0')
            if row['type']=='dir': dest.mkdir(parents=True,exist_ok=True); continue
            data=fs.read_raw(rel); total+=len(data)
            if indexed: fingerprint.update(hashlib.sha256(data).digest())
            if total>256*1024*1024: raise AppError('unavailable','Снимок проекта превышает лимит байтов')
            dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data)
        if not indexed:
            yield str(base); return
        # The reference index keys its cache by absolute root. Give identical input
        # the same private path, without retaining any project bytes between calls.
        global _index_base
        with _index_lock:
            if _index_base is None: _index_base=TemporaryDirectory(prefix='godot-agent-index-')
            fixed=Path(_index_base.name)/fingerprint.hexdigest()
            base.rename(fixed)
            try: yield str(fixed)
            finally: fixed.rename(base)
