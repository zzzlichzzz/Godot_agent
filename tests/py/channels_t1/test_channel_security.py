"""Mandatory HTTP boundaries and native dashboard cases."""
import io
import json
import pytest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Response
from python.channels.http.app import create_app
from python.channels.mcp.stdio import serve_stdio
from tests.py.channels_t1.test_channels import http_client
from tests.py.transfer_t1.test_write import client,physical

def raw_http(client,path,headers):
    """Deliver malicious Host verbatim, without cookie URL normalization."""
    builder=EnvironBuilder(path=path,method='GET' if path=='/health' else 'POST',headers=headers,json=None if path=='/health' else {})
    try:return Response.from_app(client.application,builder.get_environ())
    finally:builder.close()

@pytest.mark.parametrize('host',['attacker.example','127.0.0.1.attacker.example','127.0.0.1:0','127.0.0.1:65536','127.0.0.1:bad'])
@pytest.mark.parametrize('path',['/health','/chat'])
def test_untrusted_host_is_denied_even_for_health(http_client,host,path):
    client,_,root,_,headers=http_client;before=physical(root)
    response=raw_http(client,path,{**headers,'Host':host})
    assert response.status_code==403 and physical(root)==before

@pytest.mark.parametrize('origin',['https://attacker.example','null','http://localhost:different'])
@pytest.mark.parametrize('path',['/health','/chat'])
def test_foreign_origin_is_denied_before_dispatch(http_client,origin,path):
    client,_,root,_,headers=http_client;before=physical(root)
    response=raw_http(client,path,{**headers,'Origin':origin})
    assert response.status_code==403 and physical(root)==before

def test_dashboard_has_native_routes_and_read_only_envelope(http_client):
    _,agent,root,state,headers=http_client;before=physical(root)
    web=create_app(root,state,agent=agent,native_routes=True).test_client();page=web.get('/dashboard',headers=headers)
    assert page.status_code==200 and b'/dashboard/data' in page.data
    response=web.get('/dashboard/data',headers=headers);assert response.status_code==200
    data=response.get_json();assert set(data)=={'uptime','project_root','pending_action','plan','minilich','log'}
    assert data['project_root']==str(root.resolve()) and isinstance(data['minilich'],dict) and physical(root)==before

def test_native_dashboard_sessions_do_not_adopt_another_project(http_client,tmp_path):
    _,agent,root,state,headers=http_client;first=create_app(root,state,agent=agent,native_routes=True).test_client()
    other=tmp_path/'second-project';other.mkdir();(other/'project.godot').write_bytes(b'config_version=5\n')
    profile=tmp_path/'second-profile';profile.mkdir();(profile/'godot_agent_token.txt').write_text('SYNTHETIC-SECOND-HTTP-TOKEN',encoding='utf-8')
    second=create_app(other,profile,agent=agent,native_routes=True).test_client();before=physical(root),physical(other)
    a=first.get('/dashboard/data',headers=headers)
    b=second.get('/dashboard/data',headers={'X-Agent-Token':'SYNTHETIC-SECOND-HTTP-TOKEN'})
    assert a.status_code==b.status_code==200
    assert a.get_json()['project_root']==str(root.resolve()) and b.get_json()['project_root']==str(other.resolve())
    assert (physical(root),physical(other))==before

def test_deep_json_cannot_kill_mcp_before_next_valid_request(http_client):
    _,agent,root,_,_=http_client;before=physical(root);output=io.StringIO()
    source=io.BytesIO(b'['*2000+b'0'+b']'*2000+b'\n'+json.dumps(dict(jsonrpc='2.0',id=2,method='tools/list')).encode()+b'\n')
    serve_stdio(agent,source,output);rows=[json.loads(line) for line in output.getvalue().splitlines()]
    assert rows[0]['error']['code']==-32700 and rows[1]['id']==2 and physical(root)==before

def test_default_listener_requests_random_loopback_port_without_orphan_killing(tmp_path,monkeypatch):
    from python.channels.http import app as http
    import werkzeug.serving
    calls=[]
    class FakeApp:
        def run(self,**kwargs):calls.append((kwargs.get('host'),kwargs.get('port')))
    class OwnedServer:
        server_port=54321
        def serve_forever(self):pass
        def shutdown(self):pass
        def server_close(self):pass
    def factory(host,port,app,**kwargs):calls.append((host,port));return OwnedServer()
    monkeypatch.setattr(http,'create_app',lambda *args,**kwargs:FakeApp());monkeypatch.setattr(werkzeug.serving,'make_server',factory)
    project=tmp_path/'project';project.mkdir();profile=tmp_path/'profile';profile.mkdir();http.serve(project,profile)
    assert calls==[('127.0.0.1',0)]
