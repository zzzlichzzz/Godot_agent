"""B native-derived corpus through explicit integrated substrate imports."""
import hashlib
import json
import sys

import pytest

from tests.py.browser import runtime_cases as runtime

CORPUS = runtime.ROOT / 'fixtures/corpus/browser/runtime'
MANIFEST = json.loads((CORPUS / 'manifest.json').read_bytes())


@pytest.mark.parametrize('filename', MANIFEST['native_pins'])
def test_parser_reference_is_exact_native_bytes(filename):
    raw = (runtime.ROOT / 'python/substrate/llm/parsers' / (filename + '.py')).read_bytes()
    pin = MANIFEST['native_pins'][filename]
    assert len(raw) == pin['bytes']
    assert hashlib.sha256(raw).hexdigest() == pin['sha256']
    assert raw.count(b'\n') == pin['LF'] and raw.count(b'\r\n') == pin['CRLF']


@pytest.mark.parametrize('entry', MANIFEST['cases'], ids=lambda item: item['id'])
def test_integrated_native_observation(entry, monkeypatch, tmp_path):
    raw = (CORPUS / entry['file']).read_bytes()
    assert len(raw) == entry['bytes'] and hashlib.sha256(raw).hexdigest() == entry['sha256']
    case = json.loads(raw)
    assert case['id'] == entry['id']
    monkeypatch.setenv('GODOT_AGENT_CORPUS_DIR', str(tmp_path / 'parser-error-samples'))
    with runtime.references() as modules:
        assert runtime.observe(case, modules) == entry['expected']


def test_sanitize_is_used_inside_action_parser(monkeypatch, tmp_path):
    monkeypatch.setenv('GODOT_AGENT_CORPUS_DIR', str(tmp_path / 'parser-error-samples'))
    with runtime.references() as modules:
        obj, error = modules['parser_base'].parse_action_json('{"action":"done","text":"а\u200bб"}')
        assert error is None and obj == {'action': 'done', 'text': 'аб'}


def test_runtime_scope_does_not_leave_production_aliases():
    before = {name: sys.modules.get(name) for name in runtime.NAMES}
    with runtime.references():
        assert all(name in sys.modules for name in runtime.NAMES)
    assert {name: sys.modules.get(name) for name in runtime.NAMES} == before
