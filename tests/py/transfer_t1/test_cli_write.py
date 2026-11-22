"""Real CLI translation, explicit approval, and the existing write funnel."""
import io
import json
import pytest
from python.channels.cli.main import main
from .test_write import client,physical
from .test_turn import with_packets,packet

def invoke(client,words):
    agent,project,state=client;out=io.StringIO()
    code=main(['--project',str(project),'--state-dir',str(state),*words],
              agent_factory=lambda **kwargs:agent,stdout=out)
    return code,json.loads(out.getvalue())

def test_cli_preview_confirm_and_rollback_use_same_agent(client):
    agent,project,state=client;before=physical(project)
    action=dict(action='create_file',path='res://cli.gd',content='extends Node\n')
    code,answer=invoke(client,['plan','--action',json.dumps(action)])
    assert code==0 and physical(project)==before
    plan=answer['result'];words=[plan['plan_id'],plan['digest']]
    code,answer=invoke(client,['confirm',*words,'--approve'])
    assert code==0 and answer['result']['state']=='COMMITTED' and 'cli.gd' in physical(project)
    entry=answer['result']['entry_id']
    code,answer=invoke(client,['rollback',plan['plan_id'],entry])
    assert code==0 and answer['result']['state']=='ROLLED_BACK' and physical(project)==before

def test_cli_confirm_requires_explicit_approval_option(client):
    agent,project,state=client;before=physical(project)
    with pytest.raises(SystemExit) as caught:
        invoke(client,['confirm','missing','a'*64])
    assert caught.value.code==2 and physical(project)==before

def test_cli_malformed_action_is_data_not_a_command(client):
    _,project,_=client;before=physical(project)
    code,answer=invoke(client,['plan','--action','not json'])
    assert code==1 and answer['kind']=='invalid_input' and physical(project)==before

def test_cli_traversing_confirmation_never_opens_foreign_journal(client):
    _,project,_=client;before=physical(project)
    code,answer=invoke(client,['confirm','../foreign','a'*64,'--approve'])
    assert code==1 and answer['kind']=='invalid_input' and physical(project)==before

def test_cli_turn_can_only_prepare_not_autoapprove(client):
    agent,_,project=with_packets(client,[packet(dict(action='create_file',path='res://cli.gd',content='extends Node\n'))])
    before=physical(project)
    code,answer=invoke((agent,project,client[2]),['turn','create cli script'])
    assert code==0 and answer['result']['state']=='pending_confirmation' and physical(project)==before
