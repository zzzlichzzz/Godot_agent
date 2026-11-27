"""Consumer-owned api_cache fake: one fresh snapshot, no FS or private state."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.modules.engine_kb.class_api import app

ROOT = Path(__file__).resolve().parents[5]
CASES = [json.loads(p.read_bytes()) for p in sorted((ROOT / 'fixtures/corpus/engine_kb/class_api').glob('[0-9]*.json'))]


class Cache:
    def __init__(self, classes=None, version=''):
        self.value = (classes or {}, version)
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return self.value

    def classes(self):
        pytest.fail('api used memoized classes instead of fresh snapshot')


def context(cache):
    def port(name):
        assert name == 'api_cache', 'api requested unrelated port'
        return cache
    return SimpleNamespace(port=port)


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_app_corpus(case):
    path = ROOT / 'fixtures/projects' / case['fixture'] / '.agent_history/godot_api_cache.json'
    try:
        record = json.loads(path.read_bytes())
    except (OSError, ValueError):
        record = {}
    classes = record.get('classes', {}) if isinstance(record, dict) else {}
    cache = Cache(classes, case['reference_result']['version'])
    if case['expect']['ok']:
        result = app.call('api', case['args'], context(cache))
        assert result == case['expect']['result']
        assert app.call('api', case['args'], context(cache)) == result
        assert cache.calls == 2
    else:
        with pytest.raises(AppError) as caught:
            app.call('api', case['args'], context(cache))
        assert caught.value.kind == 'invalid_input'
        assert cache.calls == 0


@pytest.mark.parametrize('args', [None, [], 'C', {}, {'class_name': None},
                                  {'class_name': False}, {'class_name': []}])
def test_direct_app_invalid_before_port(args):
    cache = Cache()
    with pytest.raises(AppError) as caught:
        app.call('api', args, context(cache))
    assert caught.value.kind == 'invalid_input' and cache.calls == 0


def test_single_snapshot_tracks_changed_fake():
    cache = Cache({'C': {'inherits': None}}, 'old')
    assert app.call('api', {'class_name': 'C'}, context(cache))['cache_version'] == 'old'
    cache.value = ({'D': {'inherits': None}}, 'new')
    answer = app.call('api', {'class_name': 'D'}, context(cache))
    assert answer['found'] is True and answer['cache_version'] == 'new' and cache.calls == 2


def test_unknown_tool_before_io():
    cache = Cache()
    with pytest.raises(AppError) as caught:
        app.call('class_api', {'class_name': 'C'}, context(cache))
    assert caught.value.kind == 'unknown_tool' and cache.calls == 0
