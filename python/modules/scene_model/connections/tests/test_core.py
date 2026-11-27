"""New cases from actual-old capture, not copied old tests."""
import ast
import hashlib
import json
from pathlib import Path
import pytest
from ..domain import core

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT/'fixtures/corpus/scene_model/connections'
MANIFEST = json.loads((CORPUS/'manifest.json').read_bytes())
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('*.json')) if p.name!='manifest.json']
DOMAIN = [c for c in CASES if c['args']['path'].endswith(('.tscn','.scn'))
          and (CORPUS/'project'/c['args']['path'].removeprefix('res://')).is_file()]


@pytest.mark.parametrize('case',DOMAIN,ids=lambda c:c['id'])
def test_literal_raw_and_display_parity(case):
    raw=(CORPUS/'project'/case['args']['path'].removeprefix('res://')).read_bytes()
    if case['expect']['ok']:
        assert core.describe(raw)==case['expect']['result']
    else:
        with pytest.raises(ValueError) as err:
            core.describe(raw)
        assert str(err.value).encode()==case['expect']['message'].encode()


def test_manifest_pins_reference_inputs_and_case_bytes():
    assert len(CASES)>=14
    assert MANIFEST['reference']['commit']=='ba0535d4dec43c32750e601a6ca86e377abc6af3'
    assert MANIFEST['reference']['files']['godot_tools/scene_deps.py']['sha256']=='dbd502afeca7fa2fe97d49a995438c551d313d1713e6591865ab2bf3b053067b'
    for name,digest in MANIFEST['cases'].items():
        assert hashlib.sha256((CORPUS/name).read_bytes()).hexdigest()==digest
    assert set(MANIFEST['inputs'])=={p.relative_to(CORPUS/'project').as_posix() for p in (CORPUS/'project').rglob('*') if p.is_file()}
    for name,info in MANIFEST['inputs'].items():
        value=(CORPUS/'project'/name).read_bytes()
        assert len(value)==info['bytes'] and hashlib.sha256(value).hexdigest()==info['sha256']


def test_domain_has_no_io_re_or_second_parser():
    for path in (CORPUS.parents[3]/'python/modules/scene_model/connections/domain').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_bytes())):
            if isinstance(node,ast.Import):
                assert all(a.name.split('.')[0] not in {'os','pathlib','io','socket','subprocess','re'} for a in node.names)
            if isinstance(node,ast.ImportFrom):
                assert (node.module or '').split('.')[0] not in {'os','pathlib','io','socket','subprocess','re'}
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                assert node.func.id not in {'open','eval','exec','__import__'}


def test_file_strings_are_not_commands(monkeypatch):
    import builtins
    raw=(CORPUS/'project/injection.tscn').read_bytes()
    expected=next(c['expect']['result'] for c in CASES if c['note']=='injection.tscn')
    def forbidden(*args,**kwargs):
        raise AssertionError('file became IO or command')
    with monkeypatch.context() as patch:
        for name in ('open','eval','exec'):
            patch.setattr(builtins,name,forbidden)
        result=core.describe(raw)
    assert result==expected
