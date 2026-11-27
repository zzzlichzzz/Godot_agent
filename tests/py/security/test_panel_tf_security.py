"""SEC-TF: new routes preserve auth/policy; explicit native apply still uses WAL."""
import pytest
from tests.py.panel_tf.test_panel_route_contract import MISSING
from tests.py.panel_tf.conftest import http_client,isolated_chat_native_generation,extra_aliases
from tests.py.transfer_t1.test_write import client,physical

@pytest.mark.parametrize('path',MISSING,ids=MISSING)
def test_new_panel_routes_auth_host_and_escalation_before_dispatch(http_client,path):
    client,_,project,_,headers=http_client;before=physical(project)
    for supplied in ({},{'X-Agent-Token':'SYNTHETIC-WRONG'},dict(headers,Host='forged.example')):
        response=client.post(path,data='not-json',content_type='application/json',headers=supplied)
        assert response.status_code==403
    for flag in ('allow_addons','allow_self_edit'):
        response=client.post(path,json={flag:True},headers=headers)
        # ADR-0090: cache status discards UI metadata, never grants project rights.
        assert response.status_code==(200 if path=='/project/api_cache_status' else 403),response.get_json()
    assert physical(project)==before

def test_old_confirmation_cannot_make_stale_file_apply_confirm_another_chat_plan(http_client):
    client,_,project,_,headers=http_client;before=physical(project)
    body={'old_path':'res://hero.gd','new_path':'res://champion.gd','update_references':True}
    preview=client.post('/project/refactor/file/preview',json=body,headers=headers)
    assert preview.status_code==200 and preview.json['pending_confirmation']
    rejected=client.post('/chat/confirm',json={'approved':False},headers=headers)
    assert rejected.status_code==200 and rejected.json['state']=='REJECTED'
    new=client.post('/chat',json={'text':'Создай.'},headers=headers)
    assert new.status_code==200 and new.json['pending_confirmation'] and physical(project)==before
    stale=client.post('/project/refactor/file/apply',json=body,headers=headers)
    assert stale.status_code==409,stale.json
    assert physical(project)==before and not (project/'new.gd').exists()

def test_explicit_refactor_rejection_reports_no_changed_paths(http_client):
    client,_,project,_,headers=http_client;before=physical(project)
    body={'old_path':'res://hero.gd','new_path':'res://champion.gd','update_references':True}
    assert client.post('/project/refactor/file/preview',json=body,headers=headers).status_code==200
    rejected=client.post('/project/refactor/file/apply',json=dict(body,approved=False),headers=headers)
    assert rejected.status_code==200 and rejected.json['state']=='REJECTED'
    assert rejected.json['changed_paths']==[] and rejected.json['entry_id'] is None and physical(project)==before

def test_native_file_apply_is_exact_preview_then_assistant_confirmation(http_client,monkeypatch):
    client,agent,project,state,headers=http_client;before=physical(project)
    body={'old_path':'res://hero.gd','new_path':'res://champion.gd','update_references':True}
    assert client.post('/project/refactor/file/apply',json=body,headers=headers).status_code==409
    preview=client.post('/project/refactor/file/preview',json=body,headers=headers)
    assert preview.status_code==200,preview.get_json()
    plan=preview.get_json()['preview'];assert physical(project)==before
    bypass=agent.call('write_apply',dict(plan_id=plan['plan_id'],digest=plan['digest']))
    assert not bypass['ok'] and bypass['kind']=='denied'
    calls=[];original=agent.call
    def guarded(name,args):
        calls.append((name,dict(args)))
        assert name!='write_apply','HTTP bypassed assistant USER_CONFIRMED'
        return original(name,args)
    monkeypatch.setattr(agent,'call',guarded)
    changed=dict(body,new_path='res://other.gd')
    assert client.post('/project/refactor/file/apply',json=changed,headers=headers).status_code==409
    answer=client.post('/project/refactor/file/apply',json=body,headers=headers)
    assert answer.status_code==200,answer.get_json()
    assert answer.get_json()['state']=='COMMITTED'
    assert calls[-1][0]=='assistant_confirm' and calls[-1][1]==dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=True)
    assert (project/'champion.gd').exists() and not (project/'hero.gd').exists()
    rows=[__import__('json').loads(s) for s in next(state.rglob(plan['plan_id']+'.jsonl')).read_text('utf-8').splitlines()]
    assert any(row['state']=='USER_CONFIRMED' for row in rows)
    assert client.post('/chat/rollback',json={},headers=headers).status_code==200
    assert physical(project)==before
