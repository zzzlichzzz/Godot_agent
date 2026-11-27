"""New-level cases, captured through native prepare, never copied old tests."""
import ast
import base64
import hashlib
import json
from pathlib import Path

import pytest

from ..domain import core

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT / 'fixtures/corpus/scene_model/node_rename'
MANIFEST = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))
CASES = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(CORPUS.glob('[0-9]*.json'))]
LOGIC = [r for r in CASES if r['args']['path'] == 'res://main.tscn']


def supplied(record):
    project = ROOT / 'fixtures/projects' / record['fixture']
    scripts = {'res://' + p.relative_to(project).as_posix(): p.read_bytes()
               for p in project.rglob('*.gd') if 'addons' not in p.relative_to(project).parts}
    expected = record['expect']
    message = expected.get('message', '')
    first = message.split('обнаружена синтаксическая ошибка: ', 1)[-1]
    def linter(text):
        return [first] if 'обнаружена синтаксическая ошибка:' in message else []
    return (project / 'main.tscn').read_bytes(), scripts, linter


@pytest.mark.parametrize('record', LOGIC, ids=lambda r: r['id'])
def test_native_full_plan_and_literal_logic_refusals(record):
    raw, scripts, linter = supplied(record)
    a, e = record['args'], record['expect']
    def call():
        return core.prepare_rename(raw, a['path'], a['node'], a['new_name'], scripts, linter,
                                   update_scripts=a.get('update_scripts', True),
                                   scripts_only=a.get('scripts_only', False), previous_name=a.get('previous_name', ''))
    if e['ok']:
        result = call()
        assert result == e['result']
        for item in result['files']:
            assert hashlib.sha256(base64.b64decode(item['before_bytes'], validate=True)).hexdigest() == item['before_hash']
            for row in item['diff']['lines']:
                assert len(row) == 4 and row[0] in ('@', ' ', '+', '-')
                assert all(v is None or type(v) is int for v in row[1:3])
                assert isinstance(row[3], str)
    else:
        with pytest.raises(ValueError) as error:
            call()
        assert str(error.value) == e['message']


def test_manifest_source_case_and_input_pins():
    assert len(CASES) >= 14
    assert MANIFEST['reference_commit'] == 'ba0535d4dec43c32750e601a6ca86e377abc6af3'
    assert MANIFEST['references'][0]['sha256'] == '2d708a384177fa0a8d4636f3f2dd373508ee316216319edf7d793255d8918a29'
    assert {i['path'] for i in MANIFEST['cases']} == {p.name for p in CORPUS.glob('[0-9]*.json')}
    for pin in MANIFEST['cases'] + MANIFEST['inputs']:
        raw = (CORPUS / pin['path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == pin['sha256']
        if 'bytes' in pin:
            assert len(raw) == pin['bytes']


def test_domain_has_no_io_local_parsers_or_commands():
    paths = list((ROOT / 'python/modules/scene_model/node_rename/domain').glob('*.py'))
    paths.append(ROOT / 'python/modules/scene_model/shared/node_path.py')
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or '']
                assert not {'os', 'pathlib', 'io', 'socket', 'subprocess', 're'} & {n.split('.')[0] for n in names}
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {'open', 'eval', 'exec', '__import__'}


def test_project_strings_do_not_become_commands(monkeypatch):
    record = next(r for r in CASES if r['id'].endswith('commands_are_data'))
    raw, scripts, linter = supplied(record)
    def forbidden(*args, **kwargs):
        raise AssertionError('data executed or domain performed IO')
    with monkeypatch.context() as m:
        for name in ('open', 'eval', 'exec'):
            m.setattr('builtins.' + name, forbidden)
        result = core.prepare_rename(raw, 'res://main.tscn', 'Arm', 'LongArm', scripts, linter)
    assert result == record['expect']['result']


def test_transform_delegates_only_to_formats(monkeypatch):
    from python.formats import gdscript
    record = next(r for r in CASES if r['id'].startswith('002-'))
    raw, scripts, linter = supplied(record)
    calls = []
    def unchanged(text, *args):
        calls.append(text)
        return text, 0
    monkeypatch.setattr(gdscript, 'rename_node_paths', unchanged)
    result = core.prepare_rename(raw, 'res://main.tscn', 'Arm', 'LongArm', scripts, linter)
    assert len(calls) == 2
    assert result['affected_paths'] == ['res://main.tscn']
