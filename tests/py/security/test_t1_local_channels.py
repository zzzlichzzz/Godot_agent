"""SEC-T1-LOCAL attacks use in-process transport, never real sockets."""
import io
import json
from pathlib import Path
import pytest
from python.channels.http.app import create_app
from python.channels.mcp.stdio import serve_stdio
from tests.py.transfer_t1.test_write import client,physical

def test_foreign_host_and_missing_token_cannot_reach_effectful_agent(client):
    agent,root,state=client
    state.mkdir(exist_ok=True)
    (state/'godot_agent_token.txt').write_text('SYNTHETIC-LOCAL-SECURITY-TOKEN',encoding='utf-8')
    app=create_app(root,state,agent=agent,native_routes=False);http=app.test_client();before=physical(root)
    for headers in ({'Host':'foreign.example','X-Agent-Token':'SYNTHETIC-LOCAL-SECURITY-TOKEN'},{}):
        response=http.post('/tools/call',json={'name':'assistant_confirm','args':{'approved':True}},headers=headers)
        assert response.status_code==403 and physical(root)==before

def test_mcp_scalar_and_nonfinite_requests_do_not_authorize_effects(client):
    agent,root,state=client;before=physical(root);output=io.StringIO()
    serve_stdio(agent,io.BytesIO(b'1\n{"jsonrpc":"2.0","id":NaN,"method":"tools/list"}\n'),output)
    replies=[json.loads(line) for line in output.getvalue().splitlines()]
    assert [row['error']['code'] for row in replies]==[-32600,-32700]
    assert physical(root)==before
