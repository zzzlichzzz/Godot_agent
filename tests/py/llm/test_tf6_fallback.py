"""Scoped fallback metadata; no native registry/corpus rewrite."""
from types import SimpleNamespace
import pytest


@pytest.mark.parametrize('exception', [None, RuntimeError, KeyboardInterrupt])
def test_scope_restores_exact_registry_and_cache_identity(exception):
    from python.substrate.llm.api.providers_fallback import scope
    records = [{'id': 'gemini'}, {'id': 'qwen', 'name': 'existing wins'}]
    cache = {'key': object(), 'value': {'existing': object()}}
    registry = SimpleNamespace(PROVIDERS=records, _records_cache=cache)
    try:
        with scope(registry):
            assert registry.PROVIDERS is not records and registry._records_cache is not cache
            assert [p['id'] for p in registry.PROVIDERS].count('qwen') == 1
            assert next(p for p in registry.PROVIDERS if p['id'] == 'qwen')['name'] == 'existing wins'
            studio = next(p for p in registry.PROVIDERS if p['id'] == 'aistudio')
            assert studio['needs_key'] and studio['models'] == [] and not studio.get('verified')
            assert 'generativelanguage.googleapis.com' in studio['base_url']
            if exception:
                raise exception('scope diagnostic')
    except BaseException as caught:
        assert exception and isinstance(caught, exception)
    assert registry.PROVIDERS is records and registry._records_cache is cache


def test_qwen_is_api_metadata_not_browser_site():
    from python.substrate.llm.api.providers_fallback import FALLBACKS
    qwen = next(p for p in FALLBACKS if p['id'] == 'qwen')
    assert qwen['base_url'] == 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1'
    assert qwen['needs_key'] and qwen['models'] == [] and not qwen.get('verified')
    assert qwen['env_names'] == ('DASHSCOPE_API_KEY', 'QWEN_API_KEY')
    assert 'new_chat_url' not in qwen and 'needs_visibility_spoof' not in qwen
