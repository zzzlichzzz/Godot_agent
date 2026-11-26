"""Runtime composition: channels receive ports, never substrate imports."""
import builtins
from importlib import util
import os
from pathlib import Path
import sys
import uuid
from contextlib import contextmanager
from python.kernel.errors import AppError

class NativeServerReferences:
    def __init__(self,project_root,user_data_dir):
        self.project=str(Path(project_root).resolve());self.user_data=str(Path(user_data_dir).resolve())
        self._owner=uuid.uuid4().hex;self._modules={};self._api_cache=None

    def _load(self,stem,state=None):
        name='python.substrate.assistant.server._'+self._owner+'_'+stem
        path=Path(__file__).parents[1]/('substrate/assistant/server/'+stem+'.py')
        spec=util.spec_from_file_location(name,path);module=util.module_from_spec(spec)
        def native_import(import_name,globals=None,locals=None,fromlist=(),level=0):
            if import_name=='server_state' and level==0:return state or module
            return builtins.__import__(import_name,globals,locals,fromlist,level)
        module.__builtins__=dict(vars(builtins),__import__=native_import);sys.modules[name]=module
        try:spec.loader.exec_module(module)
        except BaseException:
            if sys.modules.get(name) is module:del sys.modules[name]
            raise
        self._modules[name]=module
        return module

    def activate(self):
        from python.substrate.assistant.native_bindings import NativeBindings
        from python.substrate.context.librarian_read import _LOCK
        with _LOCK:
            if self._modules:return self
            NativeBindings().register()
            server_state=self._load('server_state')
            server_auth=self._load('server_auth',server_state)
            dashboard=self._load('dashboard',server_state)
            routes=self._load('chat_routes',server_state)
            assert routes.S is server_state
            server_state.STATE.update(project_root=self.project,user_data_dir=self.user_data)
            self.state=server_state;self.auth=server_auth;self.dashboard=dashboard;self.routes=routes
            return self

    @contextmanager
    def scope(self):
        from python.substrate.assistant.native_planner import NativePlanner
        from python.substrate.assistant.chat_gateway import ChatGateway
        from python.substrate.panel_state import ExternalPanelState
        reader=NativePlanner(self.project,Path(self.user_data)/'rebuild_state',Path(__file__).parents[2])
        gateway=ChatGateway(self.project,self.user_data,Path(__file__).parents[2])
        with reader._references():
            from python.substrate.llm.api import api_keys, providers
            from python.substrate.llm.api.providers_fallback import scope as provider_scope
            gateway._guard_storage()
            files=ExternalPanelState(self.user_data,self.project)
            files.check(gateway.config_dir,directory=True)
            for name in ('api_keys.json','models_cache.json','catalog_cache.json'):
                files.check(gateway.config_dir/name);files.check(gateway.config_dir/(name+'.tmp'))
            env=api_keys.ENV_CONFIG_DIR;old_env=os.environ.get(env)
            previous=(api_keys._cfg_cache,api_keys._secrets_cache,api_keys._dirs_ready,api_keys._session_spent)
            try:
                os.environ[env]=str(gateway.config_dir)
                cache=self._api_cache or ({'key':False,'value':None},{'list':None},{},{})
                (api_keys._cfg_cache,api_keys._secrets_cache,api_keys._dirs_ready,api_keys._session_spent)=cache
                with provider_scope(providers):
                    yield
            finally:
                self.state.clear_request_activity()
                self._api_cache=(api_keys._cfg_cache,api_keys._secrets_cache,api_keys._dirs_ready,api_keys._session_spent)
                (api_keys._cfg_cache,api_keys._secrets_cache,api_keys._dirs_ready,api_keys._session_spent)=previous
                if old_env is None:os.environ.pop(env,None)
                else:os.environ[env]=old_env

    def bind_browser(self,gateway):
        self.state.get_driver=gateway.current_driver
        self.state.wait_driver=gateway.wait_driver
        self.state.browser_boot_started=gateway.browser_boot_started

    def index_status(self):
        import minilich
        return minilich.status(self.project,str(Path(__file__).parents[2]))

    def log_errors(self):
        import log_reader
        return log_reader.collect_errors(self.project,self.user_data)

    def rebuild_index(self):
        from python.substrate.context.librarian_read import LibrarianRead
        return LibrarianRead(self.project,Path(self.user_data)/'rebuild_state',Path(__file__).parents[2]).answer('индекс',12000)

def normalize_editor_snapshot(snapshot):
    from python.substrate.editor.references.editor_context import normalize_editor_snapshot as normalize
    return normalize(snapshot)

def build_http_agent(project,state,session,refs=None):
    from python.runtime.bootstrap import build_agent,default_ports
    from python.substrate.assistant.interactive_gateway import InteractiveGateway
    from python.substrate.llm.api import chat_store
    ports=default_ports(project,'cli',state_dir=state/'rebuild_state')
    def selected():
        explicit,_=session.turn_context.get()
        chat_id=explicit or (refs.state.STATE.get('current_chat_id') if refs is not None else None)
        record=chat_store.find_chat(str(state),chat_id) if chat_id else None
        if chat_id and record is None:raise AppError('not_found','Выбранный чат не найден')
        return record
    gateway=InteractiveGateway(project,state,Path(__file__).parents[2],selection=selected,
                               progress=session.report_progress,approved_read=session.approved_read)
    gateway.storage_base=state;ports['interactive_gateway']=gateway;session.gateway=gateway
    if refs is not None:refs.bind_browser(gateway)
    return build_agent(project_root=project,profile='cli',state_dir=state/'rebuild_state',ports=ports)
