"""D20 pure projection of native text, Unicode characters, not encoded bytes."""
import pytest


@pytest.mark.parametrize("text,limit,expected", [
    ("", 1, ("", False, 0)), ("я🐉\n", 2, ("я🐉", True, 2)),
    ("alpha\nbeta\n", 11, ("alpha\nbeta\n", False, 11)),
])
def test_native_character_projection(text, limit, expected):
    from python.modules.project_text.read.domain import core
    answer = core.render("res://plain.txt", text, limit)
    assert answer == dict(path="res://plain.txt", content=expected[0],
                          truncated=expected[1], chars=expected[2])
