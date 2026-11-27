"""Native case provenance + physical preview/confirmation/rollback security."""
import base64
import json
from pathlib import Path
import socket
import pytest
from python.runtime.bootstrap import build_agent, default_ports
from tests.py.transfer_t1.observations import GD,SCENE

ROOT=Path(__file__).resolve().parents[3]
REFERENCE=ROOT/'fixtures/corpus/assistant/write/reference.json'
DATA=json.loads(REFERENCE.read_bytes())

def physical(root):
    return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}

@pytest.fixture
def client(tmp_path,monkeypatch):
    project=tmp_path/'project';project.mkdir();state=tmp_path/'state'
    for name,text in {'project.godot':'[application]\nconfig/name="T1"\n','hero.gd':GD,
                      'hero.gd.uid':'uid://t1\n','level.tscn':SCENE}.items():
        (project/name).write_bytes(text.encode())
    def denied(*_args,**_kwargs): raise AssertionError('test attempted real network')
    for name in ('getaddrinfo',): monkeypatch.setattr(socket,name,denied)
    monkeypatch.setattr(socket.socket,'connect',denied);monkeypatch.setattr(socket.socket,'connect_ex',denied)
    monkeypatch.setenv('GODOT_AGENT_CONFIG_DIR',str(tmp_path/'config'))
    agent=build_agent(profile='cli',project_root=project,state_dir=state)
    return agent,project,state

def ok(agent,tool,args):
    value=agent.call(tool,args);assert value['ok'],value
    return value['result']

@pytest.mark.parametrize('case',DATA['cases'],ids=lambda c:c['id'])
def test_native_preview_parity_no_project_write(client,case):
    agent,project,_=client;before=physical(project);expected=DATA['observations'][case['id']]
    answer=agent.call('assistant_plan',{'action':case['action']})
    assert physical(project)==before
    if 'error' in expected:
        assert not answer['ok'];assert answer['kind']=='invalid_input'
        assert expected['message'] in answer['message'];return
    assert answer['ok'],answer;preview=answer['result']
    converted=[{'path':d['path'],'before':None if d['before'] is None else base64.b64encode(d['before'].encode()).decode(),
                'after':None if d['after'] is None else base64.b64encode(d['after'].encode()).decode()} for d in preview['diffs']]
    assert converted==expected['files']
    bypass=agent.call('write_apply',{'plan_id':preview['plan_id'],'digest':preview['digest']})
    assert not bypass['ok'] and bypass['kind']=='denied'
    assert physical(project)==before
    applied=ok(agent,'assistant_confirm',{'plan_id':preview['plan_id'],'digest':preview['digest'],'approved':True})
    assert applied['state']=='COMMITTED'
    after=dict(before)
    for item in expected['files']:
        path=item['path'][6:]
        if item['after'] is None: after.pop(path)
        else: after[path]=base64.b64decode(item['after'])
    assert physical(project)==after
    rollback=ok(agent,'assistant_rollback',{'plan_id':preview['plan_id'],'entry_id':applied['entry_id']})
    assert rollback['state']=='ROLLED_BACK' and physical(project)==before

def preview(client,action=None):
    agent,project,state=client
    result=ok(agent,'assistant_plan',{'action':action or DATA['cases'][0]['action']})
    return result

def test_rejection_expires_plan_without_write(client):
    agent,project,_=client;before=physical(project);plan=preview(client)
    args=dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=False)
    assert ok(agent,'assistant_confirm',args)['state']=='REJECTED'
    assert not agent.call('assistant_confirm',dict(args,approved=True))['ok']
    assert physical(project)==before

def test_wrong_digest_no_pending_and_implicit_approval_denied(client):
    agent,project,_=client;before=physical(project);plan=preview(client)
    for args in [dict(plan_id=plan['plan_id'],digest='0'*64,approved=True),
                 dict(plan_id='missing',digest=plan['digest'],approved=True),
                 dict(plan_id=plan['plan_id'],digest=plan['digest']),
                 dict(plan_id=plan['plan_id'],digest=plan['digest'],approved='yes')]:
        assert not agent.call('assistant_confirm',args)['ok']
    assert physical(project)==before

def test_policy_change_or_other_project_denied(client,tmp_path):
    agent,project,state=client;plan=preview(client);before=physical(project)
    for changed in [build_agent(profile='cli',project_root=project,state_dir=state,allow_addons=True),
                    build_agent(profile='cli',project_root=tmp_path/'other',state_dir=state)]:
        answer=changed.call('assistant_confirm',dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=True))
        assert not answer['ok'] and answer['kind']=='denied'
    assert physical(project)==before

def test_stale_file_preflight_no_partial_write(client):
    agent,project,_=client;plan=preview(client,DATA['cases'][8]['action'])
    (project/'hero.gd').write_bytes(b'extends Node\n# foreign edit\n');before=physical(project)
    answer=agent.call('assistant_confirm',dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=True))
    assert not answer['ok'] and physical(project)==before

def test_foreign_edit_blocks_rollback_and_confirmation_replay(client):
    agent,project,_=client;plan=preview(client)
    args=dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=True)
    receipt=ok(agent,'assistant_confirm',args)
    assert not agent.call('assistant_confirm',args)['ok']
    (project/'new.gd').write_bytes(b'extends Node\n# foreign edit\n');before=physical(project)
    assert not agent.call('assistant_rollback',dict(plan_id=plan['plan_id'],entry_id=receipt['entry_id']))['ok']
    assert physical(project)==before

def test_ttl_is_from_preview_not_journal_mtime(client):
    agent,project,state=client;plan=preview(client);before=physical(project)
    # Locate the real journal physically; do not alter a project file.
    path=next(state.rglob(plan['plan_id']+'.jsonl'))
    # WAL rows contain UTF-8 project/policy paths, regardless of the system locale.
    rows=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
    rows[0]['detail']['created_at']=0
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    answer=agent.call('assistant_confirm',dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=True))
    assert not answer['ok'] and answer['kind']=='not_found' and physical(project)==before

def test_effect_failure_compensates_all_previous_steps(client,monkeypatch):
    agent,project,state=client
    ports=default_ports(project,'cli',state_dir=state)
    writer=ports['writer'];count=[0]
    for method in ('write_raw','create'):
        original=getattr(writer,method)
        def broken(*args,_original=original,**kwargs):
            count[0]+=1
            if count[0]==2: raise OSError('owned injected effect failure')
            return _original(*args,**kwargs)
        monkeypatch.setattr(writer,method,broken)
    agent=build_agent(profile='cli',project_root=project,state_dir=state,ports=ports)
    before=physical(project);plan=ok(agent,'assistant_plan',{'action':DATA['cases'][8]['action']})
    answer=agent.call('assistant_confirm',dict(plan_id=plan['plan_id'],digest=plan['digest'],approved=True))
    assert not answer['ok'] and count[0]>=2 and physical(project)==before
