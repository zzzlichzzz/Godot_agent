"""The MCP executable refuses project/source-owned runtime state."""
import json
from pathlib import Path
import pytest
from tests.py.channels_t1.test_channel_entrypoints import invoke
from tests.py.transfer_t1.test_write import client,physical

@pytest.mark.parametrize('child',[False,True],ids=['project-root','project-child'])
def test_mcp_refuses_project_contained_state_before_agent_construction(client,child):
    _,root,_=client;state=root/'state' if child else root;before=physical(root)
    frame=json.dumps(dict(jsonrpc='2.0',id=1,method='initialize')).encode()+b'\n'
    result=invoke('python.channels.mcp',root,state,frame)
    assert result.returncode==2 and b'MCP startup refused' in result.stderr
    assert not result.stdout and physical(root)==before

@pytest.mark.parametrize('child',[False,True],ids=['source-root','source-child'])
def test_mcp_refuses_source_contained_state_before_agent_construction(client,child):
    _,root,_=client;source=Path(__file__).parents[3];state=source/'entry-test-state' if child else source
    before=physical(root);exists=state.exists();frame=json.dumps(dict(jsonrpc='2.0',id=1,method='initialize')).encode()+b'\n'
    result=invoke('python.channels.mcp',root,state,frame)
    assert result.returncode==2 and b'MCP startup refused' in result.stderr
    assert not result.stdout and physical(root)==before and state.exists()==exists
