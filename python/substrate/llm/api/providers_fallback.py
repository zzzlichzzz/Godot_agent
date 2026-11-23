"""Offline HTTP fallback metadata; scoped composition preserves native API core."""
from contextlib import contextmanager
from copy import deepcopy

FALLBACKS = (
    dict(id='aistudio', name='Google AI Studio (Gemini API)',
         base_url='https://generativelanguage.googleapis.com/v1beta/openai',
         needs_key=True, env_names=('GEMINI_API_KEY', 'GOOGLE_API_KEY'),
         models_path='/models', models=[], default_model='', extra_headers={},
         verified=False,
         note_ru='Статический fallback: Gemini API по ключу AI Studio. Модели и подключение живьём не проверены.',
         note_en='Static fallback: Gemini API with an AI Studio key. Models and connection have not been verified live.'),
    dict(id='qwen', name='Qwen (DashScope API)',
         base_url='https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
         needs_key=True, env_names=('DASHSCOPE_API_KEY', 'QWEN_API_KEY'),
         models_path='/models', models=[], default_model='', extra_headers={},
         verified=False,
         note_ru='Статический fallback: международный DashScope API, не браузер Qwen. Модели и подключение живьём не проверены; региональный адрес можно изменить.',
         note_en='Static fallback: international DashScope API, not the Qwen browser site. Models and connection have not been verified live; the regional endpoint is editable.'),
)


@contextmanager
def scope(registry):
    """Caller holds the existing native lock; restore exact identities even on exit."""
    records, cache = registry.PROVIDERS, registry._records_cache
    existing = {p['id'] for p in records}
    registry.PROVIDERS = list(records) + [deepcopy(p) for p in FALLBACKS if p['id'] not in existing]
    registry._records_cache = {'key': False, 'value': {}}
    try:
        yield
    finally:
        registry.PROVIDERS, registry._records_cache = records, cache
