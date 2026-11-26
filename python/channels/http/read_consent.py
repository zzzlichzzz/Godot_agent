"""One outstanding, chat-bound read; only server state supplies continuation data."""
import secrets
import time

from flask import jsonify, request

from .routes_panel import panel_chat_reply


def register_turns(bp, session, invoke):
    def run(text, chat, snap, limit, step=1, approved=None):
        turn=session.turn_context.set((chat,snap))
        consent=session.approved_read.set(approved)
        session.progress={};session.busy=True
        try:result=invoke('assistant_turn',dict(text=text,max_turns=limit))
        finally:
            session.busy=False;session.progress={}
            session.approved_read.reset(consent);session.turn_context.reset(turn)
        if isinstance(result,tuple):return result
        extra={}
        if result['state']=='pending_read':
            # An implicit first chat becomes an explicit destination before we offer data.
            owner=chat or (getattr(getattr(session,'gateway',None),'_record',None) or {}).get('id')
            if not owner:return jsonify(error='Выберите чат для чтения'),409
            action=result['action'].copy()
            if action.get('action')=='list_scene' and not ('path' in action or 'scene' in action):
                path=snap.get('scene',{}).get('active')
                if not path:return jsonify(error='Нет сохранённой активной сцены. Укажите путь к сцене.'),400
                action['path']=path
            ticket=dict(id=secrets.token_urlsafe(24),chat_id=owner,action=action,pause=step%8==0)
            session.ticket=(ticket,text,snap,limit,step,time.monotonic()+600)
            extra['read_request']=ticket
        if result['state']=='pending_confirmation':session.pending=result['plan']
        return jsonify(dict(result,ok=True,result=result['text'],response=result['text'],action=None,
                            preview=result['plan'],pending_confirmation=result['state']=='pending_confirmation',
                            **panel_chat_reply(result),**extra))

    @bp.post('/chat')
    def chat():
        body=request.get_json()
        text=next((body[k] for k in ('message','prompt','text') if k in body and body[k] is not None),'')
        with session.lock:
            if session.pending is not None:return jsonify(error='Resolve the pending preview first',kind='conflict'),409
            cid=body.get('chat_id')
            if cid is not None and not isinstance(cid,str):return jsonify(error='Invalid chat_id',kind='invalid_input'),400
            from python.runtime.http_services import normalize_editor_snapshot
            snap=normalize_editor_snapshot(body.get('editor_context',session.editor_snapshot))
            # Only the local path is necessary to resolve list_scene without a path.
            session.ticket=None
            return run(text,(cid or '').strip() or None,{'scene':snap.get('scene',{})},body.get('max_turns',8))

    @bp.post('/chat/read/decision')
    def read_decision():
        body=request.get_json()
        envelope={'project_root','user_data_dir','addon_dir','allow_addons','allow_self_edit','rename_mode','rename_unverified'}
        if type(body.get('approved')) is not bool or body.keys()-envelope-{'chat_id','request_id','approved'}:
            return jsonify(error='Expected a decision for the existing read request'),400
        with session.lock:
            record=session.ticket
            if record is None:return jsonify(error='Запрос на чтение уже закрыт'),409
            ticket,text,snap,limit,step,expires=record
            if expires<=time.monotonic():session.ticket=None;return jsonify(error='Время подтверждения истекло'),409
            if ticket['id']!=body.get('request_id') or ticket['chat_id']!=body.get('chat_id') or session.pending:
                return jsonify(error='Запрос или чат изменился'),409
            session.ticket=None
            if not body['approved']:
                msg='Чтение отклонено. Данные не отправлены.'
                return jsonify(ok=True,state='final',response=msg,answer=msg,pending_confirmation=False)
            return run(text,ticket['chat_id'],snap,limit,step+1,ticket['action'])
