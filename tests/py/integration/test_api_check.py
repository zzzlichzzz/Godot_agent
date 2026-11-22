"""Actual registry corpus, fixture hashes, live snapshot freshness, no project writes."""
import hashlib
import json
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/verification/api_check'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('[0-9]*.json'))]


def tree(root):
    return ({p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*') if p.is_file()},
            sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir()))


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_corpus_dispatch_read_only(case, tmp_path, no_bundled_api_cache):
    project = ROOT / 'fixtures/projects' / case['fixture']
    before = tree(project)
    state = tmp_path / 'absent-state'
    agent = build_agent(project_root=project, profile='headless', state_dir=state)
    answer = agent.call('api_check', case['args'])
    assert agent.call('api_check', case['args']) == answer
    if case['expect']['ok']:
        assert answer == case['expect']
    else:
        assert answer['ok'] is False and answer['kind'] == case['expect']['kind']
        assert str(project) not in json.dumps(answer) and 'Traceback' not in json.dumps(answer)
    assert tree(project) == before and not state.exists()


def test_manifest_and_consumer_port():
    from python.modules.verification.api_check.module import MODULE
    from python.modules.verification.api_check.ports import ApiCache
    from python.substrate.store.api_cache_store import ApiCacheStore
    assert MODULE.id == 'verification.api_check'
    assert MODULE.provides_tools == ('api_check',) and MODULE.requires_ports == ('api_cache',)
    assert MODULE.requires == () and MODULE.contributes_to == ('verify',)
    assert MODULE.capabilities == ('verification.api_check',)
    assert isinstance(ApiCacheStore(ROOT), ApiCache)


def test_corpus_integrity():
    manifest = json.loads((CORPUS / 'manifest.json').read_bytes())
    assert len(CASES) == 52 and len(manifest['inputs']) == 13
    assert set(manifest['cases']) == {c['id'] + '.json' for c in CASES}
    for filename, info in manifest['cases'].items():
        raw = (CORPUS / filename).read_bytes()
        assert len(raw) == info['bytes'] and hashlib.sha256(raw).hexdigest() == info['sha256']
    for filename, info in manifest['inputs'].items():
        raw = (ROOT / 'fixtures/projects' / filename).read_bytes()
        assert len(raw) == info['bytes'] and hashlib.sha256(raw).hexdigest() == info['sha256']


@pytest.mark.parametrize('replacement', ['new', 'missing', 'broken', 'empty'])
def test_same_agent_observes_cache_changes(tmp_path, replacement, no_bundled_api_cache):
    project = tmp_path / 'project'; history = project / '.agent_history'; history.mkdir(parents=True)
    path = history / 'godot_api_cache.json'
    path.write_text(json.dumps({'classes': {'Node': {'methods': {'known': [0, 0]}}}}), encoding='utf-8')
    state = tmp_path / 'absent-state'
    agent = build_agent(project_root=project, profile='headless', state_dir=state)
    args = {'path': 'res://never-written.gd', 'content': 'extends Node\nself.known()\n'}
    assert agent.call('api_check', args)['result']['problems'] == []
    if replacement == 'missing':
        path.unlink()
    elif replacement == 'broken':
        path.write_bytes(b'{broken')
    else:
        path.write_text(json.dumps({'classes': {'Node': {'methods': {'other': [0, 0]}}}
                                   if replacement == 'new' else {}}), encoding='utf-8')
    before = tree(project)
    result = agent.call('api_check', args)['result']
    assert result['checked'] is (replacement == 'new')
    assert len(result['problems']) == (1 if replacement == 'new' else 0)
    assert result['unavailable'] == ([] if replacement == 'new' else [{'kind': 'api_cache', 'reason': 'no_cache'}])
    assert tree(project) == before and not state.exists()
