"""Full native panel body: API configuration is not project-write authority."""
import json
from pathlib import Path
import pytest
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import physical

SYNTHETIC_KEY = 'SYNTHETIC-UNIT-ONLY-NOT-A-REAL-API-KEY-1234567890'


def panel_body(app, state, **extra):
    return dict(project_root=app.extensions['native_references'].project,
                user_data_dir=str(state),
                addon_dir=str(Path(app.extensions['native_references'].project) / 'addons/godot_agent/editor/native'),
                allow_addons=True, allow_self_edit=False,
                rename_mode='probable', rename_unverified=True, **extra)


@pytest.mark.parametrize('field', ['key', 'add_key'])
@pytest.mark.parametrize('flags', [(True, False), (False, True), (True, True)])
def test_save_key_with_full_panel_envelope_persists_without_leak(cold_tf6, field, flags):
    http, headers, state, calls, (_, _, app) = cold_tf6
    project = Path(app.extensions['native_references'].project)
    before = physical(project)
    token = (state / 'godot_agent_token.txt').read_bytes()
    body = panel_body(app, state, provider='openrouter', **{field: SYNTHETIC_KEY})
    body.update(allow_addons=flags[0], allow_self_edit=flags[1])
    response = http.post('/api/settings/set', json=body, headers=headers)
    assert response.status_code == 200, response.json
    assert SYNTHETIC_KEY.encode() not in response.data
    cfg = json.loads((state / 'api_config/api_keys.json').read_text('utf-8'))
    assert cfg['providers']['openrouter']['keys'][0]['key'] == SYNTHETIC_KEY
    from python.channels.http.app import create_app
    reloaded = create_app(project, state)
    response = reloaded.test_client().post('/api/providers', json=panel_body(reloaded, state), headers=headers)
    assert response.status_code == 200 and SYNTHETIC_KEY.encode() not in response.data
    assert next(p for p in response.json['providers'] if p['id'] == 'openrouter')['configured']
    assert calls == [] and physical(project) == before
    assert (state / 'godot_agent_token.txt').read_bytes() == token
    assert app.extensions['godot_session'].pending is None


@pytest.mark.parametrize('allow_addons', [False, True])
def test_existing_chats_list_accepts_real_native_addon_metadata(cold_tf6, allow_addons):
    http, headers, state, calls, (_, _, app) = cold_tf6
    path = state / 'agent_chats.json'
    path.write_text(json.dumps([{'id': 'saved-synthetic', 'title': 'Saved chat', 'last_used': 1.0}]), 'utf-8')
    before = path.read_bytes()
    body = panel_body(app, state)
    body['allow_addons'] = allow_addons
    errors = []
    app.register_error_handler(Exception, lambda error: (errors.append(type(error).__name__) or {'kind': type(error).__name__}, 500))
    response = http.post('/chats/list', json=body, headers=headers)
    assert response.status_code == 200, response.json
    assert [c['id'] for c in response.json['chats']] == ['saved-synthetic']
    assert errors == [] and calls == [] and path.read_bytes() == before
    assert app.extensions['native_references'].state.STATE['allow_addons'] is False
    assert app.extensions['native_references'].state.STATE['allow_self_edit'] is False


def test_full_panel_envelope_api_chat_lifecycle_is_offline(cold_tf6):
    http, headers, state, calls, (_, _, app) = cold_tf6
    project = Path(app.extensions['native_references'].project)
    before = physical(project)
    token = (state / 'godot_agent_token.txt').read_bytes()

    def post(path, **extra):
        response = http.post(path, json=panel_body(app, state, **extra), headers=headers)
        assert response.status_code == 200, (path, response.json)
        assert SYNTHETIC_KEY.encode() not in response.data
        return response.json

    post('/api/settings/set', provider='openrouter', key=SYNTHETIC_KEY, model='synthetic-offline-model')
    created = post('/chats/new', kind='api', provider='openrouter', model='synthetic-offline-model')
    cid = created['current_id']
    assert any(c['id'] == cid for c in post('/chats/list')['chats'])
    renamed = post('/chats/rename', id=cid, title='Synthetic renamed chat')
    assert next(c for c in renamed['chats'] if c['id'] == cid)['title'] == 'Synthetic renamed chat'
    assert post('/chats/open', id=cid)['current_id'] == cid
    unchanged = post('/chats/model', provider='openrouter', model='synthetic-offline-model')
    assert unchanged['ok'] is False
    assert post('/browser/status') == {'ready': False, 'state': 'idle', 'url': ''}
    deleted = post('/chats/delete', id=cid)
    assert all(c['id'] != cid for c in deleted['chats'])
    assert calls == [] and physical(project) == before
    assert (state / 'godot_agent_token.txt').read_bytes() == token
    assert app.extensions['native_references'].state.STATE['allow_addons'] is False
    assert app.extensions['native_references'].state.STATE['allow_self_edit'] is False
    assert app.extensions['godot_session'].pending is None


@pytest.mark.parametrize('failure', ['http', 'exception'])
def test_native_navigation_is_released_after_failed_request(cold_tf6, failure):
    from flask import abort
    http, headers, state, _, (_, _, app) = cold_tf6
    refs = app.extensions['native_references']

    def fail_after_admission():
        assert refs.state.try_begin_navigation()
        if failure == 'http':
            abort(400)
        raise RuntimeError('Synthetic navigation failure')

    app.view_functions['chats.chats_new'] = fail_after_admission
    response = http.post('/chats/new', json=panel_body(app, state), headers=headers)
    assert response.status_code == 500  # The existing catch-all redacts both errors.
    assert refs.state.try_begin_navigation() is True
    refs.state.clear_request_activity()


def test_denied_navigation_does_not_release_another_threads_exchange(cold_tf6):
    import threading
    http, headers, state, _, (_, _, app) = cold_tf6
    refs = app.extensions['native_references']
    ready = threading.Event()
    release = threading.Event()

    def other_request():
        try:
            assert refs.state.try_begin_turn_exchange()
            ready.set()
            assert release.wait(10)
        finally:
            refs.state.clear_request_activity()

    owner = threading.Thread(target=other_request)
    owner.start()
    try:
        assert ready.wait(10)
        response = http.post('/chats/new', json=panel_body(app, state, kind='api'), headers=headers)
        assert response.status_code == 409
        assert refs.state.exchange_active() is True
    finally:
        release.set()
        owner.join(10)
    assert not owner.is_alive() and refs.state.exchange_active() is False
