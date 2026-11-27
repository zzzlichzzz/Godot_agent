"""C.17 dispatch, input provenance, read-only/idempotence; no native test imports."""
import hashlib
import json
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/editing/split_py'
CASES = [c for p in sorted(CORPUS.glob('[0-9]*.json')) if (c := json.loads(p.read_bytes()))['tool']=='split_scan']


def tree(root):
    return ({p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*') if p.is_file()},
            sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir()))


@pytest.mark.parametrize('case', CASES, ids=lambda c:c['id'])
def test_corpus_dispatch(case, tmp_path):
    project = ROOT / 'fixtures/projects' / case['fixture']
    before = tree(project)
    state = tmp_path/'absent-state'
    agent = build_agent(project_root=project, profile='headless', state_dir=state)
    answer = agent.call('split_scan',case['args'])
    assert agent.call('split_scan',case['args']) == answer
    if case['expect']['ok']:
        assert answer == case['expect']
    else:
        assert not answer['ok'] and answer['kind'] == case['expect']['kind']
        if 'expected_message' in case:
            assert answer['message'] == case['expected_message']
        assert str(project) not in json.dumps(answer) and 'Traceback' not in json.dumps(answer)
    assert tree(project) == before and not state.exists()


def test_provenance():
    manifest = json.loads((CORPUS/'manifest.json').read_bytes())
    apply_inputs = manifest['apply_capture']['inputs']
    assert len(CASES)==47 and len([p for p in manifest['inputs'] if p not in manifest['c18_recut']['inputs'] and p not in apply_inputs])==163
    for folder, facts in [(CORPUS,manifest['cases']),(ROOT/'fixtures/projects',manifest['inputs'])]:
        for rel, info in facts.items():
            raw = (folder/rel).read_bytes()
            assert info == {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    for case in CASES:
        raw = case['reference_result']
        if raw is not None:
            assert 'schema' not in raw
            projected = {**{k:raw[k] for k in ('stem','counts','hard_files','soft_files','truncated')},
                         'donor':raw['rel'], 'occurrences':[{**{k:x[k] for k in ('line','kind','text')},'file':x['rel']}
                                                          for x in raw['occurrences']]}
            if case['expect']['ok']:
                assert projected == case['expect']['result']
            else:
                assert case['contract_boundary']


def test_module_and_existing_fs():
    from python.modules.editing.split_py.module import MODULE
    from python.modules.editing.split_py.ports import FileSystem
    from python.substrate.fs.disk_fs import DiskFileSystem
    assert MODULE.id=='editing.split_py' and MODULE.provides_tools==('split_scan','split_plan','split_apply')
    assert MODULE.requires_ports==('fs','journal') and MODULE.capabilities==('editing.split_py',)
    assert MODULE.requires==('editing.write_apply',) and MODULE.contributes_to==() and MODULE.corpus=='corpus'
    assert isinstance(DiskFileSystem(ROOT),FileSystem)


def test_real_agent_policy(tmp_path):
    fixture = ROOT/'fixtures/projects/corpus/editing/split_py/hard_soft_overlap'
    project = ROOT.parents[1]
    args = {'path':'res://'+(fixture/'donor.py').relative_to(project).as_posix()}
    before = tree(fixture)
    state = tmp_path/'absent-state'
    closed = build_agent(project_root=project,profile='headless',state_dir=state)
    assert closed.call('split_scan',args)['kind']=='denied'
    opened = build_agent(project_root=project,profile='headless',allow_self_edit=True,state_dir=state)
    assert opened.call('split_scan',args)==next(c['expect'] for c in CASES if c['id']=='014-hard_soft_overlap')
    assert tree(fixture)==before and not state.exists()
