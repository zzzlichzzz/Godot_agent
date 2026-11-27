"""Opt-in native read/prepare adapter. Project effects are compiled elsewhere."""
from contextlib import contextmanager
from importlib import import_module
import os
import stat
from python.kernel.errors import AppError
from python.kernel.paths import normalize_rel
from python.substrate.context.librarian_read import LibrarianRead, _LOCK
from .native_bindings import NativeBindings
from python.substrate.fs.project_view import view_addon

class NativePlanner(LibrarianRead):
    complete_bindings = None
    check_rename = None
    def __init__(self,project_root,state_dir,addon_dir,engine_overlay=None):
        super().__init__(project_root,state_dir,addon_dir)
        self._engine_overlay=engine_overlay

    @contextmanager
    def _references(self):
        self._guard_storage()
        with _LOCK:
            NativeBindings().register()
            data=import_module('python.substrate.context.ml_data')
            history=import_module('python.substrate.store.history_manager')
            cache=import_module('python.substrate.engine.gd_api_cache')
            old=(data._BASE_OVERRIDE,history._STORAGE_OVERRIDE,cache._migrate_legacy_addon_cache)
            try:
                cache._migrate_legacy_addon_cache=lambda _addon:None
                history.set_storage_dir(str(self.storage_base));data.set_storage_base(str(self.storage_base))
                self._guard_storage();yield
            finally:
                data._BASE_OVERRIDE,history._STORAGE_OVERRIDE,cache._migrate_legacy_addon_cache=old

    def prepare(self,action,*,allow_addons=False,allow_self_edit=False):
        prepared=self._prepare(action,allow_addons=allow_addons,allow_self_edit=allow_self_edit)
        parents=set()
        root=os.path.normcase(os.path.realpath(self._project))
        for item in prepared['files']:
            if item['after_bytes'] is None or item['before_bytes']==item['after_bytes']:continue
            path=item['path'];rel=normalize_rel(path[6:] if path.startswith('res://') else '')
            if not rel or ':' in rel or path!='res://'+rel:raise AppError('denied','некорректный путь плана')
            parts=rel.split('/')[:-1]
            for index in range(1,len(parts)+1):
                parent='/'.join(parts[:index]);full=os.path.join(self._project,*parts[:index])
                if os.path.commonpath((root,os.path.normcase(os.path.realpath(full))))!=root:
                    raise AppError('denied','parent-каталог вне проекта')
                try:info=os.lstat(full)
                except FileNotFoundError:parents.add('res://'+parent);continue
                if not stat.S_ISDIR(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                    raise AppError('denied','parent должен быть обычным каталогом')
        return dict(prepared,parents=sorted(parents,key=lambda p:(p.count('/'),p)))

    def _prepare(self,action,*,allow_addons=False,allow_self_edit=False):
        kwargs=dict(allow_addons=allow_addons,allow_self_edit=allow_self_edit,addon_dir=self.addon_dir)
        with self._references(), self.view(action=action,allow_addons=allow_addons,allow_self_edit=allow_self_edit) as root:
            kwargs['addon_dir']=view_addon(root,self._project,self.addon_dir)
            try:
                kind=action['action']
                if kind=='project_command':
                    action=import_module('python.substrate.assistant.high_level_actions').compile_action(root,action,**kwargs)
                    kind=action['action']
                if kind in ('rename_file','rename_symbol'):
                    from .native_actions import refactor
                    prepared = refactor(root,action,kwargs)
                    if kind=='rename_symbol' and self.check_rename:
                        self.check_rename(action,allow_addons=allow_addons,allow_self_edit=allow_self_edit)
                    if kind=='rename_symbol' and self.complete_bindings:
                        self.complete_bindings(root,action,prepared,kwargs)
                    return prepared
                if kind in ('create_file','patch_file','move_file','transaction','plan'):
                    if kind=='plan':
                        if action.get('continues'): raise AppError('invalid_input','получите все части плана до предпросмотра')
                        request={'action':'transaction','operations':action.get('steps'),'summary':action.get('description','')}
                    elif kind=='transaction': request=action
                    else: request={'action':'transaction','operations':[action]}
                    prepared=import_module('python.substrate.editing.transaction_actions').prepare(root,request,**kwargs)
                    return {'files':prepared.get('files',[]),'warnings':[]}
                if kind in ('rename_node','reparent_node','delete_node'):
                    module=import_module('python.substrate.editing.node_refactor')
                    base=[root,action['scene'],action.get('target_node_path') or action.get('node')]
                    if kind=='rename_node': prepared=module.prepare_node_rename(*base,action['new_name'],**kwargs)
                    elif kind=='reparent_node': prepared=module.prepare_node_reparent(*base,action['new_parent'],**kwargs)
                    else: prepared=module.prepare_node_deletion(*base,**kwargs)
                    return {'files':prepared['files'],'warnings':prepared.get('warnings',[])}
                if kind in ('edit_scene','create_scene','edit_resource','edit_project_settings'):
                    if self._engine_overlay is None: raise AppError('unavailable','структурный исполнитель Godot не подключён')
                    area={'edit_scene':'editing.scene_actions','create_scene':'editing.scene_actions',
                          'edit_resource':'editing.resource_actions','edit_project_settings':'project.project_settings_actions'}[kind]
                    normalized,_=import_module('python.substrate.'+area).normalize_action(root,action,**kwargs)
                    files,warnings=self._engine_overlay.prepare(normalized)
                    return {'files':files,'warnings':warnings}
                raise AppError('invalid_input','неподдерживаемое действие: '+kind)
            except AppError: raise
            except (ValueError,KeyError,TypeError,OSError) as error:
                raise AppError('invalid_input',str(error)) from None
            except Exception as error:
                # Native domain error classes do not share a base ValueError.
                if type(error).__module__.startswith(('python.substrate.','node_refactor','transaction_actions')):
                    raise AppError('invalid_input',str(error)) from None
                raise
