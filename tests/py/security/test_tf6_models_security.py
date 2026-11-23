"""No credentials means no catalog/provider transport; auth precedes the guard."""
import pytest
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.transfer_t1.conftest import isolated_chat_native_generation, extra_aliases
from tests.py.transfer_t1.test_write import client


@pytest.mark.parametrize('path', ['/api/models/refresh', '/api/models/scan'])
def test_auth_rejects_before_missing_key_or_external_transport(cold_tf6, path):
    http, headers, _, calls, _ = cold_tf6
    assert http.post(path, json={'provider': 'openrouter'}).status_code == 403
    assert http.post(path, json={}, headers={**headers, 'Host': 'evil.invalid'}).status_code == 403
    assert calls == []


def test_public_and_custom_flags_never_replace_key_authorization():
    from python.substrate.llm.api import model_refresh_policy as policy
    from types import SimpleNamespace
    registry = SimpleNamespace(env_names_for=lambda pid: (), models_url=lambda pid: 'https://example.invalid/models',
                               unavailable_reason=lambda pid: '', models_public=lambda pid: True)
    keys = SimpleNamespace(has_key=lambda pid, env: False)
    for pid in ['openrouter', 'opencode_zen', 'custom']:
        assert not policy.can_fetch(pid, registry, keys)


def test_internal_fetch_key_guard_cannot_be_bypassed(cold_tf6):
    _, _, _, calls, (_, _, app) = cold_tf6
    refs = app.extensions['native_references']
    with refs.scope():
        records, error = refs.routes._fetch_models('openrouter')
    assert records == [] and error == 'Нужен ключ провайдера' and calls == []
