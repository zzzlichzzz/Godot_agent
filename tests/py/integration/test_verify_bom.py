"""F1 consumers share the file boundary; C.8 candidate boundary stays literal."""
import hashlib
import json
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/verification/check'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('*-f1_*.json'))]


@pytest.mark.parametrize('case', [c for c in CASES if c['args']['path'].endswith('.gd')],
                         ids=lambda c: c['id'])
def test_gd_and_verify_share_file_decoding(case, tmp_path, no_bundled_api_cache):
    project = CORPUS / 'project/f1_bom'
    path = project / case['args']['path'].removeprefix('res://')
    raw = path.read_bytes()
    before = hashlib.sha256(raw).hexdigest()
    agent = build_agent(project_root=project, profile='headless', state_dir=tmp_path)
    checked = agent.call('verify', case['args'])
    gd = agent.call('gd_lint', case['args'])
    assert checked == case['expect'] and gd['ok'] is True
    assert [finding['message'] for finding in gd['result']['findings']] == checked['result']['problems']
    assert gd['result']['checked_bytes'] == len(raw)
    assert agent.call('gd_lint', case['args']) == gd
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize('case', [c for c in CASES if 'candidate_reference_result' in c],
                         ids=lambda c: c['id'])
def test_tscn_candidate_keeps_bom(case, tmp_path):
    project = CORPUS / 'project/f1_bom'
    agent = build_agent(project_root=project, profile='headless', state_dir=tmp_path)
    content = case['candidate_content']
    fixed, problems = case['candidate_reference_result']
    answer = agent.call('check', {'path': case['args']['path'], 'content': content})
    assert answer == {'ok': True, 'result': {
        'fixed': fixed, 'problems': problems, 'changed': fixed != content}}
    assert agent.call('verify', case['args']) == case['expect']
