"""Permanent exact deletion plans: scripts are warnings, never edited."""
import ast
import base64
import hashlib
import json
from pathlib import Path

import pytest

from tests.py.node_c7_ports import c7_ports

from ..domain import core

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT / 'fixtures/corpus/scene_model/node_delete'
MANIFEST = json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8'))
CASES = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(CORPUS.glob('[0-9]*.json'))]
LOGIC = [r for r in CASES if r['args']['path'] == 'res://main.tscn']


def supplied(record):
    project = ROOT / 'fixtures/projects' / record['fixture']
    return (project / 'main.tscn').read_bytes(), {
        'res://' + p.relative_to(project).as_posix(): p.read_bytes()
        for p in project.rglob('*.gd') if 'addons' not in p.relative_to(project).parts}


def plan(record, ports):
    raw, scripts = supplied(record)
    a = record['args']
    return core.prepare_delete(raw, a['path'], a['node'], scripts, ports['node_diff'],
                               cleanup_code=a.get('cleanup_code', True))


@pytest.mark.parametrize('record', LOGIC, ids=lambda r: r['id'])
def test_full_native_plan_or_literal_refusal(record, c7_ports):
    e = record['expect']
    if not e['ok']:
        with pytest.raises(ValueError) as got:
            plan(record, c7_ports)
        assert str(got.value) == e['message']
        return
    result = plan(record, c7_ports)
    assert result == e['result']
    assert len(result['files']) == 1 and result['affected_paths'] == ['res://main.tscn']
    f = result['files'][0]
    before = base64.b64decode(f['before_bytes'], validate=True)
    assert before == supplied(record)[0] and hashlib.sha256(before).hexdigest() == f['before_hash']
    after = base64.b64decode(f['after_bytes'], validate=True)
    assert before.startswith(b'\xef\xbb\xbf') == after.startswith(b'\xef\xbb\xbf')
    assert result['reference_count'] == f['occurrences']
    assert len(result['warnings']) == len({(w['file'], w['line']) for w in result['warnings']})
    for row in f['diff']['lines']:
        assert len(row) == 4 and row[0] in ('@', ' ', '+', '-')
        assert all(v is None or type(v) is int for v in row[1:3])


def test_manifest_source_case_input_and_read_only_pins():
    assert len(CASES) == 27 and MANIFEST['reference_commit'] == 'ba0535d4dec43c32750e601a6ca86e377abc6af3'
    assert MANIFEST['references'][0]['sha256'] == '2d708a384177fa0a8d4636f3f2dd373508ee316216319edf7d793255d8918a29'
    assert MANIFEST['references'][0]['bytes'] == 46881
    assert {p['path'] for p in MANIFEST['cases']} == {p.name for p in CORPUS.glob('[0-9]*.json')}
    for pin in MANIFEST['cases'] + MANIFEST['inputs']:
        raw = (CORPUS / pin['path']).read_bytes()
        assert len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256']
    assert len(MANIFEST['read_only_proofs']) == len(CASES)
    assert all(p['project_sha_before'] == p['project_sha_after'] for p in MANIFEST['read_only_proofs'])
    assert not (ROOT / 'tools/_capture_node_c7.py').exists()


def test_domain_has_no_io_regex_or_command_execution():
    for p in (ROOT / 'python/modules/scene_model/node_delete/domain').glob('*.py'):
        for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or '']
                assert not {'os', 'pathlib', 'io', 'socket', 'subprocess', 're'} & {s.split('.')[0] for s in names}
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                assert n.func.id not in {'open', 'eval', 'exec', '__import__'}


def test_poisoned_strings_and_scripts_are_not_executed(monkeypatch, c7_ports):
    record = next(r for r in CASES if r['id'].endswith('commands_are_data'))
    raw, scripts = supplied(record)
    diff = c7_ports['node_diff']
    def forbidden(*args, **kwargs):
        raise AssertionError('domain executed project data or performed IO')
    with monkeypatch.context() as m:
        for name in ('open', 'eval', 'exec'):
            m.setattr('builtins.' + name, forbidden)
        result = core.prepare_delete(raw, 'res://main.tscn', 'Old', scripts, diff)
    assert result == record['expect']['result']


def test_warning_facts_use_formats_and_skip_deleted_scripts(monkeypatch, c7_ports):
    from python.formats import gdscript
    raw, scripts = supplied(CASES[1])
    scanned = []
    def references(text, paths, names):
        scanned.append(text)
        return []
    monkeypatch.setattr(gdscript, 'deleted_node_references', references)
    result = core.prepare_delete(raw, 'res://main.tscn', 'Old', scripts, c7_ports['node_diff'])
    assert len(scanned) == 2 and scripts['res://tip.gd'].decode() not in scanned
    assert result['warnings'] == [] and len(result['files']) == 1
