"""Frozen panel URL constants must resolve to actual registered routes."""
from pathlib import Path
import re
import pytest
from python.channels.http.app import create_app

ROOT=Path(__file__).resolve().parents[3]
SOURCE=(ROOT/'editor/native/agent_server.gd').read_text('utf-8')
PATHS=re.findall(r'^const URL_\w+\s*:=\s*BASE\s*\+\s*"([^"]+)"',SOURCE,re.M)
MISSING=(
    '/chat/confirm_action','/chat/editor_action/result','/chat/live_input',
    '/chat/runtime_check/bind','/chat/runtime_check/result','/chat/runtime_inspect/result',
    '/librarian/query','/minilich/github_fetch','/minilich/set','/minilich/status',
    '/project/api_cache_status','/project/check_log','/project/refactor/file/apply',
    '/project/refactor/file/post_move_sync','/project/refactor/file/preview',
    '/project/send_log_errors','/project/split_gd/apply','/project/split_gd/plan',
    '/project/split_gd/scan','/project/update_api_cache','/scene/refactor/node/apply',
    '/scene/refactor/node/delete/apply','/scene/refactor/node/delete/preview',
    '/scene/refactor/node/preview','/scene/refactor/node/reparent/apply',
    '/scene/refactor/node/reparent/preview','/server/shutdown')

def test_frozen_url_constant_set_is_51():
    assert len(PATHS)==len(set(PATHS))==51
    assert set(MISSING)<=set(PATHS) and len(MISSING)==27

@pytest.mark.parametrize('path',PATHS,ids=PATHS)
def test_every_panel_url_has_a_real_route(http_client,path):
    _,agent,project,state,_=http_client
    app=create_app(project,state,agent=agent,native_routes=True)
    routes={str(rule):rule.methods for rule in app.url_map.iter_rules()}
    assert path in routes, 'Frozen panel URL not registered: '+path
    assert ('GET' if path in ('/chat/progress','/dashboard','/dashboard/data') else 'POST') in routes[path]

@pytest.mark.parametrize('path',MISSING,ids=MISSING)
def test_new_route_is_dispatched_not_a_missing_url(http_client,path):
    client,_,_,_,headers=http_client
    response=client.post(path,json={},headers=headers)
    assert path in {str(rule) for rule in client.application.url_map.iter_rules()}
    assert response.status_code!=500, response.get_json()
    assert response.status_code in (200,400,403,404,409,503)
    if response.status_code==404:assert path=='/project/check_log' and response.get_json()['kind']=='not_found'
