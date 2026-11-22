"""Real stdio child process; no network, provider or credentials."""
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from tests.py.transfer_t1.test_write import client,physical

def invoke(module,root,state,data=None,extra=()):
    source=Path(__file__).parents[3];env=os.environ.copy();env['PYTHONPATH']=str(source)
    env['GODOT_AGENT_STATE_DIR']=str(state);env['GODOT_AGENT_CONFIG_DIR']=str(state/'config')
    command=[sys.executable,'-B','-X','utf8','-m',module,'--project',str(root),'--state',str(state),*extra]
    return subprocess.run(command,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=source,env=env,shell=False,timeout=90)

def test_http_module_has_an_explicit_project_state_and_port_cli(client):
    _,root,state=client;before=physical(root);reply=invoke('python.channels.http',root,state,extra=('--help',))
    assert reply.returncode==0,reply.stderr.decode('utf-8','replace')
    assert all(name in reply.stdout for name in (b'--project',b'--state',b'--port')) and physical(root)==before

def test_mcp_module_real_pipes_preserve_ids_and_do_not_authorize_writes(client):
    _,root,state=client;before=physical(root)
    frames=[dict(jsonrpc='2.0',id=1,method='initialize'),dict(jsonrpc='2.0',id=2,method='tools/list'),
            dict(jsonrpc='2.0',method='notifications/initialized'),dict(jsonrpc='2.0',id=3,method='tools/call',params=dict(name='assistant_confirm',arguments={}))]
    reply=invoke('python.channels.mcp',root,state,('\n'.join(json.dumps(f) for f in frames)+'\nnot-json\n').encode())
    assert reply.returncode==0,reply.stderr.decode('utf-8','replace')
    rows=[json.loads(line) for line in reply.stdout.splitlines()];assert [row['id'] for row in rows]==[1,2,3,None]
    assert 'assistant_confirm' in {tool['name'] for tool in rows[1]['result']['tools']}
    assert rows[2]['result']['isError'] is True and rows[3]['error']['code']==-32700 and physical(root)==before

@pytest.mark.parametrize('raw,code',[pytest.param(b'{"jsonrpc":"2.0","id":NaN,"method":"initialize"}',-32700,id='nonfinite-id'),
                                    pytest.param(b'['*2000+b'0'+b']'*2000,-32700,id='deep-json'),pytest.param(b'1',-32600,id='scalar-request'),
                                    pytest.param(b'x'*1_000_001,-32700,id='oversized-record')])
def test_mcp_real_pipe_recovers_to_next_frame_after_bad_input(client,raw,code):
    _,root,state=client;before=physical(root);following=json.dumps(dict(jsonrpc='2.0',id=7,method='tools/list')).encode()
    reply=invoke('python.channels.mcp',root,state,raw+b'\n'+following+b'\n')
    assert reply.returncode==0,reply.stderr.decode('utf-8','replace')
    rows=[json.loads(line) for line in reply.stdout.splitlines()]
    assert rows[0]['error']['code']==code and rows[1]['id']==7 and len(rows)==2 and physical(root)==before
