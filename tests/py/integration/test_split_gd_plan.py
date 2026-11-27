import hashlib
import json
from pathlib import Path

import pytest

from python.kernel.schema import validate
from python.modules.editing.split_gd.tools import PLAN
from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/editing/split_gd'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('1[0-9][0-9]-*.json'))]


def tree(root):
    return ({p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*') if p.is_file()},
            sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir()))


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_plan_native_corpus_readonly_idempotent(case, tmp_path):
    fixture = ROOT / 'fixtures/projects' / case['fixture']
    before = tree(fixture)
    state = tmp_path / 'absent-state'
    agent = build_agent(project_root=fixture, profile='headless', state_dir=state)
    answer = agent.call('split_gd_plan', case['args'])
    assert agent.call('split_gd_plan', case['args']) == answer
    if case['expect']['ok']:
        assert answer == case['expect']
        if case['id'] in ('141-bom_crlf', '142-crlf', '143-cr_only'):
            assert case['reference_public']['newline'] == case['reference_result']['newline'] == '\n'
            assert answer['result']['newline'] == ('\r' if case['id'] == '143-cr_only' else '\r\n')
            assert answer['result']['donor_sha256'] == case['reference_public']['donor_sha256']
        assert not ({'addon_dir', 'project_root', 'donor_abs', 'donor_content'} & answer['result'].keys())
        assert all('content' not in module for module in answer['result']['modules'])
    else:
        assert answer['ok'] is False and answer['kind'] == case['expect']['kind']
        if case['id'] in ('108-target_below_minimum', '109-target_above_maximum', '130-empty_funcs'):
            assert answer['message'] == case['expected_message'] == case['expect']['message']
        elif 'expected_message' in case and not validate(case['args'], PLAN.args):
            assert answer['message'] == case['expected_message']
    assert str(fixture) not in json.dumps(answer) and 'Traceback' not in json.dumps(answer)
    assert tree(fixture) == before and not state.exists()


def test_plan_manifest_keeps_scan_provenance_and_raw_content():
    manifest = json.loads((CORPUS / 'manifest.json').read_bytes())
    assert len(CASES) == 55 and manifest['plan_capture']['native_calls'] == 92
    assert sum(case['reference_result'] is not None for case in CASES) == 25
    assert sum(case['reference_error'] is not None for case in CASES) == 21
    assert sum(case['contract_refusal'] is not None for case in CASES) == 9
    for case in CASES:
        if case['reference_result'] is not None:
            raw = case['reference_result']
            assert raw['donor_content'] is not None and all('content' in module for module in raw['modules'])
            public = case['reference_public']
            assert public['donor_content'] is None and all('content' not in module for module in public['modules'])
            projected = {k: v for k, v in public.items() if k not in ('addon_dir', 'project_root', 'donor_abs', 'donor_content')}
            if case['id'] in ('141-bom_crlf', '142-crlf', '143-cr_only'):
                assert public['newline'] == raw['newline'] == '\n'
                projected['newline'] = '\r' if case['id'] == '143-cr_only' else '\r\n'
            assert projected == case['expect']['result']
    assert manifest['c16_recut']['case_count'] == 102
    assert set(manifest['c16_recut']['cases']) == {'108-target_below_minimum', '109-target_above_maximum',
        '130-empty_funcs', '141-bom_crlf', '142-crlf', '143-cr_only'}
    assert len([k for k in manifest['cases'] if int(k[:3]) < 101]) == 47
    assert len([k for k in manifest['inputs'] if not k.startswith('corpus/editing/split_gd_plan/')]) == 136
    for folder, facts in [(CORPUS, manifest['cases']), (ROOT / 'fixtures/projects', manifest['inputs'])]:
        for rel, info in facts.items():
            raw = (folder / rel).read_bytes()
            assert info == {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def test_consumer_snapshot_protocol_uses_existing_adapter():
    from python.modules.editing.split_gd.module import MODULE
    from python.modules.editing.split_gd.ports import ApiCache
    from python.substrate.store.api_cache_store import ApiCacheStore
    assert MODULE.requires_ports == ('fs', 'api_cache')
    assert isinstance(ApiCacheStore(project_root=ROOT), ApiCache)
