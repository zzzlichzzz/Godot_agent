"""Consumer fake: refusals before ports, one snapshot even without extends."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from python.kernel.errors import AppError
from python.kernel.paths import PathPolicy
from python.modules.verification.api_check import app

ROOT = Path(__file__).resolve().parents[5]
CASES = [json.loads(p.read_bytes()) for p in sorted(
    (ROOT / 'fixtures/corpus/verification/api_check').glob('[0-9]*.json'))]


class Cache:
    def __init__(self, classes=None):
        self.value = (classes or {}, '4.6-fake')
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return self.value

    def classes(self):
        pytest.fail('memoized classes() must never be used')


def context(cache):
    def port(name):
        assert name == 'api_cache'
        return cache
    return SimpleNamespace(port=port, path_policy=PathPolicy())


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_app_corpus(case):
    path = ROOT / 'fixtures/projects' / case['fixture'] / '.agent_history/godot_api_cache.json'
    try:
        record = json.loads(path.read_bytes())
    except (OSError, ValueError):
        record = {}
    cache = Cache(record.get('classes', {}))
    if case['expect']['ok']:
        first = app.call('api_check', case['args'], context(cache))
        assert first == case['expect']['result']
        assert cache.calls == 1
        assert app.call('api_check', case['args'], context(cache)) == first and cache.calls == 2
    else:
        with pytest.raises(AppError) as caught:
            app.call('api_check', case['args'], context(cache))
        assert caught.value.kind == case['expect']['kind'] and cache.calls == 0


@pytest.mark.parametrize('args', [None, [], {}, {'path': None, 'content': ''},
                                   {'path': 'res://x.gd', 'content': None},
                                   {'path': 'res://x.gd', 'content': '\ud800'},
                                   {'path': 'res://x.gd', 'content': 'я' * (2 * 1024 * 1024 + 1)}])
def test_invalid_input_before_snapshot(args):
    cache = Cache()
    with pytest.raises(AppError) as caught:
        app.call('api_check', args, context(cache))
    assert caught.value.kind == 'invalid_input' and cache.calls == 0


def test_unknown_tool_before_snapshot():
    cache = Cache()
    with pytest.raises(AppError) as caught:
        app.call('check', {}, context(cache))
    assert caught.value.kind == 'unknown_tool' and cache.calls == 0


def test_exact_byte_limit_and_fresh_fake():
    cache = Cache({'Node': {'methods': {'known': [0, 0]}}})
    args = {'path': 'res://missing.gd', 'content': 'extends Node\nself.known()\n'}
    assert app.call('api_check', args, context(cache))['problems'] == []
    cache.value = ({'Node': {'methods': {'other': [0, 0]}}}, 'changed')
    assert len(app.call('api_check', args, context(cache))['problems']) == 1 and cache.calls == 2
    result = app.call('api_check', {'path': 'res://missing.gd', 'content': '#' + 'x' * (4 * 1024 * 1024 - 1)}, context(cache))
    assert result['checked'] is False and cache.calls == 3
