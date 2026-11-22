"""Frozen project URL payloads -> public Agent calls; no project writer here."""
from flask import Blueprint,jsonify,request
from python.kernel.errors import AppError
from .routes_panel import confirm_pending,panel_chat_reply

def register_project_routes(app,agent,session,services):
    bp=Blueprint('rebuild_project',__name__)
    @bp.errorhandler(AppError)
    def service_error(exc):
        return jsonify(ok=False,error=exc.message,kind=exc.kind),403 if exc.kind=='denied' else 409 if exc.kind=='conflict' else 400
    def failure(answer):
        return jsonify(dict(answer,error=answer.get('message','Request refused'))),409 if answer['kind'] in ('conflict','stale_plan') else 400
    def action(data,kind):
        if kind=='rename_file':
            return dict(action=kind,old_path=data.get('old_path'),new_path=data.get('new_path') or data.get('dest'),
                        update_references=bool(data.get('update_references',True)))
        if data.get('scripts_only') or data.get('previous_name') or data.get('cleanup_code',True) is not True:
            raise AppError('unavailable','Nondefault node options need a separately ported planner; nothing changed')
        value=dict(action=kind,scene=data.get('scene'),target_node_path=data.get('node_path') or data.get('node'))
        if kind=='rename_node':value['new_name']=data.get('new_name') or data.get('name')
        elif kind=='reparent_node':value['new_parent']=data.get('new_parent') or data.get('parent')
        return value
    def preview(kind):
        data=request.get_json()
        with session.lock:
            if session.pending is not None:return jsonify(ok=False,error='Resolve pending preview first',kind='conflict'),409
            try:requested=action(data,kind);prepared=services.describe(requested)
            except AppError as exc:return jsonify(ok=False,error=exc.message,kind=exc.kind),400
            except Exception:return jsonify(ok=False,error='Native refactor preparation refused',kind='invalid_input'),400
            answer=agent.call('assistant_plan',dict(action=requested))
            if not answer['ok']:return failure(answer)
            plan=answer['result']
            if plan['state']=='PREPARED':
                session.pending=plan;session.panel_preview=dict(action=requested,prepared=prepared,diffs=plan['diffs'],plan_id=plan['plan_id'],digest=plan['digest'])
            return jsonify(ok=True,prepared=prepared,preview=plan,pending_confirmation=plan['state']=='PREPARED')
    def apply(kind):
        with session.lock:
            bound=getattr(session,'panel_preview',None)
            if bound is None:return jsonify(ok=False,error='Run the matching preview first',kind='conflict'),409
            if session.pending is None or any(session.pending.get(key)!=bound[key] for key in ('plan_id','digest')):
                return jsonify(ok=False,error='Bound refactor preview is no longer pending',kind='stale_plan'),409
            try:requested=action(request.get_json(),kind)
            except AppError as exc:return jsonify(ok=False,error=exc.message,kind=exc.kind),400
            if requested!=bound['action']:return jsonify(ok=False,error='Refactor options changed; preview again',kind='stale_plan'),409
            data=request.get_json()
            confirmation={key:data[key] for key in ('plan_id','digest','exclude','editor_semantic_hash','dependency_fingerprint') if key in data}
            confirmation['approved']=data.get('approved',True)  # Explicit native Apply button, not automatic notification.
            body,status=confirm_pending(agent,session,confirmation)
            if status==200:
                prepared=bound['prepared'];body.update({key:prepared[key] for key in (
                    'old_path','new_path','reference_count','file_count') if key in prepared})
                body['changed_paths']=[item['path'] for item in bound['diffs']] if body['state']=='COMMITTED' else []
                body['entry_id']=body.get('history_entry_id') or None
            return jsonify(body),status
    @bp.post('/project/refactor/file/preview')
    def file_preview():return preview('rename_file')
    @bp.post('/project/refactor/file/apply')
    def file_apply():return apply('rename_file')
    @bp.post('/scene/refactor/node/preview')
    def node_preview():return preview('rename_node')
    @bp.post('/scene/refactor/node/apply')
    def node_apply():return apply('rename_node')
    @bp.post('/scene/refactor/node/reparent/preview')
    def reparent_preview():return preview('reparent_node')
    @bp.post('/scene/refactor/node/reparent/apply')
    def reparent_apply():return apply('reparent_node')
    @bp.post('/scene/refactor/node/delete/preview')
    def delete_preview():return preview('delete_node')
    @bp.post('/scene/refactor/node/delete/apply')
    def delete_apply():return apply('delete_node')
    @bp.post('/project/refactor/file/post_move_sync')
    def post_move_sync():
        return jsonify(ok=False,kind='conflict',requires_confirmation=True,
                       error='Automatic move notifications cannot approve writes; use an explicit WAL preview/confirmation'),409
    @bp.post('/project/split_gd/scan')
    @bp.post('/project/split_gd/plan')
    def split_preview():
        data=request.get_json();path=data.get('file','')
        if not isinstance(path,str) or not path.startswith('res://'):
            return jsonify(ok=False,error='Use a res:// .gd path inside the addon',kind='invalid_input'),400
        if not path.startswith('res://addons/godot_agent/'):
            return jsonify(ok=False,error='Native split scope is the agent addon only',kind='denied'),400
        tool='split_gd_scan' if request.path.endswith('/scan') else 'split_gd_plan';args=dict(path=path)
        for key in ('groups','target_lines'):
            if key in data and tool=='split_gd_plan':args[key]=data[key]
        answer=agent.call(tool,args)
        if not answer['ok']:return failure(answer)
        return jsonify(ok=True,**{'scan' if tool=='split_gd_scan' else 'plan':answer['result']})
    @bp.post('/project/split_gd/apply')
    def split_apply():return jsonify(ok=False,error='No sanctioned split WAL preview; addon/self-edit is disabled',kind='conflict'),409
    @bp.post('/librarian/query')
    def librarian_query():
        answer=agent.call('ask',dict(query=str(request.get_json().get('query') or '')))
        if not answer['ok']:return failure(answer)
        return jsonify(success=True,answer=answer['result'])
    @bp.post('/project/api_cache_status')
    def api_cache_status():return jsonify(services.cache())
    @bp.post('/project/update_api_cache')
    def update_api_cache():
        data=request.get_json();classes=data.get('classes')
        if not isinstance(classes,dict) or not classes:return jsonify(error='Empty or invalid class dictionary',kind='invalid_input'),400
        return jsonify(services.cache(classes,str(data.get('godot_version',''))))
    @bp.post('/project/check_log')
    def check_log():
        with session.lock:
            if session.pending is not None:return jsonify(error='Resolve pending confirmation first',kind='conflict'),409
            ok,report=services.log_report()
            if not ok:return jsonify(error='No readable project log',kind='not_found'),404
            info='%s (%s min ago)' % (report['log_time'],report['age_minutes'])
            if not report['errors']:return jsonify(found=0,log_time=info)
            if report['already_sent']:return jsonify(error='Log already sent; run the game again',kind='conflict'),409
            session.pending_log_report=report
            return jsonify(found=len(report['errors']),log_time=info,summary=services.log_summary(report))
    @bp.post('/project/send_log_errors')
    def send_log_errors():
        with session.lock:
            report=getattr(session,'pending_log_report',None)
            if report is None:return jsonify(error='No prepared log report; check log first',kind='invalid_input'),400
            if session.pending is not None:return jsonify(error='Resolve pending confirmation first',kind='conflict'),409
            services.validate_log_write()
            session.busy=True
            try:answer=agent.call('assistant_turn',dict(text=services.log_message(report),max_turns=8))
            finally:session.busy=False
            if not answer['ok']:return failure(answer)
            result=answer['result']
            if result['state']=='pending_confirmation':session.pending=result['plan']
            services.log_sent(report);session.pending_log_report=None
            return jsonify(dict(result,ok=True,**panel_chat_reply(result)))
    app.register_blueprint(bp)
