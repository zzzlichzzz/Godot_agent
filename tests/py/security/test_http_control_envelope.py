"""ADR-0091: exact service routes, not an HTTP project-policy bypass."""
from flask import Flask, request
import os
import pytest
from python.channels.http.auth import ProjectAuth
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.panel_tf.test_control_envelope import panel_body, SYNTHETIC_KEY
from tests.py.transfer_t1.conftest import isolated_chat_native_generation, extra_aliases
from tests.py.transfer_t1.test_write import client, physical

PATHS = ('/sites/list', '/api/providers', '/api/settings/set', '/api/models/refresh',
         '/api/models/scan', '/api/test', '/browser/status', '/chats/list', '/chats/new',
         '/chats/open', '/chats/model', '/chats/rename', '/chats/delete', '/project/api_cache_status')
POLICY = ('allow_addons', 'allow_self_edit', 'addon_dir', 'rename_mode', 'rename_unverified')
TOKEN = 'SYNTHETIC-CONTROL-UNIT-TOKEN-NOT-A-REAL-SECRET'


@pytest.fixture
def control_http(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    state = tmp_path / 'state'; state.mkdir()
    (state / 'godot_agent_token.txt').write_text(TOKEN, 'utf-8')
    app = Flask(__name__); ProjectAuth(project, state).install(app)
    calls = []

    def echo():
        calls.append(request.get_json())
        return request.get_json()

    other = ('/init', '/chat', '/tools/call', '/project/update_api_cache',
             '/project/refactor/file/apply', '/chats/list/extra', '/api/settings/set/', '/unknown')
    for index, path in enumerate((*PATHS, *other)):
        app.add_url_rule(path, str(index), echo, methods=['POST'])
    body = dict(project_root=str(project), user_data_dir=str(state), allow_addons=True,
                allow_self_edit=True, addon_dir=str(project / 'addons/untrusted'),
                rename_mode='probable', rename_unverified=True, payload='kept')
    return app.test_client(), body, {'X-Agent-Token': TOKEN}, calls


@pytest.mark.parametrize('path', PATHS)
def test_exact_control_routes_remove_whole_policy_before_dispatch(control_http, path):
    http, body, headers, calls = control_http
    response = http.post(path, json=body, headers=headers)
    assert response.status_code == 200
    assert response.json == {k: v for k, v in body.items() if k not in POLICY}
    assert len(calls) == 1 and all(key in body for key in POLICY)


@pytest.mark.parametrize('path', PATHS)
def test_control_routes_keep_auth_origin_json_and_project_bounds(control_http, path):
    http, body, headers, calls = control_http
    for supplied in ({}, {'X-Agent-Token': 'SYNTHETIC-WRONG'},
                     dict(headers, Host='foreign.invalid'), dict(headers, Origin='http://foreign.invalid')):
        assert http.post(path, json=body, headers=supplied).status_code == 403
    for field in ('project_root', 'user_data_dir'):
        assert http.post(path, json=dict(body, **{field: body[field] + '-foreign'}), headers=headers).status_code == 409
    assert http.post(path, json=[], headers=headers).status_code == 400
    assert http.post(path, data=b' ' * 1_000_001, content_type='application/json', headers=headers).status_code == 413
    assert calls == []


@pytest.mark.parametrize('path', ['/init', '/chat', '/tools/call', '/project/update_api_cache',
    '/project/refactor/file/apply', '/chats/list/extra', '/api/settings/set/', '/unknown'])
def test_project_routes_and_lookalikes_still_refuse_policy_elevation(control_http, path):
    http, body, headers, calls = control_http
    assert http.post(path, json=body, headers=headers).status_code == 403
    assert calls == []


@pytest.mark.parametrize('name', ['api_keys.json', 'api_keys.json.tmp'])
def test_settings_refuse_linked_key_input_and_output_before_effects(cold_tf6, name):
    http, headers, state, calls, (_, _, app) = cold_tf6
    project = app.extensions['native_references'].project
    target = state / 'api_config' / name; target.parent.mkdir(exist_ok=True)
    from pathlib import Path
    os.link(Path(project) / 'hero.gd', target)
    before = physical(Path(project)); raw = target.read_bytes()
    body = panel_body(app, state, provider='openrouter', key=SYNTHETIC_KEY)
    body.update(allow_addons=False, allow_self_edit=False)
    response = http.post('/api/settings/set', json=body, headers=headers)
    assert response.status_code == 403 and response.json['kind'] == 'denied', response.json
    assert physical(Path(project)) == before and target.read_bytes() == raw
    assert calls == []
    if name.endswith('.tmp'):
        assert not (state / 'api_config/api_keys.json').exists()
    else:
        assert target.exists()
