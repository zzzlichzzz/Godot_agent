"""Cold real native HTTP composition; only transports are diagnostic sentinels."""
import os
import pytest


@pytest.fixture
def cold_tf6(client, monkeypatch):
    from python.channels.http.app import create_app
    from python.substrate.assistant.native_bindings import NativeBindings
    NativeBindings().register()
    from python.substrate.llm.api import api_keys, providers, openai_compat, providers_catalog
    _, project, state = client
    monkeypatch.setattr(os, 'environ', {})
    token = 'SYNTHETIC-TF6-UNIT-NOT-A-REAL-SECRET'
    state.mkdir(exist_ok=True)
    (state / 'godot_agent_token.txt').write_text(token, encoding='utf-8')
    app = create_app(project_root=project, state_dir=state)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append('transport')
        raise AssertionError('TF6 test forbids external transport')

    monkeypatch.setattr(openai_compat, 'fetch_models', forbidden)
    monkeypatch.setattr(providers_catalog, 'refresh', forbidden)
    return app.test_client(), {'X-Agent-Token': token}, state, calls, (providers, api_keys, app)
