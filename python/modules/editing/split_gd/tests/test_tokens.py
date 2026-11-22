import pytest

from ..domain.tokens import prev_token, tokenize
from .plan_corpus import NATIVE, source


@pytest.mark.parametrize('case', NATIVE, ids=lambda c: c['id'])
def test_frozen_native_token_offsets(case):
    text = source(case)
    result = tokenize(text)
    assert result == case['reference_tokens']
    assert all(text[t['start']:t['end']] == t['value'] for t in result)


def test_comments_strings_offsets_and_significant_predecessor():
    text = '# ignored\nself.thing("a\\\"b", 0xFF)\n'
    tokens = tokenize(text)
    assert [t['value'] for t in tokens] == ['\n', 'self', '.', 'thing', '(', '"a\\\"b"', ',', '0xFF', ')', '\n']
    assert tokens[5]['closed'] is True
    assert prev_token(tokens, 1) is None
    assert prev_token(tokens, len(tokens))['value'] == ')'


def test_unclosed_and_triple_string_newlines():
    tokens = tokenize('"unclosed\n"""a\nb"""\n')
    assert tokens[0]['closed'] is False and tokens[0]['end'] == 9
    assert tokens[2]['closed'] is True and tokens[2]['line'] == 2
