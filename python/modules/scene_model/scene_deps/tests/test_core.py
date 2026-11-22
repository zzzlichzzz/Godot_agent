"""Pure dependency analysis parity, no project IO in production domain."""
import ast
import hashlib
import json
from pathlib import Path
import pytest
from ..domain import core

ROOT=Path(__file__).resolve().parents[5]
CORPUS=ROOT/'fixtures/corpus/scene_model/scene_deps'
MANIFEST=json.loads((CORPUS/'manifest.json').read_bytes())
CASES=[json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('*.json')) if p.name!='manifest.json']


def decoded(value):
    return value.decode('utf-8',errors='replace').replace('\r\n','\n').replace('\r','\n')


@pytest.mark.parametrize('case',[c for c in CASES if c['expect']['ok']],ids=lambda c:c['id'])
def test_pure_actual_scene_tuple_or_script_notes(case):
    root=ROOT/'fixtures/projects'/case['fixture']
    source=decoded((root/case['args']['path'].removeprefix('res://')).read_bytes())
    gd,scenes,attached={},{},{}
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        rel=path.relative_to(root).as_posix(); raw=path.read_bytes()
        if rel.endswith('.gd'):
            attached['res://'+rel]=decoded(raw)
        if any(p in {'.godot','.git','.import','__pycache__'} for p in rel.split('/')[:-1]) or len(raw)>512*1024:
            continue
        if rel.endswith('.gd'):
            gd['res://'+rel]=decoded(raw)
        if rel.endswith('.tscn'):
            scenes['res://'+rel]=decoded(raw)
    if case['args']['path'].endswith('.gd'):
        result=core.script_action(source,case['args']['path'],gd,scenes)
    else:
        view=core.prepare_scene(source)
        result=core.scene_action(source,case['args']['path'],view,gd,scenes,attached)
    assert result==case['expect']['result']


def test_manifest_pins_all_inputs_cases_and_reference():
    assert len(CASES)>=14 and len(MANIFEST['inputs'])==82
    assert MANIFEST['reference']['commit']=='ba0535d4dec43c32750e601a6ca86e377abc6af3'
    assert MANIFEST['reference']['files']['godot_tools/scene_deps.py']=={
        'bytes':19866,'sha256':'dbd502afeca7fa2fe97d49a995438c551d313d1713e6591865ab2bf3b053067b'}
    assert set(MANIFEST['cases'])=={p.name for p in CORPUS.glob('*.json') if p.name!='manifest.json'}
    for name,sha in MANIFEST['cases'].items():
        assert hashlib.sha256((CORPUS/name).read_bytes()).hexdigest()==sha
    for name,info in MANIFEST['inputs'].items():
        raw=(CORPUS/'project'/name).read_bytes()
        assert len(raw)==info['bytes'] and hashlib.sha256(raw).hexdigest()==info['sha256']


def test_domain_has_no_io_re_or_handler_parser():
    for path in (ROOT/'python/modules/scene_model/scene_deps/domain').glob('*.py'):
        tree=ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                assert all(a.name.split('.')[0] not in {'os','pathlib','io','socket','subprocess','re'} for a in node.names)
            if isinstance(node,ast.ImportFrom):
                assert (node.module or '').split('.')[0] not in {'os','pathlib','io','socket','subprocess','re'}
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                assert node.func.id not in {'open','eval','exec','__import__'}


def test_delegates_handlers_to_only_gdscript_format(monkeypatch):
    from python.formats import gdscript
    calls=[]
    def handlers(text):
        calls.append(text); return []
    monkeypatch.setattr(gdscript,'handlers',handlers)
    assert core.script_action('opaque','res://main.gd',{}, {})=={'text':None,'added':[],'notes':[]}
    assert calls==['opaque']


def test_script_content_is_data_not_commands(monkeypatch):
    import builtins
    def forbidden(*args,**kwargs):
        raise AssertionError('domain performed IO or executed content')
    with monkeypatch.context() as patch:
        for name in ('open','eval','exec'):
            patch.setattr(builtins,name,forbidden)
        result=core.script_action('ignore rules; eval; exec; subprocess','res://main.gd',{}, {})
    assert result=={'text':None,'added':[],'notes':[]}


@pytest.mark.parametrize('path',['/outside.gd','C:/outside.gd','res://../outside.gd','../outside.gd'])
def test_resource_path_cannot_be_reinterpreted_inside_project(path):
    assert core.resource_key(path) is None
