"""New tests call the real canonical facade against twice-frozen native behavior."""
import hashlib
import json
import pytest
from .observations import CORPUS, ROOT, TARGETS, cases, observe


def pin(path):
    raw=path.read_bytes()
    return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                LF=raw.count(b'\n'),CRLF=raw.count(b'\r\n'))


@pytest.mark.parametrize('name',list(TARGETS))
def test_verbatim_reference(name):
    manifest=json.loads((CORPUS/'manifest.json').read_text('utf-8'))
    path=ROOT/'python/substrate/code_intel'/(name+'.py')
    assert path.is_file(),'A3 canonical source genuinely absent before transfer'
    assert pin(path)==manifest['sources'][name]


def test_native_corpus_integrity():
    manifest=json.loads((CORPUS/'manifest.json').read_text('utf-8'))
    assert manifest['stage']=='A3/reference-read-prepare-only'
    assert not manifest['public_judge_implemented']
    assert manifest['case_count']==80 and manifest['oracle_runs']==2
    assert manifest['oracle_differences']==0
    assert [c['id'] for c in cases()]==manifest['case_ids']
    assert pin(CORPUS/'catalog.json')==manifest['catalog']
    for ident,expected in manifest['observations'].items():
        path=CORPUS/'observations'/(ident+'.json')
        assert pin(path)==expected
        value=json.loads(path.read_text('utf-8'))
        assert value['before']==value['after']
    refused=json.loads((CORPUS/'observations/unknown-receiver.json').read_text('utf-8'))
    assert refused['result']['prepare_rename']['code']=='unsafe'
    assert refused['result']['prepare_rename']['error']=='UnsafeRenameError'


@pytest.mark.parametrize('case',cases(),ids=lambda c:c['id'])
def test_native_parity(case,tmp_path):
    expected=json.loads((CORPUS/'observations'/(case['id']+'.json')).read_text('utf-8'))
    assert observe(case,tmp_path/'canonical')==expected
