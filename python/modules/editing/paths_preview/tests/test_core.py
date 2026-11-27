"""C.21 literal normalization, decoding and internal-path projection pins."""
import pytest

from python.kernel.errors import AppError


@pytest.mark.parametrize("path,expected", [
    ("res://a.gd", "res://a.gd"), ("  res://a.gd/ ", "res://a.gd"),
    ("res://\\src\\a.gd", "res://src/a.gd"), ("res://кириллица/а.gd", "res://кириллица/а.gd"),
])
def test_normalize_valid(path, expected):
    from python.modules.editing.paths_preview.domain.core import normalize
    assert normalize(path) == expected


@pytest.mark.parametrize("path,message", [
    ("a.gd", "Путь должен начинаться с res://: a.gd"),
    ("res://./a.gd", "Некорректный путь: res://./a.gd"),
    ("res://a//b.gd", "Некорректный путь: res://a//b.gd"),
    ("res://../a.gd", "Путь вне проекта отклонен: res://../a.gd"),
    ("res://a/../b.gd", "Путь вне проекта отклонен: res://a/../b.gd"),
    ("res://", "Некорректный путь: res://"),
])
def test_normalize_refusals(path, message):
    from python.modules.editing.paths_preview.domain.core import normalize
    with pytest.raises(AppError) as caught:
        normalize(path)
    assert caught.value.kind == "invalid_input" and caught.value.message == message


@pytest.mark.parametrize("raw,text,bom", [
    (b"a\r\nb\rc\n", "a\r\nb\rc\n", False),
    (b"\xef\xbb\xbfa\r\n", "a\r\n", True),
    (b"\xff# x", "\ufffd# x", False),
])
def test_decode_preserves_native_newlines_and_replacement(raw, text, bom):
    from python.modules.editing.paths_preview.domain.refs import decode
    assert decode(raw) == (text, bom)


@pytest.mark.parametrize("text,old,new,existing,moved,expected", [
    ('preload("missing.gd")', "res://old/a.gd", "res://new/a.gd", set(), None,
     ('preload("missing.gd")', 0)),
    ('preload("missing.gd")', "res://old/a.gd", "res://new/a.gd", set(),
     {"res://old/missing.gd": "res://elsewhere/renamed.gd"}, ('preload("res://elsewhere/renamed.gd")', 1)),
    ('load("uid://fixed")\r\n', "res://old/a.gd", "res://new/a.gd", set(), None,
     ('load("uid://fixed")\r\n', 0)),
    ('preload("./b.gd")', "res://old/a.gd", "res://new/a.gd", {"old/b.gd"},
     {"res://old/b.gd": "res://new/b.gd"}, ('preload("./b.gd")', 0)),
    ('preload("res://old/b.gd")', "res://old/a.gd", "res://new/a.gd", {"old/b.gd"},
     {"res://old/b.gd": "res://new/b.gd"}, ('preload("res://new/b.gd")', 1)),
    ('[ext_resource path="../x.gd"', "res://old/a.tscn", "res://new/a.tscn", set(), None,
     ('[ext_resource path="../x.gd"', 0)),
    ('preload("b.gd")', "res://old/a.tscn", "res://new/a.tscn", {"old/b.gd"}, None,
     ('preload("res://old/b.gd")', 1)),
])
def test_internal_native_pins(text, old, new, existing, moved, expected):
    from python.modules.editing.paths_preview.domain.internal import update_internal_relative_paths
    assert update_internal_relative_paths(text, old, new, existing, moved) == expected


def test_internal_outside_is_not_silently_kept():
    from python.modules.editing.paths_preview.domain.internal import update_internal_relative_paths
    with pytest.raises(AppError, match="Путь вне проекта отклонен: res://../outside.gd"):
        update_internal_relative_paths('load("../../outside.gd")', "res://src/a.gd", "res://new/a.gd", set())
