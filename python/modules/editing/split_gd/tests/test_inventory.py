"""Full native inventory, including quirks invisible in the scan payload."""
import pytest

from python.modules.editing.split_gd.domain.inventory import file_inventory, parse_params
from python.modules.editing.split_gd.domain.text import (
    balance, code_skeleton, decode, indent_width, leading_comment_start, newline_of,
)
from .corpus import NATIVE, inputs


@pytest.mark.parametrize('case', NATIVE, ids=lambda c: c['id'])
def test_frozen_inventory(case):
    raw = dict(inputs(case))[case['reference_donor']]
    assert file_inventory(decode(raw)) == case['reference_inventory']


@pytest.mark.parametrize('text,expected', [
    ('func f(a: int, b = [1, 2], c = {"x": 3}):',
     [{'name': 'a', 'default': None}, {'name': 'b', 'default': '[1, 2]'},
      {'name': 'c', 'default': '{"x": 3}'}]),
    ('func f(a = "x,y"):', [{'name': 'a', 'default': '"x'}, {'name': 'y', 'default': None}]),
    ('func f(a,', [{'name': 'a', 'default': None}]),
    ('no opening', []),
])
def test_params_bracket_aware_not_quote_aware(text, expected):
    assert parse_params(text) == expected


@pytest.mark.parametrize('raw,expected', [(b'\xef\xbb\xbfabc', 'abc'),
    (b'\xef\xbb\xbf\xef\xbb\xbfabc', '\ufeffabc'), (b'\xef\xbb', ''),
    (b'a\xff', 'a\ufffd'), (b'a\r\nb\rc\n', 'a\nb\nc\n')])
def test_incremental_decode_final_and_universal_newlines(raw, expected):
    assert decode(raw) == expected


@pytest.mark.parametrize('text,expected', [('"[" # }', 0), ('["}"]', 0),
    ('[ # ]\n', 1), ('"""[\n]"""()', 0), ('"unterminated\n[', 1),
    ('"trailing\\', 0)])
def test_balance_string_comment_escape_quirks(text, expected):
    assert balance(text) == expected


def test_skeleton_comment_retains_native_double_newline():
    assert code_skeleton('a # comment\nb') == 'a \n\nb'
    assert indent_width(' \t x') == 3
    assert leading_comment_start(['', '# x', '@tool', 'func f():'], 3) == 1
    assert newline_of('a\r\nb') == '\r\n' and newline_of('a\rb') == '\n'


def test_unclosed_signature_still_inventoried():
    info = file_inventory('func broken(a: int,\n')
    assert info['errors'] == ['line 1: сигнатура broken не закрыта']
    assert info['funcs'][0]['name'] == 'broken'
