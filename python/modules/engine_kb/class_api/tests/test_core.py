"""Pure C.11 rules from recorded actual-old cases; no legacy test code."""
import ast
import copy
import json
from pathlib import Path

import pytest

from python.modules.engine_kb.class_api.domain import core
from python.modules.engine_kb.shared import inheritance

ROOT = Path(__file__).resolve().parents[5]
CORPUS = ROOT / 'fixtures/corpus/engine_kb/class_api'
CASES = [json.loads(p.read_bytes()) for p in sorted(CORPUS.glob('[0-9]*.json'))]


@pytest.mark.parametrize('case', [c for c in CASES if c['expect']['ok']], ids=lambda c: c['id'])
def test_assemble_actual_old(case):
    project = ROOT / 'fixtures/projects' / case['fixture']
    path = project / '.agent_history/godot_api_cache.json'
    try:
        record = json.loads(path.read_bytes())
    except (OSError, ValueError):
        record = {}
    classes = record.get('classes', {}) if isinstance(record, dict) else {}
    before = copy.deepcopy(classes)
    expected = dict(case['expect']['result'], unavailable=[])
    assert core.assemble(case['args']['class_name'].strip(), classes, expected['cache_version']) == expected
    assert classes == before


@pytest.mark.parametrize('arity,expected', [
    ('x', (-1, -1)), ([1], (-1, -1)), (None, (-1, -1)),
    (['no', 1], (-1, -1)), (['2', '4'], (2, 4)), ('12', (1, 2)),
    ([1, 3, 99], (1, 3)), ([1.9, True], (1, 1)),
])
def test_arity_is_legacy_int_projection(arity, expected):
    result = core.assemble('C', {'C': {'methods': {'foo': arity}}}, '4.6')
    assert (result['methods'][0]['min_args'], result['methods'][0]['max_args']) == expected


@pytest.mark.parametrize('depth,expected', [(0, []), (1, ['A']), (2, ['A', 'B']), (30, ['A', 'B'])])
def test_chain_guard_and_custom_depth(depth, expected):
    assert inheritance.resolve_chain({'A': {'inherits': 'B'}, 'B': {'inherits': 'A'}}, 'A', depth) == expected


def test_nearest_member_and_signature_independently_win():
    classes = {'A': {'methods': {'foo': [1, 2]}, 'signatures': {'foo': ''}},
               'B': {'methods': {'foo': [8, 9]}, 'signatures': {'foo': 'parent()'}}}
    assert inheritance.collect_members(classes, ['A', 'B'])[0] == {'foo': [1, 2]}
    assert inheritance.collect_signatures(classes, ['A', 'B']) == {'foo': ''}


def test_signatures_only_str_to_str_pairs():
    assert inheritance.collect_signatures({'C': {'signatures': {1: 'bad', 'bad': 1, 'ok': 'exact'}}}, ['C']) == {'ok': 'exact'}


def test_shared_inheritance_has_no_io_imports_or_calls():
    """ADR-0009: explicit shared gate, since frozen lint_arch covers domain only."""
    tree = ast.parse(Path(inheritance.__file__).read_text(encoding='utf-8'))
    forbidden = {'os', 'io', 'pathlib', 'shutil', 'json', 'subprocess', 'socket',
                 'tempfile', 'sqlite3', 'urllib', 'http', 'builtins', 'importlib'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split('.')[0] for a in node.names} & forbidden
        if isinstance(node, ast.ImportFrom):
            assert (node.module or '').split('.')[0] not in forbidden
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {'open', 'eval', 'exec', '__import__'}
