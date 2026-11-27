"""C.18 dispatch/provenance, native errors as data, read-only repeat and F11."""
import hashlib
import json
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent
from python.substrate.fs.disk_fs import DiskFileSystem

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT/'fixtures/corpus/editing/split_py'
CASES = [c for p in sorted(CORPUS.glob('[0-9]*.json'))
         if (c := json.loads(p.read_bytes()))['tool'] == 'split_plan']


def tree(root):
    return [(p.relative_to(root).as_posix(),p.is_dir(),
             None if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(root.rglob('*'))]


@pytest.mark.parametrize('case', CASES, ids=lambda c:c['id'])
def test_native_corpus_dispatch(case, tmp_path, monkeypatch):
    project = ROOT/'fixtures/projects'/case['fixture']
    before = tree(project)
    state = tmp_path/'absent-state'
    agent = build_agent(project_root=project,profile='headless',state_dir=state)
    actual = agent.call('split_plan',case['args'])
    assert agent.call('split_plan',case['args']) == actual
    if case['expect']['ok']:
        assert actual == case['expect']
    else:
        assert actual['ok'] is False and actual['kind'] == case['expect']['kind']
        if 'expected_message' in case:
            assert actual['message'] == case['expected_message']
    assert str(project) not in json.dumps(actual) and 'Traceback' not in json.dumps(actual)
    assert tree(project) == before and not state.exists()


def test_c18_provenance_preserves_c17_and_directory():
    manifest = json.loads((CORPUS/'manifest.json').read_bytes())
    assert len(CASES) == 49 and len(manifest['c18_recut']['cases']) == 49
    assert manifest['c18_recut']['native_calls'] == 102
    assert manifest['c18_recut']['oracle_unchanged'] and manifest['c18_recut']['write_helpers_blocked']
    for base,facts in [(CORPUS,manifest['cases']),(ROOT/'fixtures/projects',manifest['inputs'])]:
        for rel,fact in facts.items():
            raw = (base/rel).read_bytes()
            assert fact == {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    directory = ROOT/'fixtures/projects/corpus/editing/split_py/plan_occupied-directory/part.py'
    assert directory.is_dir() and not list(directory.iterdir())


def test_original_hooked_native_refs_null_dispatch(monkeypatch,tmp_path):
    case = next(c for c in CASES if c['id']=='072-plan-refs-null')
    project = ROOT/'fixtures/projects'/case['fixture']
    original, calls, before = DiskFileSystem.is_file, [], tree(project)
    def is_file(fs,rel):
        if rel==case['args']['path'][6:]:
            calls.append(rel)
            if len(calls)%2==0:
                return False
        return original(fs,rel)
    monkeypatch.setattr(DiskFileSystem,'is_file',is_file)
    state = tmp_path/'absent-state'
    agent = build_agent(project_root=project,profile='headless',state_dir=state)
    expected = {'ok':True,'result':dict(case['expect']['result'],refs=None)}
    assert agent.call('split_plan',case['args'])==expected
    assert agent.call('split_plan',case['args'])==expected
    assert calls==['donor.py']*4 and tree(project)==before and not state.exists()


def test_exactly_four_production_exists_calls():
    calls = [(p.relative_to(ROOT).as_posix(),line.strip()) for p in (ROOT/'python').rglob('*.py')
             if 'tests' not in p.parts for line in p.read_text(encoding='utf-8-sig').splitlines()
             if 'fs.exists(' in line]
    assert len(calls) == 4
    assert {p for p,line in calls} == {'python/modules/editing/split_gd/plan_io.py',
                                     'python/modules/editing/split_py/app.py',
                                     'python/modules/editing/split_py/apply_flow.py',
                                     'python/modules/editing/paths_preview/ports.py'}
