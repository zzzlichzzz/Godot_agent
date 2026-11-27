"""Preserve the native protected-override veto without exporting protected sources."""
from python.formats import gdscript
from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.modules.code_intel.usages.domain.core import build_query, declaration_kind


class HierarchyGuard:
    def __init__(self, fs, addon):
        self.fs = fs
        self.addon = addon

    def __call__(self, action, *, allow_addons=False, allow_self_edit=False):
        policy = PathPolicy(self.fs.project_root, allow_addons, allow_self_edit, self.addon)
        query = build_query(action['kind'], action['old_name'], action['new_name'], action['declaration'])
        if not policy.can_read(query.path[6:]): raise AppError('denied', 'Путь объявления закрыт')
        source = self.fs.read_text(query.path[6:])
        kind = declaration_kind(query.kind)
        decls = gdscript.parse(source,query.path)['declarations']
        if not any(d['kind']==kind and d['name']==query.old_name and d['owner']=='script' and
                   d['line']==query.line and (query.column is None or d['column']==query.column) for d in decls): return
        classes = {d['name'] for d in decls if d['kind']=='class_name'}
        def include(row):
            path = row['path']
            if row['type'] != 'dir': return policy.protected_override_candidate(path)
            return (policy.is_addon(path) or policy.is_agent(path) or
                    (policy._agent_rel or '').startswith(path+'/')) and path.split('/')[-1] not in (
                        '.godot','.git','.import','.agent_history','__pycache__','node_modules')
        try:
            rows, cut = self.fs.list_entries_bounded('', include, 60000)
            if cut: raise OSError('scan limit')
            total = 0
            for row in rows:
                if row['type'] != 'file': continue
                path = 'res://'+row['path']; raw = self.fs.read_raw(row['path']); total += len(raw)
                if total > 64*1024*1024: raise OSError('byte limit')
                if query.old_name.encode() not in raw: continue
                text = raw.decode('utf-8-sig'); parent, name = gdscript.script_parent(text,path)
                if parent != query.path and name not in classes: continue
                if any(d['owner']=='script' and d['kind']==kind and d['name']==query.old_name
                       for d in gdscript.parse(text,path)['declarations']):
                    raise AppError('conflict','Вне зоны записи есть подкласс с переопределением; переименование остановлено')
        except (OSError,UnicodeError):
            raise AppError('conflict','Невозможно проверить целостность закрытых подклассов') from None
