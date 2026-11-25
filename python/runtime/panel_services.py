"""IO ports for panel adapters; native references stay byte-exact and scoped."""
from importlib import import_module
from pathlib import Path
from threading import Lock
from python.substrate.assistant.native_planner import NativePlanner
from python.substrate.panel_state import ExternalPanelState

class PanelServices:
    def __init__(self,project,state):
        self.project=str(project);self.state=Path(state)
        self.reader=NativePlanner(project,self.state/'rebuild_state',Path(__file__).parents[2])
        self.files=ExternalPanelState(state,project)
        self._mirror=None;self._mirror_lock=Lock()

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
        with self.reader._references():
            history=import_module('python.substrate.store.history_manager')
            reader=import_module('python.substrate.editor.references.log_reader')
            self.files.check(self.state/'logs/godot.log');self.files.check(self.reader.history_dir/'log_state.json')
            return reader.collect_errors(str(self.state),self.project,history.get_storage_dir(self.project))

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

    def describe(self,action):
        with self.reader._references():
            policy=dict(allow_addons=False,allow_self_edit=False,addon_dir=self.reader.addon_dir)
            if action['action']=='rename_file':
                native=import_module('python.substrate.editing.file_refactor').prepare_file_rename(
                    self.project,action['old_path'],action['new_path'],update_references=action['update_references'],**policy)
                keys=('old_path','new_path','companion_script','is_directory','moved_files','reference_count','affected_paths')
                result={key:native.get(key) for key in keys}
            else:
                module=import_module('python.substrate.editing.node_refactor')
                base=[self.project,action['scene'],action['target_node_path']]
                if action['action']=='rename_node':native=module.prepare_node_rename(*base,action['new_name'],**policy)
                elif action['action']=='reparent_node':native=module.prepare_node_reparent(*base,action['new_parent'],**policy)
                else:native=module.prepare_node_deletion(*base,**policy)
                result=dict(scene=native['scene_res'],node_path=native['target_node_path'])
                for key in ('new_name','new_parent','reference_count','affected_paths','deleted_nodes','warnings','scripts_only'):
                    if key in native:result[key]=native[key]
            result['file_count']=len(native['files']);result['diffs']=[item['diff'] for item in native['files']]
            return result

    def live_input(self,data,session):
        def record():
            gw=getattr(session,'gateway',None);sel=getattr(gw,'_selection',None)
            return getattr(gw,'_record',None) or (sel() if callable(sel) else None) or {}
        def site():
            rec=record()
            if rec.get('kind')=='api':return None
            return import_module('python.substrate.llm.browser.sites').get_site(rec.get('site_id') or 'qwen')
        def parser():
            selected=site()
            if not selected:return None
            module=import_module('python.substrate.llm.parsers.'+selected['parser'])
            return getattr(module,'PARSER',module)
        def url():return record().get('url') or (site() or {}).get('new_chat_url')
        with self._mirror_lock:
            if self._mirror is None:
                from python.substrate.llm.browser.live_input import LiveInputMirror
                self._mirror=LiveInputMirror(
                    get_driver=lambda:getattr(session,'gateway',None).current_driver() if hasattr(getattr(session,'gateway',None),'current_driver') else None,
                    get_parser=parser,busy_fn=lambda:session.busy,prefer_url_fn=url)
        result=self._mirror.apply(data.get('seq'),data.get('text',''))
        if not result['ok']:result=dict(ok=False,applied=False,reason='Mirror unavailable')
        return result
