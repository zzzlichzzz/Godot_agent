"""New A1 tests: real canonical calls compared to twice-recorded native cases."""
import hashlib
import json

import pytest

from .observations import CORPUS, ROOT, TARGETS, cases, observe


def _pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'LF': raw.count(b'\n'), 'CRLF': raw.count(b'\r\n')}


@pytest.mark.parametrize('name', list(TARGETS))
def test_verbatim_reference(name):
    manifest = json.loads((CORPUS/'manifest.json').read_text('utf-8'))
    path = ROOT/'python/substrate/verification'/(name+'.py')
    assert path.is_file(), 'A1 canonical target is genuinely absent before code'
    assert _pin(path) == manifest['provenance']['sources'][name]


def test_native_corpus_integrity():
    manifest = json.loads((CORPUS/'manifest.json').read_text('utf-8'))
    assert manifest['module'] == 'assistant.judge'
    assert manifest['stage'] == 'A1/reference-only'
    assert manifest['public_judge_implemented'] is False
    assert manifest['oracle_runs'] == 2 and manifest['oracle_differences'] == 0
    assert manifest['case_count'] == 118
    assert [case['id'] for case in cases()] == manifest['case_ids']
    assert len(set(manifest['case_ids'])) == 118
    assert _pin(CORPUS/'catalog.json') == manifest['catalog']
    for ident, expected in manifest['observations'].items():
        assert _pin(CORPUS/'observations'/(ident+'.json')) == expected, ident
    request = json.loads((CORPUS/'observations/runtime-final-pass.json').read_text('utf-8'))['result']
    assert request['report']['passed'] is True
    envelopes = request['envelopes']
    assert envelopes['pending']['request_id'] == 'a'*32
    assert envelopes['pending']['result_token'] == 'b'*48
    assert envelopes['public']['result_token'] == 'b'*48
    assert 'result_token' not in envelopes['game']
    headless = json.loads((CORPUS/'observations/headless-pass.json').read_text('utf-8'))['result']
    assert headless['receipt']['report']['status'] == 'passed'
    assert headless['project_unchanged'] and not headless['owned_leftovers']


@pytest.mark.parametrize('case', cases(), ids=lambda value: value['id'])
def test_native_parity(case, tmp_path):
    expected = json.loads((CORPUS/'observations'/(case['id']+'.json')).read_text('utf-8'))
    actual = observe(case, tmp_path/'canonical')
    assert actual == expected
