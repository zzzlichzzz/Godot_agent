"""C.9 actual dispatch, read-only byte proofs, manifest and optional contributions."""
import hashlib
import json
from pathlib import Path

import pytest

from python.runtime.bootstrap import build_agent

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/verification/check'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('[0-9]*.json'))]


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_corpus_dispatch_read_only_idempotent(case, tmp_path, no_bundled_api_cache):
    project = (ROOT / 'fixtures/projects' / case['fixture']).resolve()
    before = hashes(project)
    agent = build_agent(project_root=project, profile='headless', state_dir=tmp_path)
    actual = agent.call('verify', case['args'])
    if case['expect']['ok']:
        assert actual == case['expect']
    else:
        assert actual['ok'] is False and actual['kind'] == case['expect']['kind']
        assert str(project) not in json.dumps(actual)
    assert agent.call('verify', case['args']) == actual
    assert hashes(project) == before


def test_owner_and_all_contributions_are_discovered(tmp_path):
    agent = build_agent(project_root=CORPUS / 'project/common', state_dir=tmp_path)
    assert agent.conflicts() == []
    assert {'check', 'gd_lint', 'verify'} <= {t['name'] for t in agent.tools()}
    from python.modules.verification.check.domain.core import ORDER
    contributions = agent._registry.contributions('verify')
    assert [c.name for c in contributions] == ['api', 'gd', 'tscn']
    assert all(c.name in ORDER for c in contributions)
    assert len(agent.tools()) == 34
    assert {e.spec.name: e.spec.effects for e in agent._registry.entries()}['api_check'] == 'read'


@pytest.mark.parametrize('suffix', ['gd', 'tscn'])
def test_no_registered_contribution_is_disclosed(tmp_path, suffix):
    agent = build_agent(project_root=CORPUS / 'project/common', state_dir=tmp_path)
    agent._registry._contributions['verify'] = ()
    result = agent.call('verify', {'path': 'res://clean.' + suffix})['result']
    assert result['checked'] is False and result['kinds'] == []
    assert result['unavailable'][0] == {'kind': suffix, 'reason': 'no_module'}


def test_approved_manifest_inputs_and_cases_have_exact_hashes():
    manifest = json.loads((CORPUS / 'manifest.json').read_bytes())
    assert len(CASES) >= 26 and manifest['fixture_base'] == 'fixtures/projects'
    for section in ('cases', 'inputs'):
        for name, expected in manifest[section].items():
            raw = (CORPUS / name).read_bytes()
            assert {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} == expected


def test_syntax_messages_are_literal_not_reformatted(tmp_path):
    agent = build_agent(project_root=CORPUS / 'project/common', state_dir=tmp_path)
    assert agent.call('verify', {'path': 'res://duplicate.json'})['result']['problems'] == [
        'json syntax: duplicate JSON key: a']
    assert agent.call('verify', {'path': 'res://e.py'})['result']['problems'] == [
        'python syntax: invalid syntax (res://e.py, line 1)']


def test_registry_load_order_does_not_change_lint_api_problem_order(tmp_path):
    project = ROOT / 'fixtures/projects/corpus/verification/check/api'
    agent = build_agent(project_root=project, state_dir=tmp_path)
    assert [c.name for c in agent._registry.contributions('verify')] == ['api', 'gd', 'tscn']
    result = agent.call('verify', {'path': 'res://lint_api.gd'})['result']
    case = next(c for c in CASES if c['id'] == '063-lint_api_order')
    assert result['kinds'] == ['gd', 'api']
    assert result['problems'] == case['reference_lint'] + case['reference_api']


def test_real_scanner_limits_are_concatenated_not_owner_truncated(tmp_path):
    project = ROOT / 'fixtures/projects/corpus/verification/check/api'
    agent = build_agent(project_root=project, state_dir=tmp_path)
    case = next(c for c in CASES if c['id'] == '073-quota_8_plus_6')
    assert len(case['reference_lint']) == 8 and len(case['reference_api']) == 6
    assert agent.call('verify', {'path': 'res://quota.gd'})['result']['problems'] == (
        case['reference_lint'] + case['reference_api'])


def test_missing_api_contribution_is_not_false_clean(tmp_path):
    project = ROOT / 'fixtures/projects/corpus/verification/check/api'
    agent = build_agent(project_root=project, state_dir=tmp_path)
    agent._registry._contributions['verify'] = tuple(
        c for c in agent._registry.contributions('verify') if c.name != 'api')
    result = agent.call('verify', {'path': 'res://api_only.gd'})['result']
    assert result['checked'] is True and result['kinds'] == ['gd']
    assert result['unavailable'][0] == {'kind': 'api', 'reason': 'no_module'}


@pytest.mark.parametrize('requested,expected,snapshots', [
    (None, ['gd', 'api'], 1), (['api', 'gd', 'api'], ['gd', 'api'], 1),
    (['api'], ['api'], 1), (['gd'], ['gd'], 0), (['py'], [], 0),
])
def test_actual_contribution_never_rereads_source_and_snapshots_only_when_selected(requested, expected, snapshots):
    from types import SimpleNamespace
    from python.kernel.paths import PathPolicy
    from python.modules.verification.api_check.tools import CONTRIBUTIONS as API
    from python.modules.verification.gd_lint.tools import CONTRIBUTIONS as GD
    from python.modules.verification.check import app
    raw = b'extends Node2D\nvar x: int = "wrong"\nfunc run():\n\tself.rotatte(1)\n'
    calls, seen = [], []
    fs = SimpleNamespace(is_file=lambda path: (calls.append(('is_file', path)) or True),
                         read_raw=lambda path: (calls.append(('read_raw', path)) or raw))
    cache = SimpleNamespace(snapshot=lambda: (seen.append('snapshot') or {
        'Node2D': {'methods': {'rotate': [1, 1]}}}, 'fixture'))
    ctx = SimpleNamespace(port=lambda name: {'fs': fs, 'api_cache': cache}[name],
                          path_policy=PathPolicy(), registry=SimpleNamespace(contributions=lambda _: (*API, *GD)))
    args = {'path': 'res://x.gd'}
    if requested is not None:
        args['kinds'] = requested
    result = app.call('verify', args, ctx)
    assert result['kinds'] == expected and len(seen) == snapshots
    assert calls == [('is_file', 'x.gd'), ('read_raw', 'x.gd')]
    if expected == ['gd', 'api']:
        assert 'int' in result['problems'][0] and 'self.rotatte' in result['problems'][1]
    assert result['checked'] is bool(expected)
