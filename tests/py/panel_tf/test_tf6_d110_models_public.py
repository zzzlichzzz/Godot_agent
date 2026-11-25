"""RED/D110: scoped HTTP model-list badge must stay honest without mutating native."""
from contextlib import contextmanager
import pytest
from tests.py.panel_tf.tf6_fixture import cold_tf6
from tests.py.panel_tf.test_control_envelope import panel_body


PUBLIC_IDS = ('openrouter', 'opencode_zen')


def test_scoped_http_providers_disables_models_public_and_requires_key(cold_tf6):
    http, headers, state, calls, (_, _, app) = cold_tf6
    response = http.post('/api/providers', json=panel_body(app, state), headers=headers)
    assert response.status_code == 200, response.get_json()
    by_id = {rec['id']: rec for rec in response.json['providers']}
    assert set(PUBLIC_IDS) <= set(by_id)
    for pid in PUBLIC_IDS:
        rec = by_id[pid]
        assert rec['models_public'] is False, (pid, rec)
        assert 'Нужен ключ провайдера' in rec['note_ru'], (pid, rec['note_ru'])
        assert 'без ключа' not in rec['note_ru'].lower(), (pid, rec['note_ru'])
        assert 'without a key' not in rec['note_en'].lower(), (pid, rec['note_en'])
        assert 'key' in rec['note_en'].lower(), (pid, rec['note_en'])
    assert calls == []


@pytest.mark.parametrize('exit_error', [None, RuntimeError('boom')])
def test_provider_scope_restores_native_public_flags_and_notes_without_mutation(exit_error):
    from python.substrate.llm.api.providers_fallback import scope
    native_openrouter = {
        'id': 'openrouter',
        'name': 'OpenRouter',
        'needs_key': True,
        'models_public': True,
        'note_ru': 'Бесплатные модели.',
        'note_en': 'Free models.',
    }
    native_zen = {
        'id': 'opencode_zen',
        'name': 'Opencode Zen',
        'needs_key': True,
        'models_public': True,
        'note_ru': 'Список моделей загружается без ключа — нажмите «Обновить».',
        'note_en': 'Curated models. The model list loads without a key — press "Refresh".',
    }
    original_list = [native_openrouter, native_zen]
    snapshot = [dict(native_openrouter), dict(native_zen)]
    registry = type('Registry', (), {'PROVIDERS': original_list, '_records_cache': {'key': False, 'value': {}}})()
    try:
        with scope(registry):
            assert registry.PROVIDERS is not original_list
            scoped = {p['id']: p for p in registry.PROVIDERS}
            for pid in PUBLIC_IDS:
                assert scoped[pid] is not (native_openrouter if pid == 'openrouter' else native_zen)
                assert scoped[pid]['models_public'] is False
                assert 'Нужен ключ провайдера' in scoped[pid]['note_ru']
                assert 'without a key' not in scoped[pid]['note_en'].lower()
            if exit_error is not None:
                raise exit_error
    except RuntimeError as caught:
        assert exit_error is not None and caught is exit_error
    assert registry.PROVIDERS is original_list
    assert [dict(native_openrouter), dict(native_zen)] == snapshot
    assert native_openrouter['models_public'] is True
    assert native_zen['models_public'] is True
