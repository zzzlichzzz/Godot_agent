"""A failed Arena send must not replay the full first-turn prompt or a restored draft."""
from types import SimpleNamespace

import pytest

from .test_browser_composers import ARENA_SEND, bind
from .test_studio_conversation import local_studio
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[{'https://arena.ai/*':ARENA_SEND}],indirect=True)
def test_one_insert_no_submit_on_mismatch_then_explicit_retry(local_studio,cold_tf6,monkeypatch):
    from python.substrate.llm.parsers.arena_delivery import ArenaDelivery
    browser=local_studio; post=bind(browser,cold_tf6,monkeypatch)
    mon=SimpleNamespace(chat_request_count=lambda:0,is_generating=lambda:False,
                        assistant_message_count=lambda:0,end_battle_capture=lambda:None)
    monkeypatch.setattr(ArenaDelivery,'_ensure_monitor',lambda *_:mon)
    monkeypatch.setattr(ArenaDelivery,'_arena_targets',lambda *_:{})
    monkeypatch.setattr(ArenaDelivery,'_follow_first_chat_transition',lambda *_:None)
    monkeypatch.setattr(ArenaDelivery,'extract_answer_snapshot',lambda *_:{})
    monkeypatch.setattr(ArenaDelivery,'wait_for_new_answer',lambda *_a,**_k:{'text':'OK. ===DONE==='})
    cid=post('/chats/new',site_id='arena')['current_id']
    assert post('/chat/live_input',chat_id=cid,text='draft',seq=1)['applied']
    browser.execute_script('''window.corrupt=true;pastes.length=0;field.addEventListener('input',()=>{
        if(window.corrupt && field.textContent.includes('agent_action')) field.lastChild.append('!');})''')
    result=post('/chat',chat_id=cid,prompt='draft')
    assert browser.execute_script('return [pastes.length,sent.length]')==[1,0],result
    assert result['kind']=='unavailable' and 'Arena' in result['error']
    before=browser.execute_script('return field.innerHTML')
    for seq,text in ((2,''),(3,'draft')):
        assert post('/chat/live_input',chat_id=cid,seq=seq,text=text)['reason']=='send_unresolved'
    assert browser.execute_script('return field.innerHTML')==before
    browser.execute_script('window.corrupt=false')
    retry=post('/chat',chat_id=cid,prompt='edited\n\tvalue')
    assert retry['ok'],retry
    sent,pasted=browser.execute_script('return [sent,pastes.at(-1)]')
    assert len(sent)==1 and sent[0][0]==pasted and pasted.endswith('edited\n\tvalue')


@pytest.mark.needs_live
@pytest.mark.parametrize('local_studio',[{'https://arena.ai/*':ARENA_SEND}],indirect=True)
def test_tab_draft_and_missing_monitor_leave_composer_untouched(local_studio,cold_tf6,monkeypatch):
    from python.substrate.llm.parsers.arena_delivery import ArenaDelivery
    browser=local_studio;post=bind(browser,cold_tf6,monkeypatch)
    cid=post('/chats/new',site_id='arena')['current_id']
    assert post('/chat/live_input',chat_id=cid,text='start',seq=1)['applied']
    browser.execute_script('window.keys=[]; document.addEventListener("keydown",e=>keys.push(e.key),true);pastes.length=0')
    result=post('/chat/live_input',chat_id=cid,text='start\n\tvalue',seq=2)
    assert not result['applied'] and result['reason']=='draft_local'
    monkeypatch.setattr(ArenaDelivery,'_ensure_monitor',lambda *_:None)
    failure=post('/chat',chat_id=cid,prompt='start\n\tvalue')
    assert failure['kind']=='unavailable' and 'Arena' in failure['error']
    assert browser.execute_script('return [field.textContent,keys,pastes,sent]')==['start',[],[],[]]
