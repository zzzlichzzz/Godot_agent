"""SEC-T1-WRITE: a plan or model answer is not user approval."""
from tests.py.transfer_t1.test_write import client,physical,preview

def test_bare_write_apply_cannot_bypass_explicit_assistant_approval(client):
    agent,project,_=client;before=physical(project);plan=preview(client)
    result=agent.call('write_apply',dict(plan_id=plan['plan_id'],digest=plan['digest']))
    assert result['ok'] is False and result['kind']=='denied'
    assert physical(project)==before

def test_confirmation_path_traversal_never_opens_other_wal(client):
    agent,project,state=client;before=physical(project)
    for name in ('../foreign','C:/foreign','..\\foreign','/foreign',''):
        result=agent.call('assistant_confirm',dict(plan_id=name,digest='a'*64,approved=True))
        assert result['ok'] is False and result['kind']=='invalid_input'
    assert physical(project)==before and not list(state.rglob('foreign.jsonl'))

def test_rejected_preview_cannot_later_be_applied_via_old_endpoint(client):
    agent,project,_=client;before=physical(project);plan=preview(client)
    args=dict(plan_id=plan['plan_id'],digest=plan['digest'])
    assert agent.call('assistant_confirm',dict(args,approved=False))['ok']
    assert agent.call('write_apply',args)['ok'] is False
    assert physical(project)==before
