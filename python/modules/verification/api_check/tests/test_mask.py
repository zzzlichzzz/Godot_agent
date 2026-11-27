"""Masking preserves source offsets, newlines and literal legacy quirks."""
import pytest


def mask(text, strings, comments):
    from python.modules.verification.api_check.domain.mask import mask as run
    return run(text, strings, comments)


@pytest.mark.parametrize('strings', [False, True])
@pytest.mark.parametrize('comments', [False, True])
def test_independent_masks(strings, comments):
    text = 'self.x # self.y\n"self.z"\n'
    expected = 'self.x ' + (' ' * 8 if comments else '# self.y') + '\n'
    expected += (' ' * 8 if strings else '"self.z"') + '\n'
    assert mask(text, strings, comments) == expected


@pytest.mark.parametrize('literal', ["'self.fake()'", '"self.fake()"',
                                     "'a\\'b'", '"a\\"b"',
                                     '"""self.fake()\nself.fake\n"""',
                                     "'''self.fake()\n# comment\n'''", '"unclosed', '"escape\\'])
def test_strings_escaped_triple_and_unclosed(literal):
    text = 'var x = ' + literal
    expected = 'var x = ' + ''.join('\n' if c == '\n' else ' ' for c in literal)
    assert mask(text, True, True) == expected
    assert mask(text, False, True) == text


@pytest.mark.parametrize('text', ['', '# "self.fake()"', '# quote\nself.real()',
                                  '"# self.fake()" # comment\r\nself.real()',
                                  '"""x\r\ny"""\n#comment'])
def test_length_and_newline_positions(text):
    result = mask(text, True, True)
    assert len(result) == len(text)
    assert [i for i, c in enumerate(result) if c == '\n'] == [i for i, c in enumerate(text) if c == '\n']


def test_comments_do_not_open_strings():
    assert mask('# "quote\nself.real()', True, True) == ' ' * 8 + '\nself.real()'
