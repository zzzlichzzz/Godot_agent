"""Discovered scene, default composition, strict read contract."""
import copy
import json
from pathlib import Path
import pytest
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.schema import validate
from python.runtime.bootstrap import build_agent
from python.substrate.fs.disk_fs import DiskFileSystem

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/scene_model/tree'
PROJECT = CORPUS / 'project'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('*.json')) if p.name != 'manifest.json']


@pytest.fixture(scope='module')
def agent():
    return build_agent(project_root=PROJECT, profile='headless')


def test_discovery_contract_and_structural_port(agent):
    from python.modules.scene_model.tree.module import MODULE
    from python.modules.scene_model.tree.ports import RawReader
    from python.modules.scene_model.tree.tools import SCENE
    assert MODULE.id == 'scene_model.tree' and MODULE.corpus == 'corpus'
    assert MODULE.provides_tools == ('scene',) and MODULE.requires_ports == ('fs',)
    assert isinstance(DiskFileSystem(PROJECT), RawReader)
    assert SCENE.effects == 'read' and SCENE.idempotent and SCENE.cost == 'cheap'
    assert SCENE.limits == {'max_file_bytes':READ_TEXT_MAX_BYTES,'max_chars':12000}
    assert json.loads((ROOT / 'contract/capabilities/scene.json').read_bytes()) == SCENE.contract('scene_model.tree','scene_model.tree')
    assert 'scene' in [tool['name'] for tool in agent.tools()]


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_scene_literal_parity_and_read_only(agent, case):
    path = PROJECT / case['args']['path'].removeprefix('res://')
    before = path.read_bytes() if path.exists() else None
    answer = agent.call('scene', case['args'])
    expected = case['expect']
    assert answer['ok'] is expected['ok']
    if expected['ok']:
        from python.modules.scene_model.tree.tools import SCENE
        assert answer['result']['text'].encode('utf-8') == expected['result']['text'].encode('utf-8')
        assert answer['result'] == expected['result']
        assert not validate(answer['result'], SCENE.result)
        assert agent.call('scene', case['args']) == answer
    else:
        assert answer['kind'] == expected['kind'] and answer['message'] == expected['message']
        assert str(PROJECT) not in json.dumps(answer)
    if before is not None:
        assert path.read_bytes() == before


@pytest.mark.parametrize('args', [{},{'path':None},{'path':5},{'path':True},{'path':[]},
    {'path':'scenes/simple.tscn','extra':1},{'path':'scenes/simple.tscn','max_chars':-1},
    {'path':'scenes/simple.tscn','max_chars':True},{'path':'scenes/simple.tscn','max_chars':1.5},
    {'path':'scenes/simple.tscn','max_chars':None}])
def test_invalid_input_schema(agent, args):
    assert agent.call('scene', args)['kind'] == 'invalid_input'


@pytest.mark.parametrize('path', ['', '../escape.tscn','res://../escape.tscn',r'..\escape.tscn',
    '/absolute.tscn',r'C:\secret.tscn',r'\\server\share\a.tscn','x\x00.tscn','user://a.tscn','file://a.tscn'])
def test_unsafe_paths_are_refused(agent, path):
    assert agent.call('scene', {'path':path})['kind'] == 'invalid_input'


@pytest.mark.parametrize('path', ['addons/other/a.tscn','.agent_history/a.tscn'])
def test_protected_project_paths(agent, path):
    assert agent.call('scene', {'path':path})['kind'] == 'denied'


def test_actual_file_limit(tmp_path):
    (tmp_path / 'huge.tscn').write_bytes(b' ' * (READ_TEXT_MAX_BYTES + 1))
    answer = build_agent(project_root=tmp_path, profile='headless').call('scene', {'path':'huge.tscn'})
    assert answer['kind'] == 'invalid_input' and str(tmp_path) not in json.dumps(answer)


def test_strict_result_rejects_uncontracted_runtime_field(agent):
    from python.modules.scene_model.tree.tools import SCENE
    actual = agent.call('scene', {'path':'scenes/simple.tscn'})['result']
    assert not validate(actual, SCENE.result)
    mutated = copy.deepcopy(actual); mutated['uncontracted'] = True
    assert validate(mutated, SCENE.result)
    for field in ('nodes','connections','resources'):
        mutated = copy.deepcopy(actual); del mutated[field]
        assert validate(mutated, SCENE.result)


def test_context_retains_old_tools_and_advertises_scene_as_read(agent):
    result = agent.call('context', {'sections':['tools']})['result']['sections']['tools']
    names = ['analyze_rename','api','api_check','ask','assistant_confirm','assistant_plan','assistant_rollback','assistant_turn','chat','check','connections','context','functions','gd_lint','judge','node','node_delete_preview','node_rename_preview','node_reparent_preview','paths_preview','read','scene','scene_deps','search','split_apply','split_gd_plan','split_gd_scan','split_plan','split_scan','usages',
             'verify','write_apply','write_preview','write_rollback']
    effects = {name:'write' if name == 'split_apply' or name.startswith('write_') or name in ('assistant_confirm','assistant_plan','assistant_rollback','assistant_turn') else 'read' for name in names}
    assert result == {'count':34,'names':names,'effects':effects}
