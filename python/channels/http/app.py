"""Authenticated loopback HTTP transport over one rebuild Agent."""
from pathlib import Path
from flask import Flask,jsonify,request,g
from python.runtime.chrome_paths import configure_chrome_env
from python.runtime.http_services import NativeServerReferences,build_http_agent
from .auth import ProjectAuth
from .routes_chat import register_chat_routes
from .routes_panel import register_panel_routes;from .routes_project import register_project_routes
from python.runtime.panel_services import PanelServices

from .session import HttpSession

def create_app(project_root,state_dir,agent=None,native_routes=True):
    configure_chrome_env();project=Path(project_root).resolve();state=Path(state_dir).resolve()
    auth=ProjectAuth(project,state);app=Flask(__name__);auth.install(app)
    session=HttpSession()
    refs=NativeServerReferences(project,state).activate() if native_routes else None
    if agent is None:agent=build_http_agent(project,state,session,refs)
    app.extensions.update(godot_agent=agent,godot_session=session)
    if refs:
        @app.before_request
        def enter_native_scope():
            if request.blueprint!=refs.routes.chats_bp.name and request.endpoint not in ('dashboard_data','log_errors','rebuild'):
                return
            scope=refs.scope();scope.__enter__();g.godot_native_scope=scope
        @app.teardown_request
        def leave_native_scope(error):
            scope=g.pop('godot_native_scope',None)
            if scope:scope.__exit__(None,None,None)
    services=PanelServices(project,state)
    register_chat_routes(app,agent,session,services.preview_diffs)
    register_panel_routes(app,agent,session,services);register_project_routes(app,agent,session,services)
    @app.get('/health')
    def health():return jsonify(ok=True,name='Godot_Agent_Server',write_confirmation_required=True,provider_live_verified=False)
    @app.post('/init')
    def initialize():
        data=request.get_json() or {}
        if data.get('allow_addons') or data.get('allow_self_edit'):
            return jsonify(ok=False,kind='denied',message='HTTP cannot elevate startup policy'),403
        return jsonify(ok=True,project_root=str(project),write_confirmation_required=True)
    if refs:
        app.extensions['native_references']=refs
        refs.auth.install(app,jsonify)
        from .routes_panel import present_history
        refs.routes.chats_bp.after_request(present_history)
        app.register_blueprint(refs.routes.chats_bp)
        @app.get('/dashboard')
        def dashboard_page():return app.response_class(refs.dashboard.DASHBOARD_HTML,mimetype='text/html')
        @app.get('/dashboard/data')
        def dashboard_data():
            with session.lock:
                pending=bool(session.pending)
                try:status=services.index()
                except Exception:status={'error':'Index status unavailable'}
                return jsonify(uptime=refs.dashboard.uptime_text(),project_root=refs.project,
                    pending_action=pending,plan=dict(active=pending,index=0,total=int(pending)),
                    minilich=status,log=refs.dashboard.get_lines())
        @app.get('/dashboard/state')
        def dashboard_state():return jsonify(ok=True,state={'project_root':str(project),'chat_busy':session.busy,'provider_live_verified':False})
        @app.post('/project/log/errors')
        def log_errors():return jsonify(services.log_report())
        @app.post('/librarian/index/rebuild')
        def rebuild():return jsonify(ok=True,result=services.index(rebuild=True))
    @app.errorhandler(Exception)
    def unexpected(_error):return jsonify(ok=False,kind='internal',message='HTTP request failed; details redacted'),500
    return app
def serve(project_root,state_dir,port=0):
    from .listener import serve as listen;configure_chrome_env()
    return listen(create_app(project_root,state_dir),project_root,state_dir,port)
def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Godot Agent owned local HTTP channel')
    parser.add_argument('--project',required=True);parser.add_argument('--state',required=True)
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args(argv)
    try:serve(args.project,args.state,port=args.port)
    except (OSError,ValueError):parser.exit(2,'HTTP startup refused: invalid external profile or listener configuration\n')
    return 0
