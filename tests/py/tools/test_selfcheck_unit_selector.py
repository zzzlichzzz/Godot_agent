"""C.19/F4: actual targets, three real counts, unchanged masks and tool ownership."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def gate():
    spec = importlib.util.spec_from_file_location('f4_selfcheck', ROOT/'tools/selfcheck.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def targets(gate, monkeypatch, module_id, here):
    collected, invoked = [], []
    real_count = gate.collect_count
    monkeypatch.setattr(gate, 'collect_count', lambda paths: collected.extend(paths) or 1)
    monkeypatch.setattr(gate, 'run_check', lambda name, argv: invoked.append((name, argv)) or ('ok', 'pin'))
    assert gate.check_unit(module_id, here) == ('ok', 'pin')
    assert invoked == [('unit', ['tools/run_tests.py'] + [gate.rel(p) for p in collected])]
    return collected, real_count


def test_class_api_has_only_its_128_tests(gate, monkeypatch):
    paths, count = targets(gate, monkeypatch, 'engine_kb.class_api',
                           ROOT/'python/modules/engine_kb/class_api')
    assert count(paths) == 128
    assert paths == [ROOT/'python/modules/engine_kb/class_api/tests',
                     ROOT/'tests/py/contract/test_api_contract.py',
                     ROOT/'tests/py/integration/test_api.py',
                     ROOT/'tests/py/integration/test_api_snapshot.py']


@pytest.mark.parametrize('module_id,count', [
    ('scene_model.node_info', 247), ('scene_model.tree', 116),
])
def test_other_two_authorized_real_counts(gate, monkeypatch, module_id, count):
    paths, collect = targets(gate, monkeypatch, module_id, gate.module_dir(module_id))
    assert collect(paths) == count


def test_split_gd_keeps_both_tools_and_legacy_target_order(gate, monkeypatch):
    spec, reason = gate._spec('editing.split_gd')
    assert spec is not None, reason
    paths, _ = targets(gate, monkeypatch, 'editing.split_gd', ROOT/'python/modules/editing/split_gd')
    expected = legacy_targets(gate, 'editing.split_gd')
    assert paths == expected
    integration = ROOT/'tests/py/integration'
    assert integration/'test_split_gd_scan.py' in paths
    assert integration/'test_split_gd_plan.py' in paths
    assert integration/'test_split_gd_exists.py' in paths


@pytest.mark.parametrize('current,filename,selected', [
    ('api', 'test_api.py', True),
    ('api', 'test_api_snapshot.py', True),
    ('api', 'test_api_check.py', False),
    ('api', 'test_api_check_edges.py', False),
    ('api_check', 'test_api_check_edges.py', True),
    ('api_check', 'test_api_check_extra.py', False),
    ('api_check_extra', 'test_api_check_extra_edges.py', True),
    ('api', 'test_api_checks.py', True),
    ('api', 'test_read.py', False),
    ('legacy', 'test_legacy_edges.py', True),
    ('api', 'test_apix.py', True),
    ('api', 'test_api_checksuffix.py', True),
    ('scene', 'test_scene_ops_bridge.py', False),
    ('scene_ops', 'test_scene_ops_bridge.py', True),
])
def test_owner_comes_from_longest_known_tool_not_an_arbitrary_suffix(
        gate, monkeypatch, tmp_path, current, filename, selected):
    integration = tmp_path/'tests/py/integration'
    integration.mkdir(parents=True)
    case = integration/filename
    case.write_bytes(b'')
    here = tmp_path/'python/modules/sample'/current
    (here/'tests').mkdir(parents=True)
    names = ('api', 'api_check', 'api_check_extra', 'read', 'scene', 'scene_ops')
    specs = [SimpleNamespace(id='sample.'+name, provides_tools=(name,)) for name in names]
    if current == 'legacy':
        specs.append(SimpleNamespace(id='sample.legacy', provides_tools=()))
    loaded = [SimpleNamespace(spec=spec) for spec in specs]
    monkeypatch.setattr(gate, 'ROOT', tmp_path)
    monkeypatch.setattr(gate, 'CONTRACTS', tmp_path/'tests/py/contract')
    monkeypatch.setattr(gate, '_catalogue', lambda: (loaded, []))
    paths, _ = targets(gate, monkeypatch, 'sample.'+current, here)
    assert (case in paths) is selected
    assert paths[0] == here/'tests'


def test_api_check_keeps_its_integration_and_contract(gate, monkeypatch):
    paths, _ = targets(gate, monkeypatch, 'verification.api_check',
                       ROOT/'python/modules/verification/api_check')
    assert ROOT/'tests/py/integration/test_api_check.py' in paths
    assert ROOT/'tests/py/contract/test_api_check_contract.py' in paths
    assert ROOT/'tests/py/integration/test_api.py' not in paths


def legacy_targets(gate, module_id):
    """Reference the pre-F4 masks, preserving order and repeated file occurrences."""
    spec, _ = gate._spec(module_id)
    feature = module_id.partition('.')[2].replace('.', '_')
    names = [feature] + list(spec.provides_tools if spec else ())
    result = [gate.module_dir(module_id)/'tests']
    for tool in spec.provides_tools if spec else ():
        path = gate.CONTRACTS/('test_%s_contract.py' % tool)
        if path.exists():
            result.append(path)
    for name in dict.fromkeys(names):
        result.extend(sorted((ROOT/'tests/py/integration').glob('test_%s*.py' % name)))
    return result


MODULE_IDS = sorted(p.parent.parent.name+'.'+p.parent.name
                    for p in (ROOT/'python/modules').glob('*/*/module.py'))
REMOVED = {
    'engine_kb.class_api': ('test_api_check.py',),
    'scene_model.node_info': ('test_node_delete_preview.py', 'test_node_rename_preview.py',
                              'test_node_reparent_preview.py'),
    'scene_model.tree': ('test_scene_deps.py', 'test_scene_ops_bridge.py'),
}


@pytest.mark.parametrize('module_id', MODULE_IDS)
def test_only_three_of_44_target_lists_change_without_reordering(gate, monkeypatch, module_id):
    assert len(MODULE_IDS) == 46
    assert 'assistant.write' in MODULE_IDS
    before = legacy_targets(gate, module_id)
    paths, _ = targets(gate, monkeypatch, module_id, gate.module_dir(module_id))
    removed = {ROOT/'tests/py/integration'/name for name in REMOVED.get(module_id, ())}
    assert paths == [path for path in before if path not in removed]
    assert (paths != before) == (module_id in REMOVED)


def test_non_tool_feature_mask_preserves_repeated_owned_file(gate, monkeypatch, tmp_path):
    integration = tmp_path/'tests/py/integration'
    integration.mkdir(parents=True)
    case = integration/'test_legacy_tool_edges.py'
    case.write_bytes(b'')
    here = tmp_path/'python/modules/sample/legacy'
    (here/'tests').mkdir(parents=True)
    spec = SimpleNamespace(id='sample.legacy', provides_tools=('legacy_tool',))
    monkeypatch.setattr(gate, 'ROOT', tmp_path)
    monkeypatch.setattr(gate, 'CONTRACTS', tmp_path/'tests/py/contract')
    monkeypatch.setattr(gate, '_catalogue', lambda: ([SimpleNamespace(spec=spec)], []))
    paths, _ = targets(gate, monkeypatch, 'sample.legacy', here)
    assert paths == [here/'tests', case, case]
