"""Panel dispatch, real local judge and an isolated Chrome conversation; no public votes."""
import json
from types import SimpleNamespace

import pytest

from .test_browser_composers import ARENA_SEND, bind
from .test_studio_conversation import local_studio
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


PAGE = ARENA_SEND + '''<button id="direct" onclick="votes.push('B')">Continue with B</button>
<button id="battle" onclick="votes.push('B')">B лучше</button><button onclick="votes.push('skip')">Skip</button>
<script>window.votes=[];document.getElementById(location.pathname.endsWith('direct')?'battle':'direct').remove();
field.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey)field.innerHTML='<p><br class="ProseMirror-trailingBreak"></p>'});</script>'''


@pytest.mark.needs_live
@pytest.mark.parametrize('site',['arena','arena_battle'])
@pytest.mark.parametrize('local_studio',[{'https://arena.ai/*':PAGE}],indirect=True)
def test_valid_symbol_read_wins_once_and_is_logged(local_studio,cold_tf6,monkeypatch,site):
    from python.substrate.llm.parsers.arena_delivery import ArenaDelivery
    from python.substrate.llm.parsers.arena_parser import ArenaChatMonitor, ArenaParser

    browser=local_studio; post=bind(browser,cold_tf6,monkeypatch); state=cold_tf6[2]
    cdp=SimpleNamespace(on_event=lambda *a:None,is_alive=lambda:True)
    mon=ArenaChatMonitor(cdp)
    monkeypatch.setattr(ArenaParser,'_monitor',mon)
    monkeypatch.setattr(ArenaParser,'_choice_applied_for_request',None)
    monkeypatch.setattr(ArenaDelivery,'_ensure_monitor',lambda *_:mon)
    monkeypatch.setattr(ArenaDelivery,'_arena_targets',lambda *_:{})
    monkeypatch.setattr(ArenaDelivery,'_follow_first_chat_transition',lambda *_:None)
    action=dict(action='analyze_rename' if site=='arena' else 'find_symbol_usages',kind='function',old_name='hit')
    if site=='arena':action['new_name']='renamed'
    calls=[]; rename=dict(action,action='rename_symbol',declaration='res://hero.gd:6:6')
    def frame(action):return '```agent_action\n'+json.dumps(action)+'\n```\n===DONE==='
    def wait(parser,driver,*_,**kw):
        # Supply only the remote response frames; selection, rendering, and consent are real.
        calls.append(1)
        for i in range(2 if site=='arena_battle' else 1):
            mon._on_request_will_be_sent(dict(requestId=f'fixture-{len(calls)}-{i}',
                request=dict(url='https://arena.ai/'+mon.CHAT_URL_SUBSTR.lstrip('/'),method='POST')))
        mon._answer_request_count=mon.chat_request_count()
        mon._reset_answer_state_locked()
        texts=[frame(rename)] if len(calls)>1 else [frame(dict(action,kind=k)) for k in ('bogus','function')]
        for key,t in enumerate(texts):mon._apply_event(dict(kind='text',stream=key,text=t))
        mon._finish_collected_answer_locked('stop');mon._battle_finalized=True
        mon._active_request_id='still-open'
        assert parser.extract_answer(driver)['error'] and browser.execute_script('return votes.length')==len(calls)-1
        mon._active_request_id=None
        first=parser.extract_answer(driver)
        if len(texts)==2:mon.select_stream(0)  # A late structural fallback must not replace the winning text.
        assert parser.extract_answer(driver)==first and parser.answer_stream(driver)==texts[-1]
        return first
    monkeypatch.setattr(ArenaDelivery,'wait_for_new_answer',wait)
    cid=post('/chats/new',site_id=site)['current_id']
    response=post('/chat',chat_id=cid,prompt='private request')
    assert browser.execute_script('return votes')==['B'],response
    ticket=response['read_request'];assert ticket['action']==action
    assert response['battle_choice']['selected']=='B'
    path=state/'agent_turn_timings.json'; row=json.loads(path.read_bytes())[-1];event,=row['arena']
    assert row['arena_posts']==[2 if site=='arena_battle' else 1]
    assert event['decision']=='selected' and event['score_b']>event['score_a'] and event['variants']==2
    assert 'private' not in path.read_text('utf8')
    if site=='arena':
        script=state.parent/'project/hero.gd';before=script.read_bytes()
        next_reply=post('/chat/read/decision',chat_id=cid,request_id=ticket['id'],approved=True)
        assert next_reply.get('state')=='pending_confirmation' and 'battle_choice' not in next_reply,next_reply
        assert script.read_bytes()==before and next_reply['pending_action']['action']=='rename_symbol'
        event,=json.loads(path.read_bytes())[-1]['arena'];assert event==dict(mode='direct',variants=1,decision='single')
        assert len(calls)==2 and browser.execute_script('return votes')==['B']
        plan=next_reply['preview'];identity={k:plan[k] for k in ('plan_id','digest')}
        assert post('/chat/confirm_action',chat_id=cid,approved=True,**identity)['state']=='COMMITTED'
        assert script.read_bytes()==before.replace(b'func hit(',b'func renamed(')
        assert post('/chat/rollback')['ok'] and script.read_bytes()==before
