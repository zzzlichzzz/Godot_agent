"""IO ports for panel adapters; native references stay byte-exact and scoped."""
from importlib import import_module
from pathlib import Path
from python.kernel.errors import AppError
from python.substrate.panel_state import ExternalPanelState

class PanelServices:
    def __init__(self,project,state):
        from python.substrate.assistant.native_planner import NativePlanner
        self.project=str(project);self.state=Path(state)
        self.reader=NativePlanner(project,self.state/'rebuild_state',Path(__file__).parents[2])
        self.files=ExternalPanelState(state,project)
        self._mirror=None;self._mirror_target=None;self._reload_fences={}

    def cache(self,classes=None,version=''):
        with self.reader._references():
            module=import_module('python.substrate.engine.gd_api_cache')
            path=self.files.check(self.reader.history_dir/module.CACHE_FILENAME)
            previous=module._cache
            try:
                module._cache={'root':None,'classes':{},'godot_version':''}
                if classes is not None:
                    with self.files.native_output(module,path):
                        count=module.save_cache(self.project,classes,version,addon_dir=None)
                    return dict(classes_count=count,godot_version=version)
                value=module.get_cached_version(self.project,self.reader.addon_dir)
                return dict(cached_version=value,has_cache=bool(value) or module.has_cache(self.project,self.reader.addon_dir))
            finally:module._cache=previous

    def log_report(self):
        from python.substrate.fs.project_view import project_view
        with self.reader._references():
            history=import_module('python.substrate.store.history_manager')
            reader=import_module('python.substrate.editor.references.log_reader')
            self.files.check(self.state/'logs/godot.log');self.files.check(self.reader.history_dir/'log_state.json')
            with project_view(self.project,self.reader.addon_dir,suffixes={'.gd','.godot','.cs','.tscn','.tres'}) as root:
                return reader.collect_errors(str(self.state),root,history.get_storage_dir(self.project))

    def index(self, rebuild=False):
        from python.substrate.fs.project_view import project_view
        with self.reader._references():
            module=import_module('python.substrate.context.ml_project_index')
            path=self.files.check(self.reader.log_path.parent/module.INDEX_FILE)
            if rebuild:
                with project_view(self.project,self.reader.addon_dir,indexed=True,suffixes=module.EXTS | {'.godot'}) as root:
                    count=module.build_index(root)
                return dict(files=count)
            return dict(enabled=path.is_file(),training_active=False,disk_bytes=path.stat().st_size if path.is_file() else 0)

    def log_message(self,report):
        with self.reader._references():return import_module('python.substrate.editor.references.log_reader').format_log_report(report)

    def validate_log_write(self):
        for name in ('log_state.json','log_state.json.tmp'):self.files.check(self.reader.history_dir/name)

    def log_sent(self,report):
        with self.reader._references():
            history=import_module('python.substrate.store.history_manager')
            module=import_module('python.substrate.editor.references.log_reader');self.validate_log_write()
            with self.files.native_output(module,self.reader.history_dir/'log_state.json.tmp'):
                module.save_sent_fingerprint(history.get_storage_dir(self.project),report['fingerprint'])

    def log_summary(self,report):
        return import_module('python.substrate.editor.references.log_reader').build_summary(report)

    def preview_diffs(self, deltas):
        if not deltas: return []
        with self.reader._references():
            render=import_module('python.substrate.project.project_tools').build_diff_preview
            return [dict(path=row['path'], **(render(row['before'],row['after']) or {})) for row in deltas]

    def describe(self,action):
        from python.substrate.fs.project_view import project_view
        with self.reader._references(), project_view(self.project,self.reader.addon_dir) as root:
            policy=dict(allow_addons=False,allow_self_edit=False,addon_dir=self.reader.addon_dir)
            if action['action']=='rename_file':
                native=import_module('python.substrate.editing.file_refactor').prepare_file_rename(
                    root,action['old_path'],action['new_path'],update_references=action['update_references'],**policy)
                keys=('old_path','new_path','companion_script','is_directory','moved_files','reference_count','affected_paths')
                result={key:native.get(key) for key in keys}
            else:
                module=import_module('python.substrate.editing.node_refactor')
                base=[root,action['scene'],action['target_node_path']]
                if action['action']=='rename_node':native=module.prepare_node_rename(*base,action['new_name'],**policy)
                elif action['action']=='reparent_node':native=module.prepare_node_reparent(*base,action['new_parent'],**policy)
                else:native=module.prepare_node_deletion(*base,**policy)
                result=dict(scene=native['scene_res'],node_path=native['target_node_path'])
                for key in ('new_name','new_parent','reference_count','affected_paths','deleted_nodes','warnings','scripts_only'):
                    if key in native:result[key]=native[key]
            result['file_count']=len(native['files']);result['diffs']=[item['diff'] for item in native['files']]
            return result

    def selected_page(self, chat_id, session, *, reload=False, seq=None):
        from python.substrate.context.librarian_read import _LOCK
        busy = AppError('conflict', 'Браузер занят. Дождитесь окончания операции.')
        if not session.lock.acquire(blocking=False): raise busy
        try:
            if session.busy or not _LOCK.acquire(blocking=False): raise busy
            try:
                gateway = getattr(session, 'gateway', None)
                page = getattr(gateway, 'selected_page', None)
                record = gateway._selection() if page else None
                if not chat_id or not record or record.get('id') != chat_id or record.get('kind') == 'api':
                    raise AppError('conflict', 'Выберите открытый браузерный чат.')
                driver = gateway.current_driver()
                if not reload: return page.page_status(record, driver)
                page.reload(record, driver)
                if type(seq) is int and seq >= 0 and record.get('site_id') in ('arena','arena_battle'):
                    # Only edits made after this explicit navigation may reach the fresh document.
                    self._reload_fences[chat_id] = max(seq, self._reload_fences.get(chat_id, 0))
                    gateway._mirror_held.discard(chat_id)
                return dict(ok=True)
            finally: _LOCK.release()
        finally: session.lock.release()

    def live_input(self,data,session):
        from python.substrate.context.librarian_read import _LOCK
        def skipped(reason):return dict(ok=True,applied=False,reason=reason)
        if session.busy or not _LOCK.acquire(blocking=False):return skipped('busy')
        try:
            if session.busy:return skipped('busy')
            gateway=getattr(session,'gateway',None)
            driver=gateway.current_driver() if hasattr(gateway,'current_driver') else None
            if driver is None:return skipped('no_browser')
            selection=getattr(gateway,'_selection',None)
            rec=(selection() if callable(selection) else getattr(gateway,'_record',None)) or {}
            if not rec or rec.get('kind')=='api':return skipped('no_parser')
            if data.get('chat_id') and data['chat_id'] != rec.get('id'):return skipped('chat_changed')
            fence=self._reload_fences.get(rec.get('id'))
            if fence is not None and (type(data.get('seq')) is not int or data['seq'] <= fence):return skipped('stale_seq')
            if getattr(gateway,'selected_page',None):
                try:gateway.selected_page.require(rec,driver)
                except AppError:return skipped('history_only')
            from python.substrate.assistant.saved_page import site_for_record
            selected=site_for_record(rec)
            if not selected:return skipped('no_parser')
            url=rec.get('url') or selected['new_chat_url']
            if rec.get('id') in getattr(gateway,'_mirror_held',()):return skipped('send_unresolved')
            if selected['id']=='deepseek':
                from python.substrate.llm.parsers.deepseek_delivery import DeepSeekDelivery
                parser=DeepSeekDelivery(driver)
            elif selected['id']=='kimi':
                from python.substrate.llm.parsers.kimi_delivery import KimiDelivery
                parser=KimiDelivery(selected,driver)
            elif selected['id'] in ('arena','arena_battle'):
                from python.substrate.llm.parsers.arena_delivery import ArenaDelivery
                parser=ArenaDelivery(selected,driver,url)
            else:
                module=import_module('python.substrate.llm.parsers.'+selected['parser'])
                parser=getattr(module,'PARSER',module)
                if selected['id']=='aistudio':
                    from python.substrate.llm.parsers.studio_draft import StudioDraft
                    parser=StudioDraft(parser)
            self._mirror_target=(driver,parser,url)
            if self._mirror is None:
                from python.substrate.llm.browser.live_input import LiveInputMirror
                self._mirror=LiveInputMirror(get_driver=lambda:self._mirror_target[0],
                    get_parser=lambda:self._mirror_target[1],busy_fn=lambda:session.busy,
                    prefer_url_fn=lambda:self._mirror_target[2])
            result=self._mirror.apply(data.get('seq'),data.get('text',''))
            if not result['applied'] and getattr(parser,'draft_local',False):return skipped('draft_local')
            if result['ok']:return result
        except (AppError,OSError,RuntimeError,ValueError):
            pass
        finally:
            self._mirror_target=None
            _LOCK.release()
        return dict(ok=False,applied=False,reason='Mirror unavailable')
