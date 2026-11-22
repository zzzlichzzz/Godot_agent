"""Real registry/dispatch corpus, SHA/dirs and freshness on the same agent."""
import hashlib
import json
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/engine_kb/class_api'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('[0-9]*.json'))]


def tree(root):
    return ({p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*') if p.is_file()},
            sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir()))


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_actual_old_corpus_dispatch_read_only(case, tmp_path, no_bundled_api_cache):
    project = ROOT / 'fixtures/projects' / case['fixture']
    before = tree(project)
    agent = build_agent(project_root=project, profile='headless', state_dir=tmp_path / 'absent-state')
    first = agent.call('api', case['args'])
    assert tree(project) == before
    assert agent.call('api', case['args']) == first
    if case['expect']['ok']:
        assert first == case['expect']
    else:
        assert first['ok'] is False and first['kind'] == case['expect']['kind']
        assert str(project) not in json.dumps(first)
    assert tree(project) == before and not (tmp_path / 'absent-state').exists()


def test_only_api_manifest_and_card():
    from python.modules.engine_kb.class_api.module import MODULE
    assert MODULE.provides_tools == ('api',) and MODULE.requires_ports == ('api_cache',)
    assert MODULE.id == 'engine_kb.class_api' and MODULE.capabilities == ('engine_kb.class_api',)
    assert MODULE.requires == () and MODULE.contributes_to == ()
    assert (ROOT / 'contract/capabilities/api.json').is_file()


def test_corpus_integrity():
    manifest = json.loads((CORPUS / 'manifest.json').read_bytes())
    assert len(CASES) == 26 and len(manifest['inputs']) == 27
    assert set(manifest['cases']) == {c['id'] + '.json' for c in CASES}
    for filename, info in manifest['cases'].items():
        raw = (CORPUS / filename).read_bytes()
        assert len(raw) == info['bytes'] and hashlib.sha256(raw).hexdigest() == info['sha256']
    for filename, info in manifest['inputs'].items():
        raw = (ROOT / 'fixtures/projects' / filename).read_bytes()
        assert len(raw) == info['bytes'] and hashlib.sha256(raw).hexdigest() == info['sha256']


@pytest.mark.parametrize('replacement', ['new', 'missing', 'broken', 'empty'])
def test_same_agent_reads_replaced_or_removed_cache(tmp_path, replacement, no_bundled_api_cache):
    project = tmp_path / 'project'; history = project / '.agent_history'; history.mkdir(parents=True)
    path = history / 'godot_api_cache.json'
    path.write_text(json.dumps({'godot_version': 'old', 'classes': {'Old': {'inherits': None}}}), encoding='utf-8')
    agent = build_agent(project_root=project, profile='headless', state_dir=tmp_path / 'absent-state')
    assert agent.call('api', {'class_name': 'Old'})['result']['found'] is True
    if replacement == 'missing':
        path.unlink()
    elif replacement == 'broken':
        path.write_bytes(b'{broken')
    else:
        path.write_text(json.dumps({'godot_version': 'new', 'classes':
                                   {'New': {'inherits': None}} if replacement == 'new' else {}}), encoding='utf-8')
    before = tree(project)
    result = agent.call('api', {'class_name': 'New'})['result']
    assert result['found'] is (replacement == 'new')
    assert result['cache_version'] == ('new' if replacement == 'new' else '')
    assert result['unavailable'] == ([] if replacement == 'new' else [{'kind': 'api_cache', 'reason': 'no_cache'}])
    assert tree(project) == before and not (tmp_path / 'absent-state').exists()
