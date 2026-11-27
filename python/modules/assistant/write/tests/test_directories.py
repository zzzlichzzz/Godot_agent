"""Native missing-parent creation plus receipt-only directory compensation."""
import pytest
from python.kernel.errors import AppError
from tests.py.transfer_t1.conftest import isolated_chat_native_generation,extra_aliases
from tests.py.transfer_t1.write_composition import build_agent,default_ports,intent_unstarted
from tests.py.transfer_t1.test_write import client,physical

def directories(project):return sorted(p.relative_to(project).as_posix() for p in project.rglob('*') if p.is_dir())
def prepare(agent,path='res://new/nested/file.gd'):
    answer=agent.call('assistant_plan',{'action':dict(action='create_file',path=path,content='extends Node\n')})
    assert answer['ok'],answer
    return answer['result']
def confirm(agent,plan):return agent.call('assistant_confirm',dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=True))

def test_nested_create_and_rollback_restore_files_and_owned_directories(client):
    agent,project,_=client;before=physical(project);old_dirs=directories(project)
    plan=prepare(agent)
    assert physical(project)==before and directories(project)==old_dirs and plan['steps_count']==3
    applied=confirm(agent,plan);assert applied['ok'],applied
    assert applied['result']['result']['files_count']==1
    assert (project/'new/nested/file.gd').read_bytes()==b'extends Node\n'
    rolled=agent.call('assistant_rollback',dict(plan_id=plan['plan_id'],entry_id=applied['result']['entry_id']))
    assert rolled['ok'] and rolled['result']['result']['files_count']==1
    assert physical(project)==before and directories(project)==old_dirs

def test_existing_empty_parent_is_not_removed_by_rollback(client):
    agent,project,_=client;(project/'keep').mkdir();old_dirs=directories(project)
    plan=prepare(agent,'res://keep/new/file.gd');assert plan['steps_count']==2
    applied=confirm(agent,plan);assert applied['ok'],applied
    assert agent.call('assistant_rollback',dict(plan_id=plan['plan_id'],entry_id=applied['result']['entry_id']))['ok']
    assert directories(project)==old_dirs and (project/'keep').is_dir()

def test_failed_file_effect_compensates_all_receipted_parent_directories(client):
    _,project,state=client;before=physical(project);old_dirs=directories(project)
    ports=default_ports(project,'cli',state_dir=state)
    def fail(*_a,**_k):raise OSError('owned failure before file effect')
    ports['writer'].create=fail
    agent=build_agent(project,profile='cli',state_dir=state,ports=ports);plan=prepare(agent)
    assert plan['steps_count']==3
    assert confirm(agent,plan)['ok'] is False
    assert physical(project)==before and directories(project)==old_dirs
    assert any(r.get('state')=='ROLLED_BACK' for r in ports['journal'].read(plan['plan_id']))

def test_replaced_directory_identity_is_not_written_or_deleted(client):
    _,project,state=client;ports=default_ports(project,'cli',state_dir=state)
    mkdir=ports['writer'].mkdir
    def replace(rel):
        proof=mkdir(rel)
        if rel=='new/nested':
            (project/rel).rename(project/'retained');(project/rel).mkdir()
        return proof
    ports['writer'].mkdir=replace
    agent=build_agent(project,profile='cli',state_dir=state,ports=ports);plan=prepare(agent)
    assert confirm(agent,plan)['ok'] is False
    assert (project/'retained').is_dir() and (project/'new/nested').is_dir()
    assert not (project/'new/nested/file.gd').exists()

def test_directory_without_receipt_blocks_recovery_instead_of_guessing_ownership(client):
    _,project,state=client;ports=default_ports(project,'cli',state_dir=state);append=ports['journal'].append
    def crash(plan_id,row):
        if row.get('state')=='RECEIPT':raise SystemExit('owned crash after mkdir before receipt')
        return append(plan_id,row)
    ports['journal'].append=crash
    agent=build_agent(project,profile='cli',state_dir=state,ports=ports);plan=prepare(agent)
    assert plan['steps_count']==3
    with pytest.raises(SystemExit):confirm(agent,plan)
    entries=ports['journal'].read(plan['plan_id']);prepared=entries[0]['plan']
    with pytest.raises(AppError) as rejected:intent_unstarted(ports['writer'],prepared,'res://new')
    assert rejected.value.kind=='conflict' and (project/'new').is_dir()
    assert not any(r.get('state')=='ROLLED_BACK' for r in entries)
