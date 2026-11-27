"""Registry parity, raw provenance and byte read-only/idempotence through real fs."""
import hashlib
import json
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/editing/split_gd'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('[0-9]*.json'))]
CASES = [case for case in CASES if case['tool'] == 'split_gd_scan']


def tree(root):
    return ({p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*') if p.is_file()},
            sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir()))


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_corpus_dispatch_read_only(case, tmp_path):
    project = ROOT / 'fixtures/projects' / case['fixture']
    before = tree(project)
    state = tmp_path / 'absent-state'
    agent = build_agent(project_root=project, profile='headless', state_dir=state)
    answer = agent.call('split_gd_scan', case['args'])
    assert agent.call('split_gd_scan', case['args']) == answer
    if case['expect']['ok']:
        assert answer == case['expect']
    else:
        assert answer['ok'] is False and answer['kind'] == case['expect']['kind']
        assert str(project) not in json.dumps(answer) and 'Traceback' not in json.dumps(answer)
    assert tree(project) == before and not state.exists()


def test_provenance_inputs_and_projection():
    manifest = json.loads((CORPUS / 'manifest.json').read_bytes())
    scan_inputs = {k: v for k, v in manifest['inputs'].items() if not k.startswith('corpus/editing/split_gd_plan/')}
    assert len(CASES) == 47 and len(scan_inputs) == 136
    assert len([c for c in CASES if c['reference_result'] is not None]) == 34
    for case in CASES:
        if case['reference_result'] is not None:
            projected = {k: v for k, v in case['reference_result'].items() if k != 'schema'}
            assert case['reference_result']['schema'] == 1 and projected == case['expect']['result']
        else:
            assert case['contract_refusal'] and not case['expect']['ok']
    for folder, facts in [(CORPUS, manifest['cases']), (ROOT / 'fixtures/projects', manifest['inputs'])]:
        for rel, info in facts.items():
            raw = (folder / rel).read_bytes()
            assert info == {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def test_manifest_owned_fs_only():
    from python.modules.editing.split_gd.module import MODULE
    from python.modules.editing.split_gd.ports import FileSystem
    from python.substrate.fs.disk_fs import DiskFileSystem
    assert MODULE.id == 'editing.split_gd' and MODULE.version == '0.1.0'
    assert MODULE.provides_tools == ('split_gd_scan', 'split_gd_plan') and MODULE.requires_ports == ('fs', 'api_cache')
    assert MODULE.requires == () and MODULE.contributes_to == ()
    assert MODULE.capabilities == ('editing.split_gd',) and MODULE.corpus == 'corpus'
    assert isinstance(DiskFileSystem(ROOT), FileSystem)


def test_addon_access_uses_existing_policy(tmp_path):
    project = ROOT.parents[1]
    fixture = ROOT / 'fixtures/projects/corpus/editing/split_gd/mixed'
    before = tree(fixture)
    args = {'path': 'res://' + (fixture / 'donor.gd').relative_to(project).as_posix()}
    state = tmp_path / 'absent-state'
    closed = build_agent(project_root=project, profile='headless', state_dir=state)
    assert closed.call('split_gd_scan', args)['kind'] == 'denied'
    opened = build_agent(project_root=project, allow_self_edit=True, profile='headless', state_dir=state)
    result = opened.call('split_gd_scan', args)
    assert result == next(c['expect'] for c in CASES if c['id'] == '002-mixed')
    assert tree(fixture) == before and not state.exists()
