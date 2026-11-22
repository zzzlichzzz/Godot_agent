"""Receipt-owned parent attacks through the real write tools and recovery."""
import pytest
from python.kernel.errors import AppError
from python.runtime.bootstrap import build_agent,default_ports
from python.modules.assistant.write.domain.core import compile_plan,MAX_PARENTS
from python.modules.assistant.write.tests.test_directories import prepare,confirm,directories
from tests.py.transfer_t1.test_write import client,physical

def test_replaced_parent_with_equal_file_bytes_is_not_deleted_by_rollback(client):
    agent,project,_=client;plan=prepare(agent);applied=confirm(agent,plan)
    assert applied['ok'],applied
    (project/'new/nested').rename(project/'retained')
    (project/'new/nested').mkdir()
    (project/'new/nested/file.gd').write_bytes((project/'retained/file.gd').read_bytes())
    before=physical(project);dirs=directories(project)
    answer=agent.call('assistant_rollback',dict(plan_id=plan['plan_id'],entry_id=applied['result']['entry_id']))
    assert not answer['ok'] and physical(project)==before and directories(project)==dirs

def test_foreign_file_prevents_owned_directory_removal(client):
    agent,project,_=client;plan=prepare(agent);applied=confirm(agent,plan);assert applied['ok']
    (project/'new/nested/foreign.txt').write_bytes(b'foreign\r\n')
    answer=agent.call('assistant_rollback',dict(plan_id=plan['plan_id'],entry_id=applied['result']['entry_id']))
    assert not answer['ok'] and (project/'new/nested/foreign.txt').read_bytes()==b'foreign\r\n'
    assert (project/'new/nested').is_dir() and (project/'new').is_dir()

def test_nested_move_uses_owned_parent_steps_and_file_only_receipts(client):
    agent,project,_=client;before=physical(project);old_dirs=directories(project)
    answer=agent.call('assistant_plan',{'action':dict(action='move_file',path='res://hero.gd',dest='res://new/nested/hero.gd')})
    assert answer['ok'],answer
    plan=answer['result'];assert plan['steps_count']==5  # native script+UID: move/delete/create plus two mkdir
    applied=confirm(agent,plan);assert applied['ok'],applied
    result=applied['result']['result'];assert result['files_count']==3 and len(result['receipts'])==3
    assert (project/'new/nested/hero.gd.uid').read_bytes()==before['hero.gd.uid']
    rolled=agent.call('assistant_rollback',dict(plan_id=plan['plan_id'],entry_id=applied['result']['entry_id']))
    assert rolled['ok'],rolled
    assert rolled['result']['result']['files_count']==3
    assert physical(project)==before and directories(project)==old_dirs

def test_actual_recovery_restores_receipted_parent_directories(client):
    _,project,state=client;before=physical(project);old_dirs=directories(project)
    ports=default_ports(project,'cli',state_dir=state);create=ports['writer'].create
    def crash(*_a,**_k):raise SystemExit('owned interruption before file effect')
    ports['writer'].create=crash
    agent=build_agent(project,profile='cli',state_dir=state,ports=ports);plan=prepare(agent)
    with pytest.raises(SystemExit):confirm(agent,plan)
    ports['writer'].create=create
    from python.modules.editing.rollback.recovery import recover
    answer=recover(ports)
    assert answer==[{'plan_id':plan['plan_id'],'action':'rolled_back'}]
    assert physical(project)==before and directories(project)==old_dirs

def test_actual_recovery_blocks_directory_without_receipt(client):
    _,project,state=client;ports=default_ports(project,'cli',state_dir=state);append=ports['journal'].append
    def crash(plan_id,row):
        if row.get('state')=='RECEIPT':raise SystemExit('owned interruption before directory receipt')
        return append(plan_id,row)
    ports['journal'].append=crash
    agent=build_agent(project,profile='cli',state_dir=state,ports=ports);plan=prepare(agent)
    with pytest.raises(SystemExit):confirm(agent,plan)
    ports['journal'].append=append
    from python.modules.editing.rollback.recovery import recover
    result=recover(ports)
    assert result[0]['action']=='failed' and result[0]['reason']=='conflict'
    assert (project/'new').is_dir() and not (project/'new/nested/file.gd').exists()
    assert not any(row.get('state')=='ROLLED_BACK' for row in ports['journal'].read(plan['plan_id']))

@pytest.mark.parametrize('parents',[
    ['res://foreign'],['res://new','res://new'],['res://new:stream'],
    ['res://new/nested/file.gd'],['res://new']*(MAX_PARENTS+1),
])
def test_directory_footprint_refuses_unbounded_or_unrelated_effects(parents):
    files=[dict(path='res://new/nested/file.gd',before_bytes=None,after_bytes=b'extends Node\n')]
    with pytest.raises(AppError):compile_plan(files,dict(action='create_file'),{},'p1',parents)

def test_unique_valid_directory_footprint_has_an_independent_upper_bound():
    parts=['p'+str(i) for i in range(MAX_PARENTS+1)]
    parents=['res://'+'/'.join(parts[:i]) for i in range(1,len(parts)+1)]
    files=[dict(path=parents[-1]+'/file.gd',before_bytes=None,after_bytes=b'extends Node\n')]
    with pytest.raises(AppError,match='слишком много parent'):
        compile_plan(files,dict(action='create_file'),{},'p1',parents)
    plan,_=compile_plan(files,dict(action='create_file'),{},'p1',parents[:-1])
    assert len(plan.steps)==MAX_PARENTS+1
