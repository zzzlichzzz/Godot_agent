"""F1 file decode only: one BOM, replacement, no newline/text transformations."""
import pytest


@pytest.mark.parametrize('raw,expected', [
    (b'', ''), (b'plain\r\nnext\r', 'plain\r\nnext\r'),
    (b'\xef\xbb\xbf', ''), (b'\xef\xbb\xbfhello\r\n', 'hello\r\n'),
    (b'\xef\xbb\xbf\xef\xbb\xbfhello', '\ufeffhello'),
    (b'a\xef\xbb\xbfb', 'a\ufeffb'),
    (b'\xef\xbb\xbf\xff', '\ufffd'), (b'\xef\xbb', ''),
])
def test_decode_exact_source(raw, expected):
    from python.modules.verification.shared.source_text import decode_source
    before = bytes(raw)
    assert decode_source(raw) == expected
    assert raw == before
