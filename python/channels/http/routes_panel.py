"""Native panel control payloads over the authenticated server-owned session."""
import re
from flask import Blueprint,current_app,jsonify,request
from python.kernel.errors import AppError
from .rename_report import offer

def rename_label(action):
    return ('Переименование %s → %s' % (action['old_name'],action['new_name'])
            if action and action.get('action')=='rename_symbol' else '')

def receipt(plan,result):
    if result['state']!='COMMITTED': return 'Отклонено. Файлы проекта не изменены.',[]
    # A committed move is a single journal step but changes both names on disk.
    paths=list(dict.fromkeys([row['path'] for row in result['result']['applied']]+[d['path'] for d in plan.get('diffs',[])]))
    label=plan.get('rename_label','Изменения')+' — применено. Изменённые файлы:'
    return '\n'.join([label,*paths,*plan.get('warnings',[])]),paths

def panel_chat_reply(result,preview_diffs):
    plan=result.get('plan')
    paths=[item['path'] for item in (plan or {}).get('diffs',[])]
    pending=dict(action='transaction',paths=paths) if result.get('state')=='pending_confirmation' else None
    label=rename_label(result.get('action'))
    if pending and label: pending['action']='rename_symbol'
    return dict(answer=result['text'],pending_action=pending,
                pending_action_description='\n'.join([label or 'Предпросмотр изменений:',*paths,*(plan or {}).get('warnings',[])]),
                pending_action_diffs=preview_diffs((plan or {}).get('diffs',[])))

def confirm_pending(agent,session,body):
    plan=session.pending
    if plan is None:return dict(ok=False,error='No pending action',kind='not_found'),400
    if (not isinstance(plan.get('plan_id'),str) or not isinstance(plan.get('digest'),str)
            or re.fullmatch(r'[0-9a-f]{64}',plan['digest']) is None):
        return dict(ok=False,error='Server preview identity missing',kind='stale_plan'),409
    if body.get('plan_id',plan['plan_id'])!=plan['plan_id'] or body.get('digest',plan['digest'])!=plan['digest']:
        return dict(ok=False,error='Preview identity changed',kind='stale_plan'),409
    if 'chat_id' in body and session.pending_chat and body['chat_id']!=session.pending_chat:
        return dict(ok=False,error='Preview chat changed',kind='stale_plan'),409
    if body.get('exclude') or any(key in body for key in ('editor_semantic_hash','dependency_fingerprint')):
        return dict(ok=False,error='Changed selection requires a new immutable preview',kind='stale_plan'),409
    if type(body.get('approved')) is not bool:
        return dict(ok=False,error='Explicit boolean approval required',kind='invalid_input'),400
    answer=agent.call('assistant_confirm',dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=body['approved']))
    if not answer['ok']:
        return dict(answer,error=answer.get('message','Confirmation refused')),409 if answer['kind'] in ('conflict','stale_plan') else 400
    result=answer['result'];session.pending=None;session.panel_preview=None
    if result['state']=='COMMITTED':session.last_receipt=result
    text,paths=receipt(plan,result)
    saved=offer(session,plan,result,paths);saved.update(session.finish_preview_note(text))
    return dict(result,**saved,ok=True,answer=text,message=text,pending_action=None,plan_started=False,
                plan_finished=result['state']=='COMMITTED',changed_paths=paths,history_entry_id=result.get('entry_id')),200

def register_panel_routes(app,agent,session,services):
    bp=Blueprint('rebuild_panel',__name__)
    @bp.post('/chat/confirm_action')
    def confirm_action():
        with session.lock:
            body,status=confirm_pending(agent,session,request.get_json())
            return jsonify(body),status
    @bp.post('/chat/editor_action/result')
    def editor_result():
        data=request.get_json()
        if data.get('editor_action_kind','scene') not in ('scene','project_settings','resource'):
            return jsonify(ok=False,error='Unknown editor transaction kind',kind='invalid_input'),400
        return jsonify(ok=False,error='No issued native editor transaction; server effects use WAL',kind='conflict'),409
    @bp.post('/chat/runtime_check/bind')
    @bp.post('/chat/runtime_check/result')
    @bp.post('/chat/runtime_inspect/result')
    def runtime_result():
        data=request.get_json()
        if request.path.endswith('/result') and (
            not isinstance(data.get('request_id'),str) or not data['request_id'] or
            not isinstance(data.get('result_token'),str) or not data['result_token'] or not data['result_token'].isascii() or
            type(data.get('session_id',-1)) is not int or not isinstance(data.get('run_id',''),str) or
            not isinstance(data.get('status','protocol_error'),str)):
            return jsonify(ok=False,error='Invalid runtime result metadata',kind='invalid_input'),400
        return jsonify(ok=False,error='No issued runtime request; result not adopted',kind='conflict'),409
    @bp.post('/chat/live_input')
    def live_input():
        return jsonify(services.live_input(request.get_json(),session))
    @bp.post('/browser/reload')
    def reload_page():
        data=request.get_json()
        try: return jsonify(services.selected_page(data.get('chat_id'), session, reload=True, seq=data.get('seq')))
        except AppError as error:
            return jsonify(ok=False, kind=error.kind, error=error.message), 503 if error.kind=='unavailable' else 409
    @bp.post('/browser/page_status')
    def page_status():
        try: return jsonify(services.selected_page(request.get_json().get('chat_id'), session))
        except AppError: return jsonify(ready=False)
    @bp.post('/minilich/github_fetch')
    @bp.post('/minilich/set')
    @bp.post('/minilich/status')
    def excluded_nn():
        return jsonify(ok=False,kind='unavailable',error='Minilich neural networks and GitHub fetch are excluded (F0); nothing was started'),503
    @bp.post('/server/shutdown')
    def shutdown():
        callback=current_app.extensions.get('godot_shutdown')
        if callback is None:return jsonify(ok=False,kind='unavailable',error='No owned listener to shut down'),503
        callback()
        return jsonify(ok=True,message='Server shutting down')
    app.register_blueprint(bp)
