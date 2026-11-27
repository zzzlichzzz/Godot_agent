"""New A2 tests call canonical functions against the twice-observed native oracle."""
import hashlib
import json

import pytest

from .observations import CORPUS, ROOT, TARGETS, cases, observe


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'LF': raw.count(b'\n'), 'CRLF': raw.count(b'\r\n')}


@pytest.mark.parametrize('name', list(TARGETS))
def test_verbatim_reference(name):
    manifest = json.loads((CORPUS/'manifest.json').read_text('utf-8'))
    path = ROOT/(TARGETS[name].replace('.', '/')+'.py')
    assert path.is_file(), 'A2 canonical target genuinely absent before code'
    assert pin(path) == manifest['provenance']['sources'][name]


def test_native_corpus_integrity():
    manifest = json.loads((CORPUS/'manifest.json').read_text('utf-8'))
    assert manifest['module'] == 'assistant.judge'
    assert manifest['stage'] == 'A2/reference-read-prepare-only'
    assert manifest['public_judge_implemented'] is False
    assert manifest['case_count'] == 214
    assert manifest['oracle_runs'] == 2 and manifest['oracle_differences'] == 0
    assert manifest['case_ids'] == [case['id'] for case in cases()]
    assert len(set(manifest['case_ids'])) == 214
    assert pin(CORPUS/'catalog.json') == manifest['catalog']
    for ident, expected in manifest['observations'].items():
        path = CORPUS/'observations'/(ident+'.json')
        assert pin(path) == expected, ident
        envelope = json.loads(path.read_text('utf-8'))
        assert envelope['before'] == envelope['after'], ident


@pytest.mark.parametrize('case', cases(), ids=lambda value: value['id'])
def test_native_parity(case, tmp_path):
    expected = json.loads((CORPUS/'observations'/(case['id']+'.json')).read_text('utf-8'))
    actual = observe(case, tmp_path/'canonical')
    assert actual == expected
