"""HTTP adapter: all planning, confirmation and effects belong to Agent."""
from flask import Blueprint,jsonify,request
from .read_consent import register_turns

def register_chat_routes(app,agent,session):
    bp=Blueprint('rebuild_chat',__name__)
    def invoke(name,args):
        answer=agent.call(name,args)
        if not answer['ok']:
            return jsonify(dict(answer,error=answer.get('message','Request failed'))),409 if answer['kind'] in ('conflict','stale_plan') else 400
        return answer['result']
    register_turns(bp,session,invoke)
    @bp.post('/chat/confirm')
    def confirm():
        body=request.get_json()
        with session.lock:
            plan=session.pending
            if plan is None:return jsonify(error='No pending action',kind='not_found'),400
            args=dict(plan_id=body.get('plan_id',plan['plan_id']),digest=body.get('digest',plan['digest']),approved=body.get('approved'))
            if args['plan_id']!=plan['plan_id'] or args['digest']!=plan['digest']:
                return jsonify(error='Preview identity changed',kind='stale_plan'),409
            result=invoke('assistant_confirm',args)
            if isinstance(result,tuple):return result
            session.pending=None
            if result['state']=='COMMITTED':session.last_receipt=result
            text='Applied through the journal' if result['state']=='COMMITTED' else 'Rejected: no project file changed'
            return jsonify(dict(result,ok=True,message=text,**session.finish_preview_note(text),
                                plan_started=False,plan_finished=result['state']=='COMMITTED'))
    @bp.post('/chat/rollback')
    def rollback():
        body=request.get_json()
        with session.lock:
            receipt=session.last_receipt
            if receipt is None:return jsonify(error='No committed plan',kind='not_found'),400
            result=invoke('assistant_rollback',dict(plan_id=body.get('plan_id',receipt['plan_id']),entry_id=body.get('entry_id',receipt['entry_id'])))
            if isinstance(result,tuple):return result
            session.last_receipt=None
            return jsonify(dict(result,ok=True,message='Restored through the journal'))
    @bp.post('/chat/rollback/preview')
    def rollback_preview():
        receipt=session.last_receipt
        return jsonify(ok=receipt is not None,plan=receipt,error=None if receipt else 'No committed plan')
    @bp.post('/chat/plan/step')
    def plan_step():
        return jsonify(error='Plans are atomic: use explicit /chat/confirm',kind='conflict'),409
    @bp.post('/chat/plan/stop')
    def plan_stop():
        with session.lock:
            plan=session.pending
            if plan is None:return jsonify(ok=True,message='No pending plan')
            result=invoke('assistant_confirm',dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=False))
            if isinstance(result,tuple):return result
            session.pending=None;return jsonify(dict(result,ok=True,**session.finish_preview_note('Plan stopped')))
    @bp.post('/chat/plan/rollback_chain')
    def rollback_chain():return rollback()
    @bp.post('/chat/editor/sync')
    def editor_sync():
        from python.runtime.http_services import normalize_editor_snapshot
        snapshot=request.get_json().get('editor_snapshot',{})
        session.editor_snapshot=normalize_editor_snapshot(snapshot)
        return jsonify(ok=True)
    @bp.post('/chat/editor/dirty')
    def editor_dirty():return editor_sync()
    @bp.get('/chat/progress')
    def progress():return jsonify(ok=True,busy=session.busy,active=session.busy,pending_confirmation=session.pending is not None,**session.progress)
    @bp.post('/chat/stop')
    def stop():
        gateway=getattr(session,'gateway',None)
        stopped=gateway.stop() if hasattr(gateway,'stop') else False
        return jsonify(ok=bool(stopped),message='Stop requested' if stopped else 'No cancellable browser turn; API requests have bounded timeouts')
    @bp.post('/tools/call')
    def tools_call():
        body=request.get_json();return jsonify(agent.call(body.get('name'),body.get('args',{})))
    @bp.get('/tools/list')
    def tools_list():return jsonify(ok=True,tools=agent.tools())
    app.register_blueprint(bp)
