"""D108 real channel contracts, independent of saved observation-RED receipts."""
import re
from pathlib import Path
import pytest
from tests.py.panel_tf.tf6_fixture import cold_tf6

ROOT = Path(__file__).resolve().parents[3]
REQUIRED = {'aistudio', 'openrouter', 'deepseek', 'qwen'}


def state_bytes(state):
    config = state / 'api_config'
    return {p.relative_to(config).as_posix(): p.read_bytes() for p in config.rglob('*') if p.is_file()}


def test_cold_static_minimum_is_not_live_model_availability(cold_tf6):
    client, headers, state, calls, _ = cold_tf6
    response = client.post('/api/providers', json={}, headers=headers)
    assert response.status_code == 200
    result = response.get_json()
    records = {p['id']: p for p in result['providers']}
    assert REQUIRED <= records.keys() and 'gemini' in records
    for pid in REQUIRED:
        assert not records[pid]['configured'] and not records[pid]['ready']
        assert not records[pid]['verified'] and records[pid]['models'] == []
    assert result['catalog']['models'] == 0 and calls == [] and state_bytes(state) == {}


@pytest.mark.parametrize('path,body', [('/api/models/refresh', {'provider': 'openrouter'}),
    ('/api/models/refresh', {'provider': 'aistudio'}), ('/api/models/refresh', {'provider': 'qwen'}),
    ('/api/models/refresh', {'provider': 'deepseek'}), ('/api/models/refresh', {'provider': 'opencode_zen'}),
    ('/api/models/scan', {}), ('/api/models/scan', {'force': True})])
def test_keyless_refusal_preserves_full_settings_and_state(cold_tf6, path, body):
    client, headers, state, calls, _ = cold_tf6
    client.post('/api/providers', json={}, headers=headers)
    before = state_bytes(state)
    response = client.post(path, json=body, headers=headers)
    result = response.get_json()
    assert response.status_code == 200 and result['error'] == 'Нужен ключ провайдера'
    assert result['error_code'] == 'no_key' and result['kind'] == 'denied' and result['hint']
    assert REQUIRED <= {p['id'] for p in result['providers']}
    assert calls == [] and state_bytes(state) == before
    if path.endswith('scan'):
        assert result['scanned'] == result['failed'] == [] and result['scan_skipped'] is True
    else:
        assert result['provider'] == body['provider']


def test_keyed_fresh_scan_skips_catalog_and_keyless_public_targets(cold_tf6, monkeypatch):
    client, headers, _, calls, (providers, keys, _) = cold_tf6
    monkeypatch.setattr(keys, 'has_key', lambda pid, env=(): pid == 'openrouter')
    monkeypatch.setattr(providers, 'models_stale', lambda *args, **kwargs: False)
    response = client.post('/api/models/scan', json={}, headers=headers)
    assert response.get_json()['scan_skipped'] is True and calls == []


def test_unknown_and_unavailable_are_not_misreported_as_missing_key(cold_tf6):
    client, headers, _, calls, _ = cold_tf6
    unknown = client.post('/api/models/refresh', json={'provider': 'unknown'}, headers=headers)
    unavailable = client.post('/api/models/refresh', json={'provider': 'agentrouter'}, headers=headers)
    assert unknown.status_code == 400
    assert 'пока недоступен' in unavailable.get_json()['error'] and calls == []


@pytest.mark.parametrize('path,body', [('/api/models/refresh', {'provider': 'openrouter'}),
    ('/api/models/scan', {}), ('/api/models/scan', {'force': True})])
def test_keyed_requests_reach_only_the_keyed_provider(cold_tf6, monkeypatch, path, body):
    client, headers, _, calls, (_, keys, app) = cold_tf6
    from python.substrate.llm.api import openai_compat, providers_catalog
    with app.extensions['native_references'].scope():
        keys.set_key('openrouter', 'SYNTHETIC-TF6-PROVIDER-NOT-A-REAL-SECRET')

    def fetch(url, key, **kwargs):
        assert url == 'https://openrouter.ai/api/v1/models'
        assert key == 'SYNTHETIC-TF6-PROVIDER-NOT-A-REAL-SECRET'
        calls.append('keyed-provider')
        return [{'id': 'synthetic-model'}]

    def catalog(**kwargs):
        calls.append('catalog-stub')
        return False, ''

    monkeypatch.setattr(openai_compat, 'fetch_models', fetch)
    monkeypatch.setattr(providers_catalog, 'refresh', catalog)
    result = client.post(path, json=body, headers=headers).get_json()
    assert not result.get('error') and calls.count('keyed-provider') == 1 and 'transport' not in calls
    if path.endswith('scan'):
        assert result['scanned'] == ['openrouter'] and result['failed'] == []
    else:
        assert result['models'] == ['synthetic-model']


def test_scene_script_uid_matches_actual_sidecar():
    scene = (ROOT / 'editor/native/AgentStatusBar.tscn').read_text('utf-8')
    match = re.search(r'\[ext_resource type="Script" uid="([^"]+)"', scene)
    assert match.group(1) == (ROOT / 'editor/native/AgentStatusBar.gd.uid').read_text('utf-8').strip()
