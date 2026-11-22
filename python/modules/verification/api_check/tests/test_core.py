"""Literal messages/quirks from actual-old corpus; no legacy imports."""
import json
from pathlib import Path
import time

import pytest

from python.modules.verification.api_check.domain import core

ROOT = Path(__file__).resolve().parents[5]
CASES = [json.loads(p.read_bytes()) for p in sorted(
    (ROOT / 'fixtures/corpus/verification/api_check').glob('[0-9]*.json'))]
API_CASES = [c for c in CASES if c['expect']['ok'] and c['fixture'].endswith('/api')]
METHODS = {'connect': [2, 3], 'base': [0, 0], 'inherited': [1, 1], 'f': [2, 3],
           'a': [2, 2], 'zero': [0, 0], 'one': [1, 1], 'overridden': [0, 0]}
MEMBERS = (METHODS, {'parent_prop', 'name', 'position'}, {'parent_signal', 'known_signal', 'moved'})


@pytest.mark.parametrize('case', API_CASES, ids=lambda c: c['id'])
def test_literal_corpus_core(case):
    expected = case['expect']['result']
    members = MEMBERS if expected['checked'] else ({}, set(), set())
    problems, base, checked, reason = core.check(case['args']['content'], {'Node2D': {}}, members)
    assert problems == case['reference_result'] == expected['problems']
    assert (base, checked) == (expected['base_class'], expected['checked'])
    assert reason == (expected['unavailable'][0]['reason'] if expected['unavailable'] else '')


@pytest.mark.parametrize('text,classes,members,expected', [
    ('self.x()', {}, ({}, set(), set()), ('', False, 'no_extends')),
    ('extends Node\nself.x()', {}, ({}, set(), set()), ('Node', False, 'no_cache')),
    ('extends Unknown\nself.x()', {'Node': {}}, ({}, set(), set()), ('Unknown', False, 'base_not_in_cache')),
])
def test_unavailable_precedence(text, classes, members, expected):
    problems, base, checked, reason = core.check(text, classes, members)
    assert problems == [] and (base, checked, reason) == expected


@pytest.mark.parametrize('text,index,end', [('f()', 1, 2), ('f((1),2)', 1, 7), ('f(', 1, -1)])
def test_matching_parenthesis(text, index, end):
    assert core.find_matching_paren(text, index) == end


@pytest.mark.parametrize('inner,count', [('', 0), ('   ', 0), ('1', 1), ('1,2', 2),
                                        ('[1,2],{a:1,b:2}', 2), ('f(1,2),3', 2), ('1,', 2)])
def test_argument_count(inner, count):
    assert core.count_top_level_args('(' + inner + ')', 0, len(inner) + 1) == count


def test_local_declarations_literal():
    text = 'static func f():\n@export var p\n@export_range(0, 2) static var q\nconst C = 1\nsignal s\nenum E {A, B = 3}\n'
    assert core.local_symbols(text) == ({'f'}, {'p', 'q', 'C', 'A', 'B'}, {'s'})


def test_horizontal_whitespace_budget():
    start = time.monotonic()
    assert core.local_symbols(' \n' * 100000) == (set(), set(), set())
    assert time.monotonic() - start < 3.0
