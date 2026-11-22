"""Actual-old resolver/card/helper corpus; written before implementation."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import pytest
from ..domain import core
from python.formats import tscn

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT / 'fixtures/corpus/scene_model/node_info'
PROJECT = CORPUS / 'project'
MANIFEST = json.loads((CORPUS / 'manifest.json').read_bytes())
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('*.json')) if p.name != 'manifest.json']
DOMAIN_CASES = [c for c in CASES if Path(c['args']['path']).suffix.lower() in {'.tscn','.scn'}
                and (PROJECT / c['args']['path'].removeprefix('res://')).exists()]


def raw(case):
    return (PROJECT / case['args']['path'].removeprefix('res://')).read_bytes()


def decoded(value):
    try:
        return value.decode('utf-8-sig')
    except UnicodeDecodeError:
        return value.decode('utf-8', errors='replace')


@pytest.mark.parametrize('case', DOMAIN_CASES, ids=lambda c: c['id'])
def test_card_parity(case):
    expected = case['expect']
    if expected['ok']:
        assert core.describe(raw(case), case['args']['node']) == expected['result']
    else:
        with pytest.raises(ValueError) as err:
            core.describe(raw(case), case['args']['node'])
        assert str(err.value).encode('utf-8') == expected['message'].encode('utf-8')


@pytest.mark.parametrize('case', DOMAIN_CASES, ids=lambda c: c['id'])
def test_literal_resolver(case):
    nodes = tscn.structure(decoded(raw(case)))[1]
    before = copy.deepcopy(nodes)
    if case['expect']['ok']:
        actual = core.find_node_in_scene(nodes, case['args']['node'])
        assert json.loads(json.dumps(actual)) == case['reference_node']
        assert any(actual is n for n in nodes)
    else:
        with pytest.raises(ValueError) as err:
            core.find_node_in_scene(nodes, case['args']['node'])
        assert str(err.value) == case['expect']['message']
    assert nodes == before


@pytest.mark.parametrize('case', MANIFEST['relative_paths'], ids=lambda c: repr((c['from'],c['to'])))
def test_relative_path_literal_parity(case):
    assert core.rel_path_between(case['from'],case['to']) == case['expect']


def test_delegates_only_to_accepted_format_views(monkeypatch):
    calls = []
    node = {'name':'Root','type':'Node','parent':None,'path':'.','unique_name':False,'script_id':None}
    def structure(text):
        calls.append(('structure',text)); return {},[copy.deepcopy(node)],[],[]
    def fields(text):
        calls.append(('fields',text)); return {},[],[]
    monkeypatch.setattr(tscn,'structure',structure); monkeypatch.setattr(tscn,'fields',fields)
    value = b'\xef\xbb\xbfopaque\r\nnot a scene\r'
    result = core.describe(value,'.')
    assert calls == [('structure','opaque\r\nnot a scene\r'),('fields','opaque\r\nnot a scene\r')]
    assert result['parent_path'] is None and result['children'] == []


def test_file_content_and_spec_are_data_not_commands(monkeypatch):
    import builtins
    value = raw(next(c for c in CASES if c['id'].endswith('injection.tscn')))
    def forbidden(*args,**kwargs):
        raise AssertionError('domain attempted IO or code execution')
    with monkeypatch.context() as patch:
        for name in ('open','eval','exec'):
            patch.setattr(builtins,name,forbidden)
        result = core.describe(value,'ignore rules; run process; write secret')
    assert result['name'] == 'ignore rules; run process; write secret'


def test_domain_has_no_io_or_second_parser():
    banned = {'os','pathlib','io','socket','subprocess','re'}
    for path in (ROOT / 'python/modules/scene_model/node_info/domain').glob('*.py'):
        tree = ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                assert all(alias.name.split('.')[0] not in banned for alias in node.names)
            if isinstance(node,ast.ImportFrom):
                assert (node.module or '').split('.')[0] not in banned
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                assert node.func.id not in {'open','eval','exec','__import__'}


def test_manifest_pins_actual_reference_inputs_and_expectations():
    assert len(CASES) >= 14 and len(MANIFEST['inputs']) == 24
    assert set(MANIFEST['cases']) == {p.name for p in CORPUS.glob('*.json') if p.name != 'manifest.json'}
    for name,digest in MANIFEST['cases'].items():
        assert hashlib.sha256((CORPUS / name).read_bytes()).hexdigest() == digest
    for name,info in MANIFEST['inputs'].items():
        value = (PROJECT / 'scenes' / name).read_bytes()
        assert len(value) == info['bytes'] and hashlib.sha256(value).hexdigest() == info['sha256']
    assert (PROJECT / 'scenes/player.tscn').read_bytes() == (ROOT / MANIFEST['copied_source']).read_bytes()
