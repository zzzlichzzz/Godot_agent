"""Saved native panel policy must not disable unrelated metadata requests."""
import pytest
from pathlib import Path
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.test_write import physical


@pytest.mark.parametrize('path,extra', [('/chats/list', {}), ('/sites/list', {}),
    ('/api/providers', {}), ('/project/api_cache_status', {}),
    ('/api/models/scan', {}), ('/api/models/refresh', {'provider': 'openrouter'})])
@pytest.mark.parametrize('policy', [{'allow_addons': True, 'allow_self_edit': False},
    {'allow_addons': False, 'allow_self_edit': True},
    {'allow_addons': True, 'allow_self_edit': True}])
def test_saved_panel_policy_does_not_block_metadata(cold_tf6, path, extra, policy):
    http, headers, state, calls, (_, _, app) = cold_tf6
    project = app.extensions['native_references'].project
    before = physical(Path(project))
    token_before = (state / 'godot_agent_token.txt').read_bytes()
    body = dict(extra, **policy, project_root=project, user_data_dir=str(state),
                rename_unverified=False, rename_mode='strict')
    response = http.post(path, json=body, headers=headers)
    assert response.status_code == 200, response.get_json()
    if path.startswith('/api/models/'):
        assert response.json['error_code'] == 'no_key'
        assert response.json['kind'] == 'denied'
    assert calls == [] and physical(Path(project)) == before
    assert (state / 'godot_agent_token.txt').read_bytes() == token_before
    assert app.extensions['godot_session'].pending is None
