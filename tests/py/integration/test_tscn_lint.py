"""Real composition/dispatch, exact corpus and read-only project SHA."""
import hashlib
import json
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/verification/tscn_lint'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('[0-9]*.json'))]


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_corpus_real_dispatch_and_read_only(case):
    project = ROOT / 'fixtures/projects' / case['fixture']
    before = hashes(project)
    agent = build_agent(project_root=project, profile='headless')
    answer = agent.call('check', case['args'])
    assert hashes(project) == before
    if case['expect']['ok']:
        assert answer == case['expect']
        assert all(isinstance(p, str) for p in answer['result']['problems'])
        assert agent.call('check', case['args']) == answer
    else:
        assert answer['ok'] is False and answer['kind'] == case['expect']['kind']
        assert str(project) not in json.dumps(answer)
    assert hashes(project) == before


def test_only_check_no_aggregator_or_apply():
    from python.modules.verification.tscn_lint.module import MODULE
    assert MODULE.id == 'verification.tscn_lint'
    assert MODULE.provides_tools == ('check',)
    assert MODULE.requires_ports == ('fs', 'api_cache')
    assert MODULE.capabilities == ('verification.tscn_lint',)
    assert MODULE.contributes_to == ('verify',) and MODULE.requires == ()


def test_context_inventory_and_pinned_case_need_only_new_read_name():
    """Red proof before authorized accepted-inventory/context edits."""
    names = ['analyze_rename', 'api', 'api_check', 'check', 'connections', 'context', 'functions',
             'gd_lint', 'node', 'node_delete_preview', 'node_rename_preview',
             'node_reparent_preview', 'paths_preview', 'read', 'scene', 'scene_deps', 'search', 'split_apply', 'split_gd_plan', 'split_gd_scan', 'split_plan', 'split_scan', 'usages',
             'verify', 'write_apply', 'write_preview', 'write_rollback']
    case = json.loads((ROOT / 'fixtures/corpus/context/gather/001-all-sections.json').read_bytes())
    pinned = case['expect']['result']['sections']['tools']
    assert pinned['names'] == names and pinned['count'] == len(names)
    assert pinned['effects']['check'] == 'read'
    agent = build_agent(project_root=ROOT / 'fixtures/minimal', profile='headless')
    result = agent.call('context', {'sections': ['tools']})['result']['sections']['tools']
    live_names = sorted(names + ['ask', 'assistant_confirm', 'assistant_plan', 'assistant_rollback', 'assistant_turn', 'chat', 'judge'])
    live_names.insert(live_names.index('usages'), 'tree')
    assert result == {'count': len(live_names), 'names': live_names,
                      'effects': {n: 'write' if n == 'split_apply' or n.startswith('write_') or n in ('assistant_confirm','assistant_plan','assistant_rollback','assistant_turn') else 'read' for n in live_names}}
