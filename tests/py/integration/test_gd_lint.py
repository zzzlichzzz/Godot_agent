"""Real discovery/dispatch/fs contract and read-only refusals, no old host."""
import json
from pathlib import Path

import pytest

from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.runtime.bootstrap import build_agent
from python.substrate.fs.disk_fs import DiskFileSystem

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / 'fixtures/corpus/verification/gd_lint/project'


@pytest.fixture
def agent():
    return build_agent(project_root=PROJECT, profile='headless')


def test_module_contract_and_real_composition(agent):
    from python.modules.verification.gd_lint.module import MODULE
    from python.modules.verification.gd_lint.tools import GD_LINT
    from python.modules.verification.gd_lint.ports import RawReader
    assert MODULE.id == 'verification.gd_lint'
    assert MODULE.provides_tools == ('gd_lint',)
    assert MODULE.requires_ports == ('fs',)
    assert MODULE.corpus == 'corpus'
    assert isinstance(DiskFileSystem(PROJECT), RawReader)
    assert GD_LINT.effects == 'read' and GD_LINT.idempotent
    assert GD_LINT.limits == {'max_file_bytes': READ_TEXT_MAX_BYTES, 'max_errors': 8}
    card = json.loads((ROOT / 'contract/capabilities/gd_lint.json').read_bytes())
    assert card == GD_LINT.contract('verification.gd_lint', 'verification.gd_lint')
    assert 'gd_lint' in {tool['name'] for tool in agent.tools()}


@pytest.mark.parametrize('path', ['scripts/clean.gd', 'res://scripts/clean.gd'])
def test_real_file_is_read_only_and_idempotent(agent, path):
    target = PROJECT / 'scripts/clean.gd'
    before = target.read_bytes()
    answer = agent.call('gd_lint', {'path': path})
    assert answer['ok'], answer
    assert answer['result'] == {'findings': [], 'truncated': False, 'checked_bytes': len(before)}
    assert agent.call('gd_lint', {'path': path}) == answer
    assert target.read_bytes() == before


@pytest.mark.parametrize('args', [{}, {'path': 5}, {'path': None}, {'path': True}, {'path': []},
                                  {'path': {}}, {'path': 'scripts/clean.gd', 'extra': True}])
def test_invalid_schema_is_typed(agent, args):
    assert agent.call('gd_lint', args)['kind'] == 'invalid_input'


@pytest.mark.parametrize('path', ['', '../outside.gd', 'res://../outside.gd', '..\\outside.gd',
                                  '/outside.gd', 'C:/outside.gd', '\\\\host\\share\\x.gd',
                                  'scripts/x\x00.gd', 'user://x.gd', 'file://outside.gd'])
def test_outside_paths_are_invalid_before_io(agent, path):
    answer = agent.call('gd_lint', {'path': path})
    assert not answer['ok'] and answer['kind'] == 'invalid_input'


@pytest.mark.parametrize('path', ['scripts/clean.txt', 'scene.tscn', 'resource.tres'])
def test_only_gd_files(agent, path):
    assert agent.call('gd_lint', {'path': path})['kind'] == 'invalid_input'


@pytest.mark.parametrize('path', ['addons/foreign/x.gd', '.agent_history/x.gd'])
def test_policy_refuses_protected_paths(agent, path):
    assert agent.call('gd_lint', {'path': path})['kind'] == 'denied'


def test_missing_file_is_typed_without_host_path(agent):
    answer = agent.call('gd_lint', {'path': 'scripts/missing.gd'})
    assert answer['kind'] == 'not_found'
    assert str(PROJECT) not in json.dumps(answer)


def test_real_read_limit(tmp_path):
    (tmp_path / 'large.gd').write_bytes(b'#' * (READ_TEXT_MAX_BYTES + 1))
    agent = build_agent(project_root=tmp_path, profile='headless', ports={'fs': DiskFileSystem(tmp_path)})
    assert agent.call('gd_lint', {'path': 'large.gd'})['kind'] == 'invalid_input'


def test_context_lists_new_read_tool_without_hiding_old_tools(agent):
    """Authorized composition snapshot refresh: real registry, no filtered list."""
    answer = agent.call('context', {'sections': ['tools']})
    assert answer['ok'], answer
    names = ['analyze_rename', 'api', 'api_check', 'ask', 'assistant_confirm', 'assistant_plan', 'assistant_rollback', 'assistant_turn', 'chat', 'check', 'connections', 'context', 'functions', 'gd_lint', 'judge', 'node', 'node_delete_preview', 'node_rename_preview', 'node_reparent_preview', 'paths_preview', 'read', 'scene', 'scene_deps', 'search', 'split_apply', 'split_gd_plan', 'split_gd_scan', 'split_plan', 'split_scan', 'usages',
             'verify', 'write_apply', 'write_preview', 'write_rollback']
    effects = {name: 'write' if name == 'split_apply' or name.startswith('write_') or name in ('assistant_confirm','assistant_plan','assistant_rollback','assistant_turn') else 'read' for name in names}
    assert answer['result']['sections']['tools'] == {'count': 34, 'names': names, 'effects': effects}
