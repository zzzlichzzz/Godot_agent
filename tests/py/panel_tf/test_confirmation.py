"""Native button payload is not the digest-bearing public tool contract."""
import pytest
from tests.py.transfer_t1.test_write import physical

def turn(http_client):
    client,_,project,_,headers=http_client
    before=physical(project)
    answer=client.post('/chat',json={'text':'Создай.'},headers=headers)
    assert answer.status_code==200,answer.get_json()
    return answer.get_json(),before

def test_native_chat_exposes_pending_card_without_an_editor_writer(http_client):
    body,before=turn(http_client)
    assert body['answer']==body['text']
    assert body['pending_action']['action']=='transaction'
    assert body['pending_action']['paths']==['res://new.gd']
    assert body['pending_action_description'] and body['preview']['digest']
    assert 'editor_action' not in body and physical(http_client[2])==before

@pytest.mark.parametrize('approved',[True,False],ids=['approve','reject'])
def test_native_approved_only_button_uses_bound_preview_wal(http_client,approved):
    _,before=turn(http_client)
    client,_,project,_,headers=http_client
    response=client.post('/chat/confirm_action',json={'approved':approved},headers=headers)
    assert response.status_code==200,response.get_json()
    body=response.get_json();assert body['state']==('COMMITTED' if approved else 'REJECTED')
    assert body['pending_action'] is None and body['answer'] and not body['plan_started']
    if approved:
        assert body['history_entry_id']==body['entry_id'] and (project/'new.gd').exists()
        assert client.post('/chat/rollback',json={},headers=headers).status_code==200
    assert physical(project)==before
    assert client.post('/chat/confirm_action',json={'approved':True},headers=headers).status_code==400

@pytest.mark.parametrize('extra',[{'digest':'0'*64},{'digest':None},{'plan_id':'foreign'},
    {'exclude':['res://new.gd:1']},{'editor_semantic_hash':'forged'}],ids=['wrong-digest','null-digest','foreign-id','exclude-repreview','no-editor-proof'])
def test_changed_native_confirmation_cannot_apply(http_client,extra):
    _,before=turn(http_client)
    client,_,project,_,headers=http_client
    response=client.post('/chat/confirm_action',json=dict(approved=True,**extra),headers=headers)
    assert response.status_code in (400,409),response.get_json()
    assert physical(project)==before

def test_missing_server_digest_is_not_approval(http_client):
    turn(http_client)
    client,_,project,_,headers=http_client;before=physical(project)
    client.application.extensions['godot_session'].pending.pop('digest')
    response=client.post('/chat/confirm_action',json={'approved':True},headers=headers)
    assert response.status_code==409 and physical(project)==before
