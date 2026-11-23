"""ADR-0090: non-authoritative UI metadata, never an auth/policy bypass."""
import pytest
from flask import Flask, request
from python.channels.http.auth import ProjectAuth

PATHS = ('/chats/list', '/sites/list', '/api/providers', '/api/models/refresh',
         '/api/models/scan', '/project/api_cache_status')
TOKEN = 'SYNTHETIC-METADATA-NOT-A-REAL-SECRET'


@pytest.fixture
def metadata_http(tmp_path):
    project = tmp_path / 'project'
    state = tmp_path / 'external'
    project.mkdir()
    state.mkdir()
    (state / 'godot_agent_token.txt').write_text(TOKEN, 'utf-8')
    app = Flask(__name__)
    ProjectAuth(project, state).install(app)
    calls = []

    def echo():
        body = request.get_json()
        calls.append(body)
        return body

    for index, path in enumerate((*PATHS, '/init', '/chat', '/tools/call',
        '/project/refactor/file/preview', '/project/refactor/file/apply',
        '/project/update_api_cache', '/api/providers/extra', '/sites/list/',
        '/unknown')):
        app.add_url_rule(path, str(index), echo, methods=['POST'])
    body = dict(project_root=str(project), user_data_dir=str(state),
                allow_addons=True, allow_self_edit=True)
    return app.test_client(), body, {'X-Agent-Token': TOKEN}, calls


@pytest.mark.parametrize('path', PATHS)
def test_policy_fields_are_removed_before_metadata_dispatch(metadata_http, path):
    http, body, headers, calls = metadata_http
    response = http.post(path, json=body, headers=headers)
    assert response.status_code == 200
    assert response.json == {key: value for key, value in body.items()
                             if key not in ('allow_addons', 'allow_self_edit')}
    assert len(calls) == 1 and body['allow_addons'] is True


@pytest.mark.parametrize('path', PATHS)
def test_metadata_auth_origin_project_and_bounds_still_fail_closed(metadata_http, path):
    http, body, headers, calls = metadata_http
    for supplied in ({}, {'X-Agent-Token': 'SYNTHETIC-WRONG'},
        dict(headers, Host='evil.invalid'), dict(headers, Origin='http://evil.invalid')):
        assert http.post(path, json=body, headers=supplied).status_code == 403
    for field in ('project_root', 'user_data_dir'):
        foreign = dict(body, **{field: body[field] + '-foreign'})
        assert http.post(path, json=foreign, headers=headers).status_code == 409
    assert http.post(path, json=[], headers=headers).status_code == 400
    assert http.post(path, data=b' ' * 1_000_001, content_type='application/json',
                     headers=headers).status_code == 413
    assert calls == []


@pytest.mark.parametrize('path', ['/init', '/chat', '/tools/call',
    '/project/refactor/file/preview', '/project/refactor/file/apply',
    '/project/update_api_cache', '/api/providers/extra', '/sites/list/', '/unknown'])
def test_other_paths_cannot_elevate_policy(metadata_http, path):
    http, body, headers, calls = metadata_http
    assert http.post(path, json=body, headers=headers).status_code == 403
    assert calls == []


@pytest.mark.parametrize('raw', [b'not-json', b'{"pid":0}',
    b'{"pid":99999999,"session_id":"foreign"}', b'{"session_id":"foreign"}'])
def test_startup_never_removes_an_unowned_endpoint(tmp_path, monkeypatch, raw):
    from python.channels.http import listener
    from types import SimpleNamespace
    state = tmp_path / 'state'
    state.mkdir()
    endpoint = state / 'http_endpoint.json'
    endpoint.write_bytes(raw)
    closed = []
    server = SimpleNamespace(server_port=54321, server_close=lambda: closed.append(True),
                             serve_forever=lambda: pytest.fail('Foreign endpoint adopted'))
    monkeypatch.setattr(listener.serving, 'make_server', lambda *a, **kw: server)
    with pytest.raises(FileExistsError):
        listener.serve(object(), tmp_path / 'project', state)
    assert endpoint.read_bytes() == raw and closed == [True]
