"""Permanent red tests after actual-old capture, before behavior."""
import ast
import builtins
import hashlib
import json

import pytest

from python.modules.verification.tscn_lint.domain import core
from .corpus import CASES, CORPUS, ROOT, domain_args


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_full_literal_reference(case):
    actual = core.check(case['args']['content'], **domain_args(case))
    expected = case['reference_result']
    assert set(actual) == {'fixed', 'changed', 'problems'}
    assert actual['fixed'].encode('utf-8') == expected['fixed'].encode('utf-8')
    assert actual['problems'] == expected['problems']
    assert all(isinstance(p, str) for p in actual['problems'])
    assert actual['changed'] is (actual['fixed'] != case['args']['content'])
    assert actual == expected
    if case['expect']['ok']:
        assert actual == case['expect']['result']


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_manifest_case_pin(case):
    manifest = json.loads((CORPUS / 'manifest.json').read_bytes())
    raw = (CORPUS / (case['id'] + '.json')).read_bytes()
    assert manifest['cases'][case['id'] + '.json'] == {
        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def test_manifest_inputs_and_reference_pin():
    manifest = json.loads((CORPUS / 'manifest.json').read_bytes())
    assert len(CASES) == len(manifest['cases']) == 65
    assert len(manifest['inputs']) == 18
    assert manifest['reference_commit'] == 'ba0535d4dec43c32750e601a6ca86e377abc6af3'
    assert manifest['reference']['bytes'] == 74080
    assert manifest['reference']['sha256'] == '118e9ddc0b776cd86974666ff42789a3b41b93ba2b404f06c78db605ca0ac3f8'
    for name, expected in manifest['inputs'].items():
        raw = (CORPUS / name).read_bytes()
        assert expected == {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def test_domain_has_no_io_regex_commands_or_foreign_layers():
    banned = {'os', 'pathlib', 'io', 'socket', 'subprocess', 're', 'pickle'}
    for path in (ROOT / 'python/modules/verification/tscn_lint/domain').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_bytes())):
            if isinstance(node, ast.Import):
                assert all(a.name.split('.')[0] not in banned for a in node.names), path
            if isinstance(node, ast.ImportFrom):
                assert (node.module or '').split('.')[0] not in banned, path
                assert not any(part in {'substrate', 'channels', 'protocol', 'editor'}
                               for part in (node.module or '').split('.')), path
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in {'open', 'eval', 'exec', '__import__'}, path
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in {'compile', 'read_bytes', 'read_text',
                                                  'write_bytes', 'write_text', 'system', 'popen'}, path


@pytest.mark.parametrize('number', [23, 58, 64])
def test_source_data_never_becomes_commands(monkeypatch, number):
    case = CASES[number - 1]
    kwargs = domain_args(case)
    def forbidden(*args, **kwargs):
        pytest.fail('scene data was executed or caused IO')
    with monkeypatch.context() as guard:
        for name in ('open', 'eval', 'exec'):
            guard.setattr(builtins, name, forbidden)
        actual = core.check(case['args']['content'], **kwargs)
    assert actual == case['reference_result']


def test_m5_scanner_problem_prevents_later_uid_and_load_steps_fixes():
    case = CASES[31]
    assert 'uid://dummy' in case['args']['content']
    actual = core.check(case['args']['content'], **domain_args(case))
    assert actual['problems'] == case['reference_result']['problems']
    assert actual['fixed'] == case['args']['content']
    assert actual['changed'] is False
