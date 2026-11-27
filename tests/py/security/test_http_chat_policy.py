"""ADR-0093 / SEC-HTTP-CHAT-POLICY: fail-closed /chat + /chat/live_input policy boundary."""
from pathlib import Path
from flask import Flask, request
import pytest
from python.channels.http.auth import ProjectAuth
from tests.py.panel_tf.test_control_envelope import SYNTHETIC_KEY, panel_body
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import client, physical

PANEL_ACTION_PATHS = (
    '/chat', '/chat/live_input', '/chat/stop', '/chat/rollback/preview',
    '/server/shutdown', '/minilich/status', '/minilich/set', '/minilich/github_fetch',
    '/init', '/tools/call', '/chat/confirm_action', '/chat/rollback',
    '/project/update_api_cache', '/project/refactor/file/apply',
)
TOKEN = 'SYNTHETIC-CHAT-POLICY-TOKEN-NOT-A-SECRET'


@pytest.fixture
def chat_policy_http(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    state = tmp_path / 'state'; state.mkdir()
    (state / 'godot_agent_token.txt').write_text(TOKEN, 'utf-8')
    app = Flask(__name__); ProjectAuth(project, state).install(app)
    calls = []

    def echo():
        calls.append(request.get_json())
        return request.get_json()

    for idx, path in enumerate(PANEL_ACTION_PATHS):
        app.add_url_rule(path, str(idx), echo, methods=['POST'])
    body = dict(project_root=str(project), user_data_dir=str(state),
                allow_addons=False, allow_self_edit=False,
                addon_dir=str(project / 'addons/untrusted'),
                rename_mode='strict', rename_unverified=True, payload='kept')
    return app.test_client(), body, {'X-Agent-Token': TOKEN}, calls


@pytest.mark.parametrize('path', PANEL_ACTION_PATHS)
def test_panel_action_and_chat_routes_refuse_policy_elevation(chat_policy_http, path):
    http, body, headers, calls = chat_policy_http
    for flag in ('allow_addons', 'allow_self_edit'):
        response = http.post(path, json=dict(body, **{flag: True}), headers=headers)
        assert response.status_code == 403 and response.json['kind'] == 'denied'
    assert calls == []


@pytest.mark.parametrize('path', PANEL_ACTION_PATHS)
def test_panel_action_routes_fail_closed_on_auth_origin_project_bounds(chat_policy_http, path):
    http, body, headers, calls = chat_policy_http
    for bad in ({}, {'X-Agent-Token': 'WRONG'},
                dict(headers, Host='foreign.invalid'), dict(headers, Origin='http://foreign.invalid')):
        assert http.post(path, json=body, headers=bad).status_code == 403
    for key in ('project_root', 'user_data_dir'):
        assert http.post(path, json=dict(body, **{key: body[key] + '-other'}), headers=headers).status_code == 409
    assert http.post(path, json=[], headers=headers).status_code == 400
    assert http.post(path, data=b' ' * 1_000_001, content_type='application/json', headers=headers).status_code == 413
    assert calls == []


def test_api_chat_live_input_does_not_open_browser_site(cold_tf6, monkeypatch):
    http, headers, state, calls, (_, _, app) = cold_tf6
    assert http.post('/api/settings/set', json=panel_body(app, state, provider='openrouter', key=SYNTHETIC_KEY, model='m1'),
                     headers=headers).status_code == 200
    assert http.post('/chats/new', json=panel_body(app, state, kind='api', provider='openrouter', model='m1'),
                     headers=headers).status_code == 200
    seen_sites = []
    from python.substrate.llm.browser import sites
    orig_get = sites.get_site
    monkeypatch.setattr(sites, 'get_site', lambda sid: seen_sites.append(sid) or orig_get(sid))
    base = panel_body(app, state, text='hi', seq=1)
    base.update(allow_addons=False, allow_self_edit=False)
    response = http.post('/chat/live_input', json=base, headers=headers)
    assert response.status_code == 200
    assert response.json == {'ok': True, 'applied': False, 'reason': 'no_browser'}
    monkeypatch.setattr(app.extensions['godot_session'].gateway, 'current_driver', lambda: object())
    second = http.post('/chat/live_input', json=dict(base, text='hi2', seq=2), headers=headers)
    assert second.status_code == 200
    assert second.json == {'ok': True, 'applied': False, 'reason': 'no_parser'}
    assert seen_sites == [] and calls == []
    assert app.extensions['native_references'].state.STATE['allow_addons'] is False
    assert app.extensions['native_references'].state.STATE['allow_self_edit'] is False
