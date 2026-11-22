"""In-process HTTP/MCP with synthetic auth and denied real sockets."""
import io
import json
import socket
import sys
import pytest
from python.runtime.bootstrap import build_agent,default_ports
from tests.py.transfer_t1.test_write import client,physical
from tests.py.transfer_t1.test_turn import OfflineGateway,packet
from python.channels.http.app import create_app
from python.channels.mcp.stdio import serve_stdio

@pytest.fixture
def http_client(client,tmp_path):
    _,project,state=client
    state.mkdir(exist_ok=True);(state/'godot_agent_token.txt').write_text('SYNTHETIC-HTTP-T1-NOT-A-REAL-SECRET',encoding='utf-8')
    ports=default_ports(project,'cli',state_dir=state)
    ports['chat_gateway']=OfflineGateway([packet(dict(action='create_file',path='res://new.gd',content='extends Node\n'),text='Создам файл.')])
    agent=build_agent(project,profile='cli',state_dir=state,ports=ports)
    app=create_app(project,state,agent=agent,native_routes=False)
    return app.test_client(),agent,project,state,{'X-Agent-Token':'SYNTHETIC-HTTP-T1-NOT-A-REAL-SECRET'}

def test_http_chat_confirm_rollback_same_agent_no_implicit_write(http_client):
    client,_,project,_,headers=http_client;before=physical(project)
    response=client.post('/chat',json={'text':'Создай.'},headers=headers)
    assert response.status_code==200,response.get_json()
    body=response.get_json();assert body['pending_confirmation'] and physical(project)==before
    assert client.post('/chat/confirm',json={},headers=headers).status_code==400
    assert physical(project)==before
    applied=client.post('/chat/confirm',json={'approved':True},headers=headers)
    assert applied.status_code==200 and applied.get_json()['state']=='COMMITTED'
    assert (project/'new.gd').exists()
    assert client.post('/chat/rollback',json={},headers=headers).status_code==200
    assert physical(project)==before

@pytest.mark.parametrize('path',['/chat','/chat/confirm','/init','/tools/call','/chat/editor/sync'])
def test_missing_or_wrong_auth_is_denied_before_json(http_client,path):
    client,_,project,_,_=http_client;before=physical(project)
    for headers in ({},{'X-Agent-Token':'SYNTHETIC-WRONG'}):
        answer=client.post(path,data=b'not JSON',content_type='application/json',headers=headers)
        assert answer.status_code==403
    assert physical(project)==before

def test_other_project_and_policy_escalation_fail_closed(http_client,tmp_path):
    client,_,project,state,headers=http_client;before=physical(project)
    for body in ({'project_root':str(tmp_path/'foreign')},{'user_data_dir':str(tmp_path/'foreign')},{'allow_self_edit':True}):
        response=client.post('/init',json=body,headers=headers);assert response.status_code in (403,409)
    assert physical(project)==before

def test_body_bounds_and_nonobject(http_client):
    client,_,_,_,headers=http_client
    assert client.post('/init',json=[],headers=headers).status_code==400
    assert client.post('/init',data=b' '*1_000_001,content_type='application/json',headers=headers).status_code==413
    assert client.get('/health').get_json()['provider_live_verified'] is False

def test_missing_token_cannot_start_server(client):
    agent,project,state=client
    from python.kernel.errors import AppError
    with pytest.raises(AppError,match='token'):create_app(project,state,agent=agent,native_routes=False)

def test_mcp_stdio_list_call_notifications_errors_without_network(client):
    agent,project,_=client;before=physical(project)
    messages=[dict(jsonrpc='2.0',id=1,method='initialize',params={}),dict(jsonrpc='2.0',method='notifications/initialized'),
              dict(jsonrpc='2.0',id=2,method='tools/list'),dict(jsonrpc='2.0',id=3,method='tools/call',params={'name':'assistant_confirm','arguments':{'plan_id':'missing','digest':'a'*64,'approved':True}})]
    source=io.BytesIO(('\n'.join(json.dumps(m) for m in messages)+'\nnot-json\n').encode());target=io.StringIO()
    serve_stdio(agent,source,target);replies=[json.loads(s) for s in target.getvalue().splitlines()]
    assert [r['id'] for r in replies]==[1,2,3,None]
    names={t['name'] for t in replies[1]['result']['tools']};assert {'assistant_plan','assistant_confirm','assistant_rollback'}<=names
    assert replies[2]['result']['isError'] and replies[3]['error']['code']==-32700 and physical(project)==before

def test_native_route_binding_restores_base_owner(client):
    agent,project,state=client;state.mkdir(exist_ok=True)
    (state/'godot_agent_token.txt').write_text('SYNTHETIC-HTTP-T1-NOT-A-REAL-SECRET',encoding='utf-8')
    from python.substrate.assistant.native_bindings import NativeBindings
    NativeBindings().register();owner=sys.modules['server_state'];before=physical(project)
    app=create_app(project,state,agent=agent,native_routes=True)
    assert sys.modules['server_state'] is owner
    assert app.extensions['native_references'].routes.S is app.extensions['native_references'].state
    client=app.test_client();headers={'X-Agent-Token':'SYNTHETIC-HTTP-T1-NOT-A-REAL-SECRET'}
    answer=client.post('/api/providers',json={},headers=headers)
    assert answer.status_code==200,answer.get_json()
    assert 'providers' in answer.get_json() and physical(project)==before

def test_default_http_composition_uses_native_api_offline_and_external_profile(client,monkeypatch):
    _,project,state=client;state.mkdir(exist_ok=True);before=physical(project)
    token='SYNTHETIC-HTTP-T1-NOT-A-REAL-SECRET'
    (state/'godot_agent_token.txt').write_text(token,encoding='utf-8')
    from python.substrate.assistant.native_bindings import NativeBindings
    NativeBindings().register()
    import api_backend
    calls=[]
    def offline(self,prompt,**kwargs):
        calls.append((prompt,kwargs))
        return packet(dict(action='create_file',path='res://composed.gd',content='extends Node\n'),text='Подготовлю файл.')
    monkeypatch.setattr(api_backend.ApiBackend,'send',offline)
    app=create_app(project,state,native_routes=True)
    gateway=app.extensions['godot_session'].gateway
    assert gateway.state_dir==state and gateway.config_dir==state/'api_config'
    response=app.test_client().post('/chat',json={'text':'Подготовь.'},headers={'X-Agent-Token':token})
    assert response.status_code==200,response.get_json()
    assert response.get_json()['pending_confirmation'] and calls and physical(project)==before

def test_stop_on_injected_agent_has_no_private_context_dependency(http_client):
    client,_,project,_,headers=http_client;before=physical(project)
    response=client.post('/chat/stop',json={},headers=headers)
    assert response.status_code==200 and response.get_json()['ok'] is False
    assert physical(project)==before
