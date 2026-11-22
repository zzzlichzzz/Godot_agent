"""Discovered node, actual fs, strict schema and accepted scene coexistence."""
import copy
import json
from pathlib import Path
import pytest
from python.kernel.limits import READ_TEXT_MAX_BYTES
from python.kernel.schema import validate
from python.runtime.bootstrap import build_agent
from python.substrate.fs.disk_fs import DiskFileSystem

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'fixtures/corpus/scene_model/node_info'
PROJECT = CORPUS / 'project'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('*.json')) if p.name != 'manifest.json']


@pytest.fixture(scope='module')
def agent():
    return build_agent(project_root=PROJECT,profile='headless')


def test_discovery_contract_and_structural_port(agent):
    from python.modules.scene_model.node_info.module import MODULE
    from python.modules.scene_model.node_info.ports import RawReader
    from python.modules.scene_model.node_info.tools import NODE
    assert MODULE.id == 'scene_model.node_info' and MODULE.corpus == 'corpus'
    assert MODULE.provides_tools == ('node',) and MODULE.requires_ports == ('fs',)
    assert isinstance(DiskFileSystem(PROJECT),RawReader)
    assert NODE.effects == 'read' and NODE.idempotent and NODE.cost == 'cheap'
    assert NODE.limits == {'max_file_bytes':READ_TEXT_MAX_BYTES}
    assert json.loads((ROOT / 'contract/capabilities/node.json').read_bytes()) == NODE.contract(MODULE.id,MODULE.id)
    assert 'node' in [tool['name'] for tool in agent.tools()]


@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_node_literal_parity_read_only(agent,case):
    path = PROJECT / case['args']['path'].removeprefix('res://')
    before = path.read_bytes() if path.exists() else None
    actual = agent.call('node',case['args']); expected = case['expect']
    assert actual['ok'] is expected['ok']
    if expected['ok']:
        from python.modules.scene_model.node_info.tools import NODE
        assert actual['result'] == expected['result']
        assert not validate(actual['result'],NODE.result)
        assert agent.call('node',case['args']) == actual
    else:
        assert actual['kind'] == expected['kind'] and actual['message'].encode('utf-8') == expected['message'].encode('utf-8')
        assert str(PROJECT) not in json.dumps(actual)
    if before is not None:
        assert path.read_bytes() == before


@pytest.mark.parametrize('args',[{}, {'path':'scenes/hierarchy.tscn'}, {'path':None,'node':'.'},
    {'path':3,'node':'.'}, {'path':True,'node':'.'}, {'path':[],'node':'.'},
    {'path':'scenes/hierarchy.tscn','node':None}, {'path':'scenes/hierarchy.tscn','node':3},
    {'path':'scenes/hierarchy.tscn','node':True}, {'path':'scenes/hierarchy.tscn','node':[]},
    {'path':'scenes/hierarchy.tscn','node':{}}, {'path':'scenes/hierarchy.tscn','node':'.','extra':1}])
def test_invalid_input_schema(agent,args):
    assert agent.call('node',args)['kind'] == 'invalid_input'


@pytest.mark.parametrize('path',['','../escape.tscn','res://../escape.tscn',r'..\escape.tscn',
    '/absolute.tscn',r'C:\secret.tscn',r'\\server\share\a.tscn','x\x00.tscn','user://a.tscn','file://a.tscn'])
def test_unsafe_paths(agent,path):
    assert agent.call('node',{'path':path,'node':'.'})['kind'] == 'invalid_input'


@pytest.mark.parametrize('path',['addons/other/a.tscn','.agent_history/a.tscn'])
def test_protected_paths(agent,path):
    assert agent.call('node',{'path':path,'node':'.'})['kind'] == 'denied'


def test_actual_file_limit(tmp_path):
    (tmp_path / 'huge.tscn').write_bytes(b' ' * (READ_TEXT_MAX_BYTES + 1))
    result = build_agent(project_root=tmp_path,profile='headless').call('node',{'path':'huge.tscn','node':'.'})
    assert result['kind'] == 'invalid_input' and str(tmp_path) not in json.dumps(result)


def test_strict_result_schema_checks_every_field(agent):
    from python.modules.scene_model.node_info.tools import NODE
    result = agent.call('node',{'path':'scenes/hierarchy.tscn','node':'.'})['result']
    assert not validate(result,NODE.result)
    changed = copy.deepcopy(result); changed['uncontracted'] = True
    assert validate(changed,NODE.result)
    for field in result:
        changed = copy.deepcopy(result); del changed[field]
        assert validate(changed,NODE.result)


@pytest.mark.parametrize(('path','spec'),[('hierarchy.tscn','.'),('hierarchy.tscn','Main/Arm/End'),
    ('instance.tscn','Weapon'),('unique.tscn','%Unique'),('bom.tscn','Tip'),('crlf.tscn','Main/Arm')])
def test_depth_path_and_metadata_equal_accepted_scene(agent,path,spec):
    args = {'path':'scenes/'+path}
    card = agent.call('node',{**args,'node':spec})['result']
    nodes = agent.call('scene',args)['result']['nodes']
    entry = next(n for n in nodes if n['path'] == card['path'])
    for field in ('name','type','parent','path','depth','script','instance'):
        assert card[field] == entry[field]


def test_context_advertises_node_without_hiding_old_tools(agent):
    result = agent.call('context',{'sections':['tools']})['result']['sections']['tools']
    names = ['analyze_rename','api','api_check','ask','assistant_confirm','assistant_plan','assistant_rollback','assistant_turn','chat','check','connections','context','functions','gd_lint','judge','node','node_delete_preview','node_rename_preview','node_reparent_preview','paths_preview','read','scene','scene_deps','search','split_apply','split_gd_plan','split_gd_scan','split_plan','split_scan','usages',
             'verify','write_apply','write_preview','write_rollback']
    assert result == {'count':34,'names':names,'effects':{n:'write' if n == 'split_apply' or n.startswith('write_') or n in ('assistant_confirm','assistant_plan','assistant_rollback','assistant_turn') else 'read' for n in names}}
